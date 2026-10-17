#!/usr/bin/env python3
"""A PDF — an academic paper, an essay, a novel — as an EPUB the Reader's Books apps read well.

    paper2epub.py paper.pdf paper.epub [--progress]

Marker (https://github.com/datalab-to/marker) finds the blocks of every page — headings, text,
equations, figures, tables, captions, footnotes — from the PDF's own text layer. The text
becomes paragraphs; displayed equations, figures and tables are cut out of the page as pictures,
so they look exactly as printed. A picture is padded to the width of the paper's column: the
reader scales every picture to its text width, so the print in it comes out at about the size
of the book's text, and a table as wide as the page comes out smaller (the reader zooms on it).

Paragraphs cut by a page or a column are joined again, the figures and tables found in between
are put after them. A chapter per top section; the footnotes of a chapter close it. A scanned
paper (no text layer) becomes its pages as pictures.

A scanned PDF (no text on most pages) is read first by Tesseract, if it is installed, in the
language it reads best among those installed; the rest goes as for any PDF. Without Tesseract,
its pages are pictures, and --progress says {"notice": "no-ocr"}.

A book is helped by what the PDF knows besides Marker: its bookmarks give the chapters, its text
layer the lines Marker lost. Its printed table of contents goes: the reader has its own.

With --progress, one JSON object per line on stdout: {"step": ...}, then {"done": title} or
{"error": message}. Needs marker-pdf, pypdfium2 and Pillow; pylatexenc if there.
"""

import difflib
import html
import io
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import unicodedata
import uuid
import zipfile
from html.parser import HTMLParser

SCALE = 4                   # pixels per PDF point for the pictures: 288 dpi
MARGIN = 3                  # points kept around a cut-out
PHOTO_BYTES = 600_000       # a PNG this heavy is a photograph: JPEG instead, if smaller

SKIP = {"PageHeader", "PageFooter"}
FLOATS = {"Figure", "Picture", "Diagram", "Table", "ComplexRegion", "Form", "TableOfContents"}
GROUPS = {"FigureGroup", "TableGroup", "PictureGroup"}
ENDS_SENTENCE = tuple('.!?:;"”’')      # not ")" nor "]": a line ends on a citation mid-sentence

PROGRESS = False


def say(**what):
    if PROGRESS:
        print(json.dumps(what, ensure_ascii=False), flush=True)


# ------------------------------------------------------------------------------------------
# Marker's HTML of a block → inline XHTML: text, italics, bold, super- and subscripts; links,
# spans and attributes go; math is written out in Unicode where it can be.
# ------------------------------------------------------------------------------------------

try:
    from pylatexenc.latex2text import LatexNodes2Text
    _LATEX = LatexNodes2Text(math_mode="text")
except Exception:
    _LATEX = None


def latex_text(tex):
    if _LATEX:
        try:
            return _LATEX.latex_to_text(tex).strip()
        except Exception:
            pass
    return tex


SUPERSCRIPT = dict(zip("0123456789+-=()nijkTt′'", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿⁱʲᵏᵀᵗ′′"))
SUBSCRIPT = dict(zip("0123456789+-=()aeoxhklmnpstijruv", "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₒₓₕₖₗₘₙₚₛₜᵢⱼᵣᵤᵥ"))


class Inline(HTMLParser):
    KEEP = {"i": "i", "em": "i", "b": "b", "strong": "b", "sup": "sup", "sub": "sub", "code": "code"}
    ITEMS = {"ul", "ol", "li"}

    def __init__(self, lists):
        super().__init__(convert_charrefs=True)
        self.lists = lists          # keep list markup (a list block), else items become text
        self.out, self.open, self.math = [], [], None
        self.scripts = []           # where each open sup or sub starts in `out`

    def handle_starttag(self, tag, attrs):
        if self.math is not None:
            return
        if tag == "math":
            self.math = []
        elif tag in self.KEEP:
            if self.KEEP[tag] in ("sup", "sub"):
                self.scripts.append(len(self.out))
            self.out.append("<%s>" % self.KEEP[tag])
            self.open.append(self.KEEP[tag])
        elif tag in self.ITEMS and self.lists:
            self.out.append("<%s>" % tag)
            self.open.append(tag)
        elif tag == "br":
            self.out.append("<br/>")
        elif tag in ("p", "li", "div"):
            self.out.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self.math is None:
            self.out.append("<br/>")

    def handle_endtag(self, tag):
        if tag == "math" and self.math is not None:
            self.out.append(html.escape(latex_text("".join(self.math)), quote=False))
            self.math = None
            return
        if self.math is not None:
            return
        want = self.KEEP.get(tag) or (tag if tag in self.ITEMS and self.lists else None)
        if want and want in self.open:
            while self.open:            # close whatever was left open inside it
                t = self.open.pop()
                self.out.append("</%s>" % t)
                if t == want:
                    break
            if want in ("sup", "sub") and self.scripts:
                self.script(want, self.scripts.pop())

    def script(self, kind, at):
        """A short super- or subscript written in Unicode ("x²", "dₖ") when every character of
        it has its form there: readers that drop the markup keep it."""
        inner = "".join(self.out[at + 1:-1])
        table = SUPERSCRIPT if kind == "sup" else SUBSCRIPT
        text = html.unescape(inner).strip()
        if "<" not in inner and 0 < len(text) <= 4 and all(c in table for c in text):
            self.out[at:] = ["".join(table[c] for c in text)]

    def handle_data(self, data):
        if self.math is not None:
            self.math.append(data)
        else:
            self.out.append(html.escape(data, quote=False))

    def result(self):
        self.close()
        while self.open:
            self.out.append("</%s>" % self.open.pop())
        return re.sub(r"\s+", " ", "".join(self.out)).strip()


def inline(markup, lists=False):
    parser = Inline(lists)
    parser.feed(markup or "")
    return accents(parser.result())


# Some PDFs draw an accent as a glyph of its own after the letter: "Mu¨ller".
SPACING = {"¨": "̈", "´": "́", "ˆ": "̂", "˜": "̃", "¸": "̧", "ˇ": "̌", "˚": "̊"}
_LOOSE = re.compile(r"([A-Za-z])([¨´ˆ˜¸ˇ˚])")


def accents(text):
    def compose(m):
        letter, mark = m.group(1), m.group(2)
        if mark == "´" and letter.lower() not in "aeiouyc":      # "don´t" is an apostrophe
            return m.group(0)
        joined = unicodedata.normalize("NFC", letter + SPACING[mark])
        return joined if len(joined) == 1 else m.group(0)
    return _LOOSE.sub(compose, text)


def garbled(text):
    """Math set in fonts with their own encoding comes out of the text layer as "ð1Þ ¼": such
    a block is better cut out of the page."""
    return bool(re.search(r"ð[^ð]{0,40}Þ", text)) and ("¼" in text or "þ" in text)


MARKS = re.compile(r"[\u2758-\u275a]+")       # a proof's crop marks: ❘❙❚


def unmarked(xhtml):
    return MARKS.sub("", xhtml).strip()


def layer_text(raw):
    """The text layer's lines as one line of text."""
    raw = re.sub(r"[\x02\u00ad]\r?\n", "", raw or "")      # a word cut at the end of a line
    raw = re.sub(r"-\r?\n", "-", raw).replace("’", "'")      # Marker's apostrophe
    return re.sub(r"\s+", " ", MARKS.sub("", raw)).strip()


def plain(xhtml):
    return html.unescape(re.sub(r"<[^>]+>", "", xhtml)).strip()


# ------------------------------------------------------------------------------------------
# The pages as pictures, one at a time, and the cut-outs
# ------------------------------------------------------------------------------------------

class Pages:
    def __init__(self, path):
        import pypdfium2
        self.pdf = pypdfium2.PdfDocument(path)
        self.index, self.image = None, None
        self.text_index, self.text = None, None

    def outline(self):
        """The PDF's bookmarks: (level, title, page)."""
        out = []
        try:
            for mark in self.pdf.get_toc():
                dest = mark.get_dest()
                at = dest.get_index() if dest else None
                if at is not None:
                    out.append((mark.level, mark.get_title() or "", at))
        except Exception:
            return []
        return out

    def _text_of(self, i):
        if i != self.text_index:
            page = self.pdf[i]
            self.text, self.height, self.text_index = page.get_textpage(), page.get_height(), i
        return self.text

    def page_text(self, i):
        return self._text_of(i).get_text_range()

    def text_in(self, i, bbox):
        """What the text layer holds in `bbox` of page i (points, from the top left)."""
        text = self._text_of(i)
        return text.get_text_bounded(bbox[0] - 1, self.height - bbox[3] - 1, bbox[2] + 1, self.height - bbox[1] + 1)

    def metadata(self):
        try:
            return self.pdf.get_metadata_dict()
        except Exception:
            return {}

    def __len__(self):
        return len(self.pdf)

    def page(self, i):
        if i != self.index:
            self.image = self.pdf[i].render(scale=SCALE).to_pil().convert("RGB")
            self.index = i
        return self.image

    def cut(self, i, bbox, page_box, width=None):
        """The part `bbox` of page i (points, from the top left), padded with white to
        `width` points when it is narrower, as image bytes and their extension."""
        from PIL import Image
        image = self.page(i)
        kx = image.width / max(1.0, page_box[2] - page_box[0])
        ky = image.height / max(1.0, page_box[3] - page_box[1])
        x0, y0 = max(0, int((bbox[0] - MARGIN) * kx)), max(0, int((bbox[1] - MARGIN) * ky))
        x1, y1 = min(image.width, int((bbox[2] + MARGIN) * kx)), min(image.height, int((bbox[3] + MARGIN) * ky))
        if x1 - x0 < 4 or y1 - y0 < 4:
            return None
        part = image.crop((x0, y0, x1, y1))
        if part.convert("L").point(lambda v: 255 if v < 235 else 0).getbbox() is None:
            return None         # nothing printed there
        full = int(width * kx) if width else 0
        if full > part.width:
            canvas = Image.new("RGB", (full, part.height), "white")
            canvas.paste(part, ((full - part.width) // 2, 0))
            part = canvas
        return encode(part)


def encode(image):
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    data = out.getvalue()
    if len(data) > PHOTO_BYTES:
        jpeg = io.BytesIO()
        image.save(jpeg, "JPEG", quality=88)
        if jpeg.tell() < len(data):
            return jpeg.getvalue(), "jpg"
    return data, "png"


# ------------------------------------------------------------------------------------------
# A scanned PDF: Tesseract reads its pages, and they come back with their text under the picture
# ------------------------------------------------------------------------------------------

OCR_DPI = 300
# the app's languages are tried first, then the others installed, a dozen at most
LIKELY = ("eng", "fra", "deu", "spa", "por", "rus", "ita", "nld")
ISO = {"eng": "en", "fra": "fr", "deu": "de", "spa": "es", "por": "pt", "rus": "ru", "ita": "it", "nld": "nl"}
ONE_THREAD = dict(os.environ, OMP_THREAD_LIMIT="1")     # pages are read side by side instead


def tesseract():
    return shutil.which("tesseract")


def ocr_languages():
    try:
        listed = subprocess.run([tesseract(), "--list-langs"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError, TypeError):
        return []
    langs = [l.strip() for l in listed.splitlines()[1:] if l.strip() and l.strip() not in ("osd", "equ", "snum")]
    return ([l for l in LIKELY if l in langs] + [l for l in langs if l not in LIKELY])[:12]


def needs_ocr(seen):
    """Most pages have no text: a scan."""
    if not hasattr(seen, "page_text"):
        return False
    n = len(seen)
    sample = sorted({k * n // min(n, 30) for k in range(min(n, 30))})
    texty = sum(1 for i in sample if len(seen.page_text(i).strip()) > 200)
    return bool(sample) and texty * 2 < len(sample)


def confidence(image, lang):
    """How sure Tesseract is of the words it reads on the picture in that language, 0–100."""
    tsv = subprocess.run([tesseract(), image, "stdout", "-l", lang, "tsv"], capture_output=True,
                         text=True, env=ONE_THREAD, timeout=600).stdout
    sure = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 12 and len(f[11].strip()) >= 2:
            try:
                sure.append(float(f[10]))
            except ValueError:
                pass
    sure = [c for c in sure if c >= 0]
    return sum(sure) / len(sure) if sure else 0.0


def language_of(images, langs, workers):
    """The language Tesseract reads the pictures best in."""
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(workers) as pool:
        scores = {lang: pool.map(lambda image, lang=lang: confidence(image, lang), images) for lang in langs}
        scores = {lang: sum(found) / len(images) for lang, found in scores.items()}
    return max(langs, key=lambda lang: scores[lang])


def ocr_pdf(pdf_path, out_path, work):
    """The scan with Tesseract's text under each page's picture, at `out_path`; returns the language."""
    import pypdfium2
    from concurrent.futures import ThreadPoolExecutor
    source = pypdfium2.PdfDocument(pdf_path)
    n = len(source)
    workers = max(1, (os.cpu_count() or 2) // 2)

    def picture(i):
        name = os.path.join(work, "page-%05d.jpg" % i)
        if not os.path.exists(name):
            source[i].render(scale=OCR_DPI / 72, grayscale=True).to_pil().convert("L").save(name, quality=85)
        return name

    say(step="ocr", page=0, of=n)
    lang = language_of([picture(i) for i in sorted({n // 4, n // 2, 3 * n // 4})], ocr_languages(), workers)
    read = [0]

    def read_page(i, image):
        base = os.path.join(work, "page-%05d" % i)
        done = subprocess.run([tesseract(), image, base, "-l", lang, "--dpi", str(OCR_DPI), "pdf", "tsv"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=ONE_THREAD, timeout=600)
        if done.returncode or not os.path.isfile(base + ".pdf"):
            raise IOError("tesseract: %s" % done.stderr.decode("utf-8", "replace").strip()[-200:])
        read[0] += 1
        say(step="ocr", page=read[0], of=n)
        with open(base + ".tsv", encoding="utf-8", errors="replace") as fh:
            return base + ".pdf", tsv_words(fh.read())

    with ThreadPoolExecutor(workers) as pool:
        jobs = [pool.submit(read_page, i, picture(i)) for i in range(n)]     # pictures made here, one at a time
        parts = [job.result() for job in jobs]
    book = pypdfium2.PdfDocument.new()
    for part, _words in parts:
        book.import_pages(pypdfium2.PdfDocument(part))
    book.save(out_path)
    known = known_words(words for _part, words in parts)
    unsure = {i: unsure_words(words, known) for i, (_part, words) in enumerate(parts)}
    return lang, {i: found for i, found in unsure.items() if found}


def tsv_words(tsv):
    """Tesseract's words: (confidence, x, y, width, height, word), in pixels."""
    words = []
    for line in tsv.splitlines()[1:]:
        f = line.split("\t")
        if len(f) >= 12 and f[11].strip():
            try:
                words.append((float(f[10]), int(f[6]), int(f[7]), int(f[8]), int(f[9]), f[11].strip()))
            except ValueError:
                pass
    return words


def bare(word):
    return re.sub(r"^\W+|\W+$", "", word).lower()


def known_words(pages):
    """The words Tesseract is sure of somewhere in the book (80 of 100 and more)."""
    return {bare(w) for words in pages for conf, *_box, w in words if conf >= 80 and bare(w)}


def unsure_words(words, known=()):
    """The words Tesseract read in the drawings, (x0, y0, x1, y1, word) in points: unsure ones (under
    60 of 100) that do not look like words — no three letters in a row and not read for sure
    elsewhere in the book, or signs words never hold. Its confidence alone will not do:
    "l'Histoire", read right, gets 27."""
    out = []
    k = 72 / OCR_DPI
    for conf, x, y, w, h, word in words:
        if 0 <= conf < 60 and (re.search(r"[{}|\\/~@*¥<>^_=#%$§©®]", word) or bare(word) not in known
                               and not re.search(r"[^\W\d_]{3}", re.sub(r"['’]", "", word))):
            out.append((x * k, y * k, (x + w) * k, (y + h) * k, word))
    return out


def unsure_in(seen, number, bbox):
    words = (getattr(seen, "unsure", None) or {}).get(number) or []
    return {w for x0, y0, x1, y1, w in words
            if bbox[0] - 2 <= (x0 + x1) / 2 <= bbox[2] + 2 and bbox[1] - 2 <= (y0 + y1) / 2 <= bbox[3] + 2}


def scrub(text, unsure, markup=True):
    """`text` without the unsure words; "" when they were most of it."""
    if not unsure:
        return text
    counts = [0, 0]             # kept, dropped

    def words(part):
        out = []
        for token in re.split(r"(\s+)", part):
            if token.strip() and html.unescape(token) in unsure:
                counts[1] += 1
                continue
            counts[0] += bool(token.strip())
            out.append(token)
        return "".join(out)

    parts = re.split(r"(<[^>]+>)", text) if markup else [text]
    cleaned = "".join(part if markup and part.startswith("<") else words(part) for part in parts)
    if counts[1]:
        real = re.findall(r"[^\W\d_]{2,}", plain(cleaned) if markup else cleaned)
        if counts[1] >= counts[0] or len(real) < 2:
            return ""
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
        cleaned = re.sub(r"(<(?:p|li|h\d)\b[^>]*>)\s+|\s+(</(?:p|li|h\d)>)", lambda m: m.group(1) or m.group(2), cleaned)
    return cleaned


# ------------------------------------------------------------------------------------------
# Marker's pages → a flow of pieces: ("h", level, xhtml, page), ("p", xhtml, class, page), ("img"
# or "eq", page, bbox, page box, kind, caption or text), ("note", xhtml), ("aside", xhtml, page)
# ------------------------------------------------------------------------------------------

def marker_pages(path):
    say(step="models")
    from marker.config.parser import ConfigParser
    from marker.converters.pdf import PdfConverter
    from marker.models import create_model_dict
    config = ConfigParser({"output_format": "json", "disable_ocr": True, "disable_tqdm": True})
    converter = PdfConverter(config=config.generate_config_dict(), artifact_dict=create_model_dict(),
                             renderer=config.get_renderer(), processor_list=config.get_processors())
    say(step="pages")
    return json.loads(converter(path).model_dump_json())["children"]     # model_dump() trips on the metadata


def heading_level(markup):
    m = re.match(r"\s*<h([1-6])", markup or "")
    return int(m.group(1)) if m else 2


def main_column(pages):
    """Where the paper's text starts and how wide its column is: the left edge that carries
    the most text over the whole paper. A narrow block wholly left of it sits in the margin
    (a journal's sidebar of citation, dates and licence)."""
    chars, widths_at = {}, {}
    for page in pages:
        for b in page.get("children") or []:
            if b["block_type"] == "Text":
                edge = round(b["bbox"][0] / 10)
                chars[edge] = chars.get(edge, 0) + len(plain(b.get("html") or ""))
                widths_at.setdefault(edge, []).append(b["bbox"][2] - b["bbox"][0])
    if not chars:
        return None, None
    edge = max(chars, key=chars.get)
    found = sorted(widths_at[edge])
    return edge * 10 - 5, found[len(found) // 2]


def margin_of(page, left, column):
    """The right edge of the page's margin, or None: a page with something as wide as a column
    starting left of the main one (the left column of a two-column page) has none."""
    if left is None:
        return None
    for b in page.get("children") or []:
        if b["block_type"] not in SKIP and b["bbox"][0] < left - 10 and b["bbox"][2] - b["bbox"][0] >= column * 0.6:
            return None
    return left + 2


def flow_of(pages, seen=None):
    """The pieces in reading order, page after page. The margin's text is an ("aside", xhtml, page).
    A paragraph is ("p", xhtml, "", page, at): `at` is "break" at the top of a page or a column,
    where a cut paragraph may go on, None elsewhere."""
    pieces = []
    left, column = main_column(pages)

    def from_layer(number, bbox):
        said = layer_text(seen.text_in(number, bbox)) if hasattr(seen, "text_in") else ""
        return scrub(said, unsure_in(seen, number, bbox), markup=False)

    for number, page in enumerate(pages):
        box = page["bbox"]
        margin = margin_of(page, left, column)
        above = None            # the top of the last paragraph of this page
        for block in page.get("children") or []:
            kind = block["block_type"]
            if kind in SKIP or kind == "TableOfContents":      # the reader has its own contents
                continue
            x0, y0, x1, y1 = block["bbox"]
            unsure = unsure_in(seen, number, block["bbox"])
            if unsure and kind not in FLOATS and kind not in GROUPS:      # Tesseract read a drawing
                had = plain(block.get("html") or "")
                for b in [block] + (block.get("children") or []):
                    b["html"] = scrub(b.get("html") or "", unsure)
                if had and not plain(block["html"]) and not any(plain(b.get("html") or "") for b in block.get("children") or []):
                    continue
            if margin is not None and x1 <= margin and x1 - x0 < column * 0.6:
                text = "" if kind in FLOATS or kind in GROUPS else inline(block.get("html") or "")
                if text:
                    pieces.append(("aside", text, number))
                continue
            if kind in GROUPS:
                parts = block.get("children") or []
                shapes = [b for b in parts if b["block_type"] not in ("Caption", "Footnote")]
                if shapes:
                    bbox = [min(b["bbox"][0] for b in shapes), min(b["bbox"][1] for b in shapes),
                            max(b["bbox"][2] for b in shapes), max(b["bbox"][3] for b in shapes)]
                    caption = " ".join(inline(b["html"]) for b in parts if b["block_type"] == "Caption")
                    pieces.append(("img", number, bbox, box, kind, caption))
                continue
            if kind in FLOATS:
                pieces.append(("img", number, block["bbox"], box, kind, ""))
            elif kind == "Equation":
                pieces.append(("eq", number, block["bbox"], box, kind, plain(inline(block["html"]))))
            elif kind == "SectionHeader":
                text = unmarked(inline(block["html"]))
                if not text and not plain(block.get("html") or ""):
                    said = from_layer(number, block["bbox"])
                    if not said[:1].islower():     # else the scraps of a line cut off by the page
                        text = html.escape(said, quote=False)
                if text:
                    pieces.append(("h", heading_level(block["html"]), text, number))
            elif kind == "Footnote":
                text = inline(block["html"])
                if text:
                    pieces.append(("note", text))
            elif kind == "Caption":
                text = inline(block["html"])
                if text:
                    pieces.append(("p", text, "caption", number))
            elif kind == "ListGroup":
                for b in block.get("children") or []:
                    if b["block_type"] != "ListItem":
                        continue
                    item = unmarked(inline(b["html"]))
                    raw = seen.text_in(number, b["bbox"]) if hasattr(seen, "text_in") else ""
                    raw = scrub(raw, unsure_in(seen, number, b["bbox"]), markup=False)
                    if layer_text(raw)[:1] in tuple("–—«“\""):
                        # lines of dialogue taken for a list (Marker ate the dash), one a line
                        for line in re.split(r"\r?\n(?=\s*[–—«“\"])", raw):
                            if layer_text(line):
                                pieces.append(("p", html.escape(layer_text(line), quote=False), "", number, None))
                    elif item:
                        pieces.append(("p", item, "item", number))
            elif kind == "Code":
                text = plain(inline(block["html"]))
                if text:
                    pieces.append(("p", "<code>%s</code>" % html.escape(text, quote=False), "code", number))
            else:                       # Text, TextInlineMath, ListItem, Reference, Handwriting…
                text = unmarked(inline(block["html"]))
                if not text and plain(block.get("html") or ""):
                    continue            # printer's marks only
                if not text:            # Marker lost it: the text layer may have it
                    raw = seen.text_in(number, block["bbox"]) if hasattr(seen, "text_in") else ""
                    said = scrub(layer_text(raw), unsure, markup=False)
                    if raw.strip() and not said:
                        continue
                    if said and not garbled(said):
                        text = html.escape(said, quote=False)
                if text and garbled(plain(text)):
                    pieces.append(("eq", number, block["bbox"], box, kind, plain(text)))
                elif text:
                    pieces.append(("p", text, "", number, "break" if above is None or y0 < above - 2 else None))
                    above = y0
                elif x1 - x0 > 20 and y1 - y0 > 6:     # text the text layer lost: never dropped
                    pieces.append(("eq", number, block["bbox"], box, kind, ""))
    return pieces


def continues(before, after):
    """A paragraph cut by the end of a page or a column: the first part does not end a
    sentence and the second starts in lower case — or the first stops on a bare word."""
    a, b = plain(before), plain(after)
    if not a or not b:
        return False
    if re.search(r"[a-z,]$", a) and len(a) > 40 and b[0].isalnum():     # "… in which σ denotes" + "ReLU [29] …"
        return True
    return b[0].islower() and (a.endswith("-") or not a.endswith(ENDS_SENTENCE))


def join(before, after):
    if plain(before).endswith("-") and before.endswith("-"):
        return before[:-1] + after
    return before + " " + after


def page_of(piece):
    return piece[1] if piece[0] in ("img", "eq") else piece[3] if piece[0] in ("p", "h") else None


def mend(pieces):
    """Joins the cut paragraphs; the figures and tables met in between, with their captions and
    the lines cut out next to them, follow the paragraph. A paragraph in lower case after an
    equation goes on with its sentence: the figures wait for it too."""
    out, waiting = [], []
    last = None                 # the index in `out` of the paragraph that may go on
    for piece in pieces:
        kind = piece[0]
        if kind == "img" or kind == "p" and piece[2] == "caption" \
                or kind == "eq" and not piece[5] and waiting and page_of(waiting[-1]) == piece[1]:
            waiting.append(piece)
            continue
        if kind in ("note", "aside"):
            out.append(piece)
            continue
        if kind == "p" and piece[2] == "" and last is not None:
            at = piece[4] if len(piece) > 4 else "break"
            if out[last][0] == "p" and at == "break" and continues(out[last][1], piece[1]):
                out[last] = ("p", join(out[last][1], piece[1]), "", out[last][3], out[last][4] if len(out[last]) > 4 else None)
                continue
            if out[last][0] == "eq" and plain(piece[1])[:1].islower():
                out.append(piece)
                last = len(out) - 1
                continue
        out.extend(waiting)
        waiting = []
        out.append(piece)
        last = len(out) - 1 if kind == "eq" or kind == "p" and piece[2] == "" else None
    out.extend(waiting)
    return out


# ------------------------------------------------------------------------------------------
# The book: a title page, a chapter per top section
# ------------------------------------------------------------------------------------------

def widths(pages):
    """The width of a column of text and the width the text takes on a page, in points."""
    columns, spans = [], []
    for page in pages:
        lefts, rights = [], []
        for block in page.get("children") or []:
            if block["block_type"] == "Text" and len(plain(block.get("html") or "")) > 150:
                x0, _y0, x1, _y1 = block["bbox"]
                columns.append(x1 - x0)
                lefts.append(x0)
                rights.append(x1)
        if lefts:
            spans.append(max(rights) - min(lefts))
    if not columns:
        return 0, 0
    columns.sort()
    spans.sort()
    return columns[len(columns) // 2], spans[len(spans) // 2]


def meta_text(text):
    """A field of the PDF's metadata; pdfium leaves some characters as "#_#x00FC;"."""
    return re.sub(r"#_#x([0-9A-Fa-f]+);", lambda m: chr(int(m.group(1), 16)), text or "").strip()


def squash(text):
    return re.sub(r"\W+", "", text or "").lower()


def good_title(text):
    t = meta_text(text)
    return t if 3 < len(t) < 300 and not re.search(r"\.(pdf|dvi|tex|docx?)$|^Microsoft Word|^untitled", t, re.I) else ""


NUMBERED = re.compile(r"^((?:\d+|[A-Z]|[IVX]+)(?:\.\d+)*)\.?\s+\S")
BACK_MATTER = re.compile(r"^(abstract|summary|references|bibliography|literature cited|acknowledge?ments?|appendi(x|ces)"
                         r"|supplementary|supporting information|conclusions?|discussion|résumé|bibliographie|remerciements"
                         r"|literatur|danksagung|zusammenfassung)\b", re.I)


def numbering(text):
    """How deep a numbered heading is: "3 Model" 0, "3.2.1 Scaled" 2; None if unnumbered."""
    m = NUMBERED.match(text)
    return m.group(1).count(".") if m else None


def chapter_depths(headings):
    """For each (Marker's level, text) heading, 1 when it opens a chapter, else 2–6. A paper
    that numbers its sections says it best: "2 Background" and "A. Proofs" are chapters, "2.1"
    one level down; an unnumbered heading ("Abstract", "References") is a chapter when Marker
    puts it no deeper than the numbered ones. Else the shallowest level Marker uses twice."""
    numbers = [numbering(t) for _l, t in headings]
    tops = [level for (level, _t), n in zip(headings, numbers) if n == 0]
    if len(tops) >= 3:
        first = numbers.index(0)
        out = []
        for i, ((level, text), n) in enumerate(zip(headings, numbers)):
            if n is not None:
                out.append(min(6, 1 + n))
            elif BACK_MATTER.match(text) or i < first and level <= max(tops):
                out.append(1)
            else:
                out.append(min(6, 1 + max(1, level - min(tops))))
        return out
    levels = [level for level, _t in headings]
    top = min(levels) if levels else 1
    if levels.count(top) < 2 and any(level > top for level in levels):
        top = min(level for level in levels if level > top)
    return [1 if level <= top or BACK_MATTER.match(text) else min(6, 1 + level - top) for level, text in headings]


CHAPTER_MARK = re.compile(r"^(?:[–—-]\s*)?(?:[IVXLC]+|\d{1,3})(?:\s*[–—-])?\.?$"
                          r"|^(?:chapitre|chapter|kapitel|cap[ií]tulo|capitolo|глава|partie|part|teil|livre|book)\s+\S+(?:\s+\S+){0,4}$", re.I)
# what bookmarks often leave out (LaTeX's \section*) and still opens a chapter
UNLISTED = re.compile(r"^(abstract|references|bibliography|acknowledge?ments?|appendi(x|ces)|résumé|bibliographie"
                      r"|remerciements|literatur(verzeichnis)?|danksagung|zusammenfassung)\b", re.I)
NUMBER_PREFIX = re.compile(r"^\W*(?:(?:chapitre|chapter|kapitel|cap[ií]tulo|capitolo|глава|part(?:ie)?|teil|livre|book)\s+)?"
                           r"(?:\d+|[IVXLC]+)\s*[:.–—-]\s*", re.I)
CONTENTS = re.compile(r"^(table des mati[eè]res|(table of )?contents|sommaire|inhalt(sverzeichnis)?|[íi]ndice|содержание|оглавление)$", re.I)


def prose(text, strict):
    """A heading of Marker's that is a line of the text: "Il répondit :", "« Orgeat ! »". With
    `strict` (the bookmarks say what the headings are) a heading ending a sentence is one too."""
    t = text.strip()
    if CHAPTER_MARK.match(t):
        return False
    if re.match(r"^[«“\"]|^[–—-]\s*\w", t) or re.search(r"[:;,]$", t):
        return True
    return bool(re.search(r"[.!?…»”]$", t)) and (strict or len(t.split()) >= 8)


def by_marks(pieces):
    """A book with no bookmarks: lines alone such as "– II –" or "Chapitre 3" open its chapters,
    when there are at least three of them."""
    marks = [i for i, p in enumerate(pieces) if p[0] == "p" and p[2] == "" and len(plain(p[1])) <= 60
             and CHAPTER_MARK.match(plain(p[1]))]
    if len(marks) < 3:
        return pieces
    top = min([p[1] for p in pieces if p[0] == "h"] or [1])
    for i in marks:
        pieces[i] = ("h", top, pieces[i][1], pieces[i][3])
    return pieces


def by_outline(pieces, outline, n_pages):
    """The PDF's bookmarks are the chapters: each goes on the line it names (else at the top of its
    page). Its upper levels open chapters, as many as make chapters of two pages or more on average;
    the rest are headings inside. Marker's other headings stay as subheadings, unless they read
    as a line of the text. Returns the pieces and the depth of each heading."""
    levels = sorted({level for level, _t, _p in outline})
    rank = {level: k for k, level in enumerate(levels)}
    files = 0
    for k in range(1, len(levels)):
        if sum(1 for level, _t, _p in outline if rank[level] <= k) > n_pages / 2:
            break
        files = k

    def depth_of(level):
        return 1 if rank[level] <= files else min(6, 1 + rank[level] - files)

    at_page = {}
    for i, p in enumerate(pieces):
        if p[0] == "h" or p[0] == "p" and p[2] == "":
            at_page.setdefault(page_of(p), []).append(i)
    named, before = {}, {}
    for level, title, page in outline:
        want = squash(title)
        core = squash(NUMBER_PREFIX.sub("", title))      # "3: Catalogs" is "CHAPTER THREE: Catalogs"
        best, score = None, 0.6
        for i in at_page.get(page, []) + at_page.get(page + 1, []):
            p = pieces[i]
            text = squash(plain(p[2] if p[0] == "h" else p[1]))
            if i in named or not text or len(text) > 2 * len(want) + 20:
                continue
            r = 1.0 if text == want else 0.9 if len(core) >= 4 and core != want and text.endswith(core) \
                else 0 if len(want) <= 6 else difflib.SequenceMatcher(None, want, text).ratio()
            if r > score:
                best, score = i, r
        if best is not None:
            named[best] = depth_of(level)
        else:
            first = [i for i, p in enumerate(pieces) if page_of(p) is not None and page_of(p) >= page][:1]
            before.setdefault(first[0] if first else len(pieces), []).append((depth_of(level), title, page))
    sub = min(6, max(depth_of(level) for level in levels) + 1)
    out, depth = [], []
    for i, p in enumerate(pieces + [None]):
        for d, title, page in before.get(i, []):
            out.append(("h", 1, html.escape(title, quote=False), page))
            depth.append(d)
        if p is None:
            break
        if i in named:
            out.append(("h", 1, p[2] if p[0] == "h" else p[1], page_of(p)))
            depth.append(named[i])
        elif p[0] == "h" and prose(plain(p[2]), True):
            out.append(("p", p[2], "", p[3], None))
        elif p[0] == "h":
            out.append(p)
            depth.append(1 if UNLISTED.match(plain(p[2])) else sub)
        else:
            out.append(p)
    return out, depth


def running_heads(pieces, n_pages):
    """A short line at the top or the foot of many pages is a running head Marker took for text:
    only its first time stays (often the chapter's own heading)."""
    by_page = {}
    for i, p in enumerate(pieces):
        if p[0] in ("h", "p"):
            by_page.setdefault(page_of(p), []).append(i)

    def key(p):
        text = plain(p[2] if p[0] == "h" else p[1])
        return re.sub(r"\d+", "", squash(text)) if len(text) <= 80 else ""

    ends = sorted({i for found in by_page.values() for i in (found[0], found[-1])})
    pages_of = {}
    for i in ends:
        if key(pieces[i]):
            pages_of.setdefault(key(pieces[i]), set()).add(page_of(pieces[i]))
    heads = {k for k, found in pages_of.items() if len(found) >= max(3, n_pages // 10)}
    seen, drop = set(), set()
    for i in ends:
        k = key(pieces[i])
        if k in heads:
            if k in seen:
                drop.add(i)
            seen.add(k)
    return [p for i, p in enumerate(pieces) if i not in drop]


def build(pdf_path, original=None, unsure=None):
    """The book of the PDF; `original` is the file it was read from when this is Tesseract's copy,
    `unsure` the words Tesseract was unsure of, by page."""
    pages_seen = Pages(pdf_path)
    pages_seen.unsure = unsure
    meta = (Pages(original) if original else pages_seen).metadata()
    pages = marker_pages(pdf_path)
    say(step="book")
    texty = sum(1 for page in pages if len(" ".join(plain(b.get("html") or "") for b in page.get("children") or [])) > 200)
    stem = os.path.splitext(os.path.basename(original or pdf_path))[0].replace("_", " ")
    if texty * 2 < len(pages):
        return scanned(pages_seen, good_title(meta.get("Title")) or stem, meta)
    column, span = widths(pages)
    pieces = running_heads(mend(flow_of(pages, pages_seen)), len(pages))

    # The title: the heading of the first page that is the PDF's own title, else its highest
    # heading, else the PDF's title, else the file's name. A heading before it on that page
    # (a journal's "RESEARCH ARTICLE") is small print.
    first = [i for i, p in enumerate(pieces) if p[0] == "h" and p[3] == 0]
    known = squash(good_title(meta.get("Title")))
    title_at = next((i for i in first if known and (known in squash(plain(pieces[i][2])) or squash(plain(pieces[i][2])) in known)), None)
    if title_at is None and first:
        title_at = min(first, key=lambda i: pieces[i][1])
    title = good_title(plain(pieces[title_at][2])) if title_at is not None else ""
    title = title or good_title(meta.get("Title")) or stem
    if title_at is not None:
        for i in first:
            if i < title_at:
                pieces[i] = ("p", pieces[i][2], "author", 0)
        pieces.pop(title_at)
    outline = [o for o in (pages_seen.outline() if hasattr(pages_seen, "outline") else []) if squash(o[1])]
    if len(outline) >= 2:
        pieces, depth = by_outline(pieces, outline, len(pages))
    else:
        pieces = [("p", p[2], "", p[3], None) if p[0] == "h" and prose(plain(p[2]), False) else p for p in by_marks(pieces)]
        depth = chapter_depths([(p[1], plain(p[2])) for p in pieces if p[0] == "h"])

    images = []

    def picture(piece):
        kind, number, bbox, box, block_kind, text = piece
        caption = text if kind == "img" else ""      # an equation's text is only its alt
        w = bbox[2] - bbox[0]
        target = column if column and w <= column * 1.15 else max(w, span or w)
        cut = pages_seen.cut(number, bbox, box, target)
        if not cut:
            return ""
        data, ext = cut
        name = "images/%03d.%s" % (len(images) + 1, ext)
        images.append((name, data))
        alt = html.escape(plain(text) or block_kind.lower(), quote=True)
        out = '<div class="%s"><img src="%s" alt="%s"/></div>' % ("equation" if kind == "eq" else "figure", name, alt)
        if caption:
            out += '\n<p class="caption">%s</p>' % caption
        return out

    chapters = [[title, ['<h1 class="title">%s</h1>' % html.escape(title, quote=False)], []]]
    front = True                # the authors and the like, before the first section
    headings = iter(depth)
    for piece in pieces:
        kind = piece[0]
        if kind == "h":
            front = False
            level = next(headings)
            if level == 1:
                chapters.append([plain(piece[2]), [], []])
            chapters[-1][1].append("<h%d>%s</h%d>" % (level, piece[2], level))
        elif kind == "aside" and piece[2] <= 1:     # the sidebar of the first pages: at the end of the title page
            notes = chapters[0][2]
            if notes and continues(plain(notes[-1]), piece[1]):
                notes[-1] = notes[-1][:-len("</p>")] + " " + piece[1] + "</p>"
            else:
                notes.append('<p class="footnote">%s</p>' % piece[1])
        elif kind in ("note", "aside"):
            chapters[-1][2].append('<p class="footnote">%s</p>' % piece[1])
        elif kind in ("img", "eq"):
            chapters[-1][1].append(picture(piece))
        else:
            cls = "author" if front and not piece[2] else piece[2]
            chapters[-1][1].append('<p class="%s">%s</p>' % (cls, piece[1]) if cls else "<p>%s</p>" % piece[1])
    chapters = [c for k, c in enumerate(chapters) if k == 0 or not CONTENTS.match(plain(c[0]))]     # the reader has its own
    return title, meta_text(meta.get("Author")), [(t, body + notes) for t, body, notes in chapters if body or notes], images


def scanned(pages_seen, title, meta):
    """No text to read: the pages as pictures, one chapter."""
    images, body = [], ['<h1 class="title">%s</h1>' % html.escape(title, quote=False)]
    for i in range(len(pages_seen)):
        say(step="book", page=i + 1, of=len(pages_seen))
        image = pages_seen.page(i)
        data, ext = encode(image.resize((image.width // 2, image.height // 2)))
        name = "images/page-%03d.%s" % (i + 1, ext)
        images.append((name, data))
        body.append('<div class="figure"><img src="%s" alt="page %d"/></div>' % (name, i + 1))
    return title, meta_text(meta.get("Author")), [(title, body)], images


# ------------------------------------------------------------------------------------------
# EPUB 3, with an NCX for the older readers
# ------------------------------------------------------------------------------------------

CSS = """body { font-family: serif; line-height: 1.45; margin: 0 4%; }
h1 { font-size: 1.4em; margin: 1.2em 0 0.6em; }
h1.title { font-size: 1.6em; text-align: center; }
h2 { font-size: 1.2em; } h3, h4, h5, h6 { font-size: 1.05em; }
p { margin: 0; text-indent: 1.2em; text-align: justify; }
h1 + p, h2 + p, h3 + p, h4 + p, div + p, p.caption + p { text-indent: 0; }
p.author { text-align: center; text-indent: 0; font-size: 0.9em; margin: 0.2em 0; }
p.caption { font-size: 0.85em; text-indent: 0; margin: 0.3em 0 1em; }
p.footnote { font-size: 0.8em; text-indent: 0; margin-top: 0.4em; }
p.item { text-indent: -1em; margin-left: 1em; }
p.code { font-family: monospace; text-indent: 0; white-space: pre-wrap; }
div.figure, div.equation { text-align: center; margin: 0.8em 0; }
div.figure img, div.equation img { max-width: 100%; }
"""

XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>%s</title><link rel="stylesheet" type="text/css" href="style.css"/></head>
<body>
%s
</body>
</html>
"""


def write_epub(path, title, authors, chapters, images, language="en"):
    esc = lambda s: html.escape(s, quote=True)
    book_id = "urn:uuid:%s" % uuid.uuid4()
    files = [("ch%03d.xhtml" % (i + 1), t, body) for i, (t, body) in enumerate(chapters)]
    manifest = ['<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>',
                '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>',
                '<item id="css" href="style.css" media-type="text/css"/>']
    manifest += ['<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (i, f) for i, (f, _t, _b) in enumerate(files)]
    manifest += ['<item id="i%d" href="%s" media-type="%s"/>' % (i, n, "image/png" if n.endswith("png") else "image/jpeg")
                 for i, (n, _d) in enumerate(images)]
    spine = ['<itemref idref="c%d"/>' % i for i in range(len(files))]
    creator = '<dc:creator>%s</dc:creator>' % esc(authors) if authors else ""
    opf = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:identifier id="id">%s</dc:identifier><dc:title>%s</dc:title>%s<dc:language>%s</dc:language>
<meta property="dcterms:modified">2000-01-01T00:00:00Z</meta>
</metadata>
<manifest>
%s
</manifest>
<spine toc="ncx">
%s
</spine>
</package>
""" % (book_id, esc(title), creator, esc(language), "\n".join(manifest), "\n".join(spine))
    nav = XHTML % (esc(title), '<nav epub:type="toc"><ol>\n%s\n</ol></nav>' % "\n".join(
        '<li><a href="%s">%s</a></li>' % (f, esc(t)) for f, t, _b in files))
    ncx = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<head><meta name="dtb:uid" content="%s"/></head><docTitle><text>%s</text></docTitle>
<navMap>
%s
</navMap>
</ncx>
""" % (book_id, esc(title), "\n".join(
        '<navPoint id="n%d" playOrder="%d"><navLabel><text>%s</text></navLabel><content src="%s"/></navPoint>'
        % (i, i + 1, esc(t), f) for i, (f, t, _b) in enumerate(files)))
    container = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/nav.xhtml", nav, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.ncx", ncx, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, zipfile.ZIP_DEFLATED)
        for f, t, body in files:
            z.writestr("OEBPS/" + f, XHTML % (esc(t), "\n".join(b for b in body if b)), zipfile.ZIP_DEFLATED)
        for name, data in images:
            z.writestr("OEBPS/" + name, data, zipfile.ZIP_STORED)
    os.replace(tmp, path)


def convert(pdf_path, epub_path):
    with tempfile.TemporaryDirectory(prefix="paper2epub-") as work:
        scan = needs_ocr(Pages(pdf_path))
        lang = None
        if scan and tesseract() and ocr_languages():
            read = os.path.join(work, "read.pdf")
            lang, unsure = ocr_pdf(pdf_path, read, work)
            title, authors, chapters, images = build(read, pdf_path, unsure)
        else:
            if scan:
                say(notice="no-ocr")
            title, authors, chapters, images = build(pdf_path)
    write_epub(epub_path, title, authors, chapters, images, ISO.get(lang, lang or "en"))
    return title


def stop_servers():
    """Marker starts its models as servers meant to outlive it (about 3 GB of memory, kept until
    the session ends): the ones this environment started are stopped once the paper is done."""
    folder = os.path.expanduser("~/.cache/datalab/surya")
    try:
        names = [n for n in os.listdir(folder) if n.endswith("_server.json")]
    except OSError:
        return
    for name in names:
        try:
            with open(os.path.join(folder, name)) as fh:
                pid = int(json.load(fh)["pid"])
            with open("/proc/%d/cmdline" % pid, "rb") as fh:
                ours = fh.read().split(b"\0")[0] == os.fsencode(sys.executable)
        except (OSError, ValueError, KeyError, TypeError):
            continue
        if ours:
            try:
                os.kill(pid, signal.SIGTERM)
                os.remove(os.path.join(folder, name))
            except OSError:
                pass


def main(argv):
    global PROGRESS
    args = [a for a in argv if a != "--progress"]
    PROGRESS = len(args) != len(argv)
    if len(args) != 2:
        print(__doc__.strip().split("\n\n")[1], file=sys.stderr)
        return 2
    try:
        title = convert(args[0], args[1])
    except Exception as exc:
        say(error="%s: %s" % (type(exc).__name__, exc))
        if not PROGRESS:
            raise
        return 1
    finally:
        stop_servers()
    say(done=title)
    if not PROGRESS:
        print(args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
