#!/usr/bin/env python3
"""An issue of The Economist or of The New Yorker in PDF, as an EPUB made like a magazine:
one chapter per article, each with its section, its title, its standfirst and its byline,
in the order of the printed issue.

    magazine2epub.py issue.pdf issue.epub [--progress]
    magazine2epub.py --which issue.pdf          # prints "economist", "newyorker" or nothing

The PDF's own text is read glyph by glyph (pypdfium2): every line knows its font, its size and
its place, so each magazine's typography says what a line is — body text, headline, rubric,
standfirst, byline, caption, chart, page furniture, advertisement. A page is read in the order a
reader's eye goes: a band across the page, then its columns from left to right (XY cut).
Articles run on from page to page until the next headline. Paragraphs are joined again across
columns and pages; a word cut at the end of a line is mended, keeping the hyphen only where the
word carries one elsewhere in the issue (or where both halves are words and the whole is not).

Photographs, cartoons and charts are cut out of the rendered page, with their captions. The
advertisements, the table of contents, the masthead and the puzzles are left out. The cover is
the first page.

The EPUB is the one the newspapers pipeline and Reader's Books' magazine view expect: the nav
lists every article with `toc-cat` (section), `toc-title` and `toc-author`; every chapter starts
with `p.category` and `h1`, then `p.lead` (standfirst), `p.author` (byline).

With --progress, one JSON object per line on stdout: {"step": "page", "page": n, "of": m}, then
{"done": title} or {"error": message}. Needs pypdfium2 and Pillow.
"""

import ctypes
import html
import io
import json
import os
import re
import sys
import unicodedata
import uuid
import zipfile
from collections import Counter, defaultdict

try:
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
except ImportError:             # the rules below can still be tried without it
    pdfium = raw = None

PROGRESS = False
RENDER = 2.5                # pixels per point for the pictures: 180 dpi
MIN_PICTURE = 40            # points: smaller pictures are ornaments


def say(**what):
    if PROGRESS:
        print(json.dumps(what, ensure_ascii=False), flush=True)


# ------------------------------------------------------------------------------------------
# Glyphs, lines and the page's pictures
# ------------------------------------------------------------------------------------------

class Char:
    __slots__ = ("c", "x0", "top", "x1", "bottom", "base", "size", "font", "accent")

    def __init__(self, c, x0, top, x1, bottom, base, size, font, accent=False):
        self.c, self.x0, self.top, self.x1, self.bottom, self.base, self.size, self.font = \
            c, x0, top, x1, bottom, base, size, font
        self.accent = accent            # set in a colour, not in black or grey


def _font_name(obj, cache):
    key = ctypes.cast(obj, ctypes.c_void_p).value
    name = cache.get(key)
    if name is None:
        font = raw.FPDFTextObj_GetFont(obj)
        buf = ctypes.create_string_buffer(256)
        raw.FPDFFont_GetBaseFontName(font, buf, 256)
        name = cache[key] = buf.value.decode("latin-1").split("+", 1)[-1]
    return name


def page_chars(page):
    """Every glyph of the page in the order of its content stream, with the spaces PDFium puts
    between words; a hyphen PDFium found at the end of a line is "\\x02"."""
    tp = page.get_textpage()
    t = tp.raw
    height = page.get_height()
    l, r, b, top = ctypes.c_double(), ctypes.c_double(), ctypes.c_double(), ctypes.c_double()
    ox, oy = ctypes.c_double(), ctypes.c_double()
    m = raw.FS_MATRIX()
    loose = raw.FS_RECTF()
    cr, cg, cb, ca = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()
    cache, out = {}, []
    for i in range(raw.FPDFText_CountChars(t)):
        u = raw.FPDFText_GetUnicode(t, i)
        if u in (0, 10, 13, 0xFFFE) or (u < 32 and u != 2) or 0xD800 <= u < 0xE000:
            continue
        if raw.FPDFText_IsGenerated(t, i):
            if u == 32 and out:
                p = out[-1]
                out.append(Char(" ", p.x1, p.top, p.x1, p.bottom, p.base, p.size, p.font))
            continue
        raw.FPDFText_GetCharBox(t, i, l, r, b, top)
        raw.FPDFText_GetLooseCharBox(t, i, loose)      # with the glyph's advance: words touch letters
        raw.FPDFText_GetCharOrigin(t, i, ox, oy)
        raw.FPDFText_GetMatrix(t, i, m)
        size = raw.FPDFText_GetFontSize(t, i) * (m.c * m.c + m.d * m.d) ** 0.5
        font = _font_name(raw.FPDFText_GetTextObject(t, i), cache)
        x0, x1 = (loose.left, loose.right) if loose.right > loose.left else (l.value, r.value)
        accent = False
        if raw.FPDFText_GetFillColor(t, i, cr, cg, cb, ca):
            accent = max(cr.value, cg.value, cb.value) - min(cr.value, cg.value, cb.value) > 90
        out.append(Char(chr(u), x0, height - top.value, x1, height - b.value,
                        height - oy.value, round(size, 2), font, accent))
    tp.close()
    return out


class Line:
    def __init__(self, chars):
        self.chars = chars
        ink = [c for c in chars if not c.c.isspace()]
        self.x0 = min(c.x0 for c in ink)
        self.x1 = max(c.x1 for c in ink)
        self.top = min(c.top for c in ink)
        self.bottom = max(c.bottom for c in ink)
        self.base = Counter(round(c.base) for c in ink).most_common(1)[0][0]
        self.font, self.size = Counter((c.font, c.size) for c in ink).most_common(1)[0][0]
        self.spans = []             # (text, font, size): runs of one font, spaces put back
        prev = before = None
        for c in chars:
            ch = c.c
            if ch == " ":
                if self.spans and not self.spans[-1][0].endswith(" "):
                    self._add(" ", prev.font if prev else c.font, c.size)
                continue
            gap = c.x0 - prev.x1 if prev is not None else 0
            after_stop = prev is not None and prev.c in ",;:!?.)”" and not (prev.c in ".," and ch.isdigit())
            sentence = after_stop and prev.c in ".!?" and before is not None and before.c.islower() and (ch.isupper() or ch in "“‘")
            if prev is not None and (gap > 0.12 * c.size or (after_stop and gap > 0.05 * c.size) or (sentence and gap > -0.05 * c.size)) \
                    and self.spans and not self.spans[-1][0].endswith(" "):
                self._add(" ", prev.font, prev.size)
            self._add(ch, c.font, c.size)
            before, prev = prev, c
        self.text = "".join(s[0] for s in self.spans).strip()
        self.accent = sum(1 for c in ink if c.accent) > 0.8 * len(ink)
        self.role = None

    def _add(self, ch, font, size):
        if self.spans and self.spans[-1][1] == font and self.spans[-1][2] == size:
            self.spans[-1][0] += ch
        else:
            self.spans.append([ch, font, size])

    @property
    def plain(self):
        return self.text.replace("\x02", "-")

    def __repr__(self):
        return "<%s %.0f,%.0f %s %.1f %r>" % (self.role, self.x0, self.base, self.font, self.size, self.text[:40])


def lines_of(chars):
    """Glyphs that follow each other on one baseline are a line."""
    groups, cur = [], []
    for c in chars:
        if cur:
            last = cur[-1]
            size = max(c.size, last.size)
            if not (abs(c.base - last.base) < 0.35 * size and last.x0 - 0.3 * size < c.x0 < last.x1 + 1.1 * size):
                groups.append(cur)
                cur = []
        if not cur and c.c == " ":
            continue
        cur.append(c)
    if cur:
        groups.append(cur)
    out = []
    for g in groups:
        while g and g[-1].c == " ":
            g.pop()
        if g and any(not c.c.isspace() for c in g):
            out.append(Line(g))
    return out


def _bounds(obj):
    l, b, r, t = ctypes.c_float(), ctypes.c_float(), ctypes.c_float(), ctypes.c_float()
    if not raw.FPDFPageObj_GetBounds(obj, l, b, r, t):
        return None
    return l.value, b.value, r.value, t.value


def page_objects(page):
    """The page's raster pictures and vector paths, as boxes (x0, top, x1, bottom), form
    XObjects opened."""
    height, width = page.get_height(), page.get_width()
    images, paths, panels = [], [], []
    fill, stroke = ctypes.c_int(), ctypes.c_int()
    r, g, b_, a = ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint(), ctypes.c_uint()

    def walk(count, get):
        for i in range(count):
            obj = get(i)
            kind = raw.FPDFPageObj_GetType(obj)
            if kind == raw.FPDF_PAGEOBJ_FORM:
                walk(raw.FPDFFormObj_CountObjects(obj), lambda j, o=obj: raw.FPDFFormObj_GetObject(o, j))
                continue
            if kind not in (raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_PATH, raw.FPDF_PAGEOBJ_SHADING):
                continue
            box = _bounds(obj)
            if not box:
                continue
            l, b, r, t = box
            l, r = max(l, 0), min(r, width)
            t, b = min(t, height), max(b, 0)
            if r - l <= 0.5 and t - b <= 0.5:
                continue
            box = (l, height - t, r, height - b)
            (images if kind == raw.FPDF_PAGEOBJ_IMAGE else paths).append(box)
            if kind == raw.FPDF_PAGEOBJ_PATH and 80 < r - l < 0.9 * width and 40 < t - b < 0.9 * height:
                # a tinted panel: a box set apart from the text
                if raw.FPDFPath_GetDrawMode(obj, fill, stroke) and fill.value and \
                        raw.FPDFPageObj_GetFillColor(obj, r_, g_, b2, a_) and a_.value > 0 and \
                        min(r_.value, g_.value, b2.value) < 248 and max(r_.value, g_.value, b2.value) > 150:
                    panels.append(box)

    r_, g_, b2, a_ = r, g, b_, a
    walk(raw.FPDFPage_CountObjects(page.raw), lambda i: raw.FPDFPage_GetObject(page.raw, i))
    return images, paths, panels


# ------------------------------------------------------------------------------------------
# What each magazine's lines are
# ------------------------------------------------------------------------------------------
# Roles: body, sub (a heading inside the text), drop (a drop capital), head (headline), rubric
# (the line above it), stand (standfirst), byline, dateline, section (a section's opening
# title), caption, note (small print kept, as a book's details), chart (text of a chart: drawn
# with it), furniture (running heads and folios), skip.

HEAD_ROLES = ("rubric", "head", "stand", "byline", "dateline")


def _is(font, *parts):
    return all(p in font for p in parts)


class Economist:
    key = "economist"
    name = "The Economist"
    skip_sections = ("Contents",)

    @staticmethod
    def house(font):
        return font.startswith(("Economist", "SundayClarendon"))     # Clarendon: the features of 1843

    @staticmethod
    def recognise(fonts, first_text):
        n = sum(k for f, k in fonts.items() if f.startswith("EconomistSerif"))
        return n > 0.5 * max(1, sum(fonts.values()))

    @staticmethod
    def issue_date(pages_text):
        for t in pages_text:
            m = re.search(r"The Economist\s+((January|February|March|April|May|June|July|August|September|October|"
                          r"November|December)\s+\d{1,2}(st|nd|rd|th)\s+\d{4})", t)
            if m:
                return m.group(1)
        return None

    def role(self, l, page_h):
        f, s, t = l.font, l.size, l.text
        if l.bottom < 38 or l.top > page_h - 24:
            return "furniture"
        if t in ("▸", "⏩", "■", "▸"):
            return "skip"
        if not self.house(f):
            return "foreign"
        if f.startswith("SundayClarendon"):
            if s >= 18 and len(t) <= 2 and t[-1:].isalpha():
                return "drop"
            return "head" if s >= 18 else "skip"        # the pull quotes are said again in the text
        if f.startswith("EconomistSerif"):
            if s >= 15:
                if len(t) <= 2 and t[-1:].isalpha() and (len(t) == 1 or not t[0].isalnum()):
                    return "drop"
                if "SC" in f:
                    return "rubric"         # a column's name: LEXINGTON
                return "head"
            if s >= 8.5:
                if "Italic" in f and s >= 9.8:
                    return "stand?"
                if "SemiBold" in f or "Bold" in f or "Medium" in f:
                    return "bold?"
                return "body"
            return "chart"
        # the sans faces
        if s >= 16 and l.top < 95:
            return "section"
        if s >= 9.4 and "SemiBold" in f and "OSF" not in f:
            return "rubric?"
        if _is(f, "Sans-SemiBold") and 8.8 <= s <= 9.2:
            return "rubric?"
        if _is(f, "Sans-Medium") and s <= 5.5 and t.isupper():
            return "dateline"
        if _is(f, "OSF", "Italic") and s >= 8.5:
            return "note"
        return "chart"

    def section_head(self, box):
        return False

    def contents_page(self, lines):
        return False

    def contents(self, lines):
        return []

    def section_of_header(self, lines):
        for l in lines:
            if l.role == "furniture" and l.top < 40:
                bold = "".join(s[0] for s in l.spans if "SemiBold" in s[1]).strip()
                bold = re.sub(r"^\d+\s*|\s*\d+$", "", bold).strip()
                bold = re.sub(r"^The Economist\b\s*", "", bold).strip()
                if bold and not bold.isdigit():
                    return bold
        return None

    def section_title(self, text, spans=()):
        fonts = [s[1] for s in spans if s[0].strip()]
        if len(set(fonts)) > 1:
            first = spans[0][1]
            head = "".join(s[0] for s in spans if s[1] == first).strip()
            if text.startswith(head) and len(head) < len(text):
                return head, text[len(head):].strip()
        m = re.match(r"(The world this week)\s+(.+)", text)
        if m:
            return m.group(1), m.group(2)
        return text, None

    def settle(self, a):
        """The Economist's own kinds of page: letters, guest columns, the obituary."""
        rubric = " ".join(a.rubric).strip()
        title = " ".join(a.title).strip()
        if title.startswith("Letters "):
            a.category = "Letters"
            rest = title[len("Letters "):]
            a.title = [rest[:1].upper() + rest[1:]]
        elif rubric.upper() == "BY INVITATION":
            a.category = "By Invitation"
            a.rubric = []
            if a.stand:
                a.byline, a.title, a.stand = a.title, a.stand[:1], a.stand[1:]
        elif rubric.upper() == "OBITUARY":
            a.category, a.rubric = "Obituary", []


class NewYorker:
    key = "newyorker"
    name = "The New Yorker"
    skip_sections = ()
    critics = {"BOOKS", "BRIEFLY NOTED", "THE THEATRE", "THE ART WORLD", "MUSICAL EVENTS", "THE CURRENT CINEMA",
               "POP MUSIC", "ON TELEVISION", "DANCING", "A CRITIC AT LARGE", "PODCAST DEPT.", "THE SKY LINE",
               "TABLES FOR TWO", "ON AND OFF THE AVENUE", "THE BOOKSHELF"}
    sections = {"THE TALK OF THE TOWN": "The Talk of the Town", "GOINGS ON": "Goings On",
                "THE CRITICS": "The Critics"}

    @staticmethod
    def house(font):
        return font.startswith(("TNY", "WilliamsCaslon"))

    @staticmethod
    def recognise(fonts, first_text):
        n = sum(k for f, k in fonts.items() if f.startswith("TNY"))
        return n > 0.5 * max(1, sum(fonts.values()))

    @staticmethod
    def issue_date(pages_text):
        for t in pages_text:
            m = re.search(r"THE NEW YORKER,\s+([A-Z]+\s+\d{1,2},\s+\d{4})", t)
            if m:
                return m.group(1).title()
        return None

    def role(self, l, page_h):
        f, s, t = l.font, l.size, l.text
        if l.top > page_h - 22 or l.bottom < 22:
            return "furniture"
        if not self.house(f):
            return "foreign"
        if "YoshiRule" in f or t in ("WINTER PREVIEW",):
            return "skip"       # the season's running title of Goings On
        if f.startswith("TNYIrvinPro-Titling") and s >= 16:
            return "head"
        if f.startswith("TNYIrvinEM"):
            if s >= 10.3 and not re.match(r"BY\s", t):
                return "sub"
            if s >= 9.5:
                return "byline" if re.match(r"BY\s", t) else "rubric?"
            return "skip"
        if f.startswith("TNYAdobeCaslonPro"):
            if s >= 18 and len(t) <= 2 and t[-1:].isalpha() and (len(t) == 1 or not t[0].isalnum()):
                return "drop"
            if s >= 13 and not re.sub(r"[•\s]", "", t):
                return "break"          # the bullets between the parts of a long piece
            if s >= 15:
                return "head"
            if "Italic" in f and s >= 10.9:
                if re.match(r"^[—–]\s*\S", t) and len(t) < 45:
                    return "sig"
                return "stand?"
            if 10.8 <= s <= 11.2:
                return "verse?"
            if 10 <= s <= 11.2:
                return "body"
            return "chart"
        if f.startswith("WilliamsCaslonText"):
            return "body"
        if f.startswith("TNYNeutraface"):
            if "Demi" in f and 9.5 <= s <= 10.5:
                return "body"           # run-in names in the listings of Goings On
            if "Bold" in f and s >= 8.5:
                return "sub"
            return "skip"               # photograph credits, the vertical ILLUSTRATION
        return "skip"

    def section_head(self, box):
        return " ".join(l.plain for l in box.lines).strip() in self.sections

    def contents(self, lines):
        """The pieces the table of contents lists: department, author, page, title."""
        out = []
        depts = [l for l in lines if l.font.startswith("TNYIrvinEM") and 7 <= l.size <= 8.5]
        for l in lines:
            m = re.match(r"^(.*?)\s+(\d{1,3})\s+(\S.+)$", l.plain)
            if not m or not l.font.startswith("TNYAdobeCaslon"):
                continue
            above = [d for d in depts if d.bottom <= l.top + 1 and d.x0 < l.x1]
            dept = max(above, key=lambda d: d.bottom).plain if above else None
            if dept and re.match(r"^\d+\s", dept):
                dept = re.sub(r"^\d+\s+", "", dept)
            out.append({"author": m.group(1).strip(), "folio": int(m.group(2)),
                        "title": m.group(3).strip().strip("“”\"").strip(), "dept": dept})
        return out

    def contents_page(self, lines):
        """The table of contents: departments in small capitals, a page number by each piece."""
        small = sum(1 for l in lines if l.font.startswith("TNYIrvinEM") and 7 <= l.size <= 8.5)
        return small >= 6

    def section_of_header(self, lines):
        return None

    def section_title(self, text, spans=()):
        return self.sections.get(text, smart_title(text)), None

    def settle(self, a):
        dept = smart_title(" ".join(a.rubric)) if a.rubric else None
        if dept and re.search(r"puzzles|crossword", dept, re.I) or " ".join(a.title).upper().endswith("CROSSWORD"):
            a.items = []                # the crossword: nothing to read
            return
        if a.category == "The Critics" and not dept and " ".join(a.title).upper() in self.critics:
            return
        if a.category == "The Critics" and (not dept or dept.upper() not in self.critics):
            a.category = None
        if a.category in ("The Talk of the Town", "Goings On", "The Critics"):
            return
        if a.category == "Poems":
            return
        a.category, a.rubric = dept or "The New Yorker", []


PROFILES = (Economist(), NewYorker())


def which(pdf_path, doc=None):
    """The magazine's profile, recognised by its typefaces on the first pages (and by its name
    in the text), or None."""
    own = doc is None
    doc = doc or pdfium.PdfDocument(pdf_path)
    try:
        fonts, text = Counter(), []
        for p in range(min(len(doc), 24)):
            chars = page_chars(doc[p])
            for c in chars:
                if not c.c.isspace():
                    fonts[c.font] += 1
            text.append("".join(c.c for c in chars))
        joined = " ".join(text)
        for prof in PROFILES:
            if prof.recognise(fonts, joined) and prof.name.lower().replace("the ", "") in joined.lower():
                return prof
        return None
    finally:
        if own:
            doc.close()


# ------------------------------------------------------------------------------------------
# A page: roles settled, pictures found, blocks in reading order
# ------------------------------------------------------------------------------------------

def _overlap(a0, a1, b0, b1):
    return min(a1, b1) - max(a0, b0)


class Box:
    """A block of the page: lines of one role, or a picture."""

    def __init__(self, kind, x0, top, x1, bottom, lines=None, caption=None):
        self.kind, self.x0, self.top, self.x1, self.bottom = kind, x0, top, x1, bottom
        self.lines = lines or []
        self.caption = caption
        self.page = None
        self.image = None

    @classmethod
    def of(cls, kind, lines):
        return cls(kind, min(l.x0 for l in lines), min(l.top for l in lines),
                   max(l.x1 for l in lines), max(l.bottom for l in lines), lines)

    def __repr__(self):
        return "<%s %.0f-%.0f x %.0f-%.0f %s>" % (self.kind, self.x0, self.x1, self.top, self.bottom,
                                                 (self.lines[0].text[:30] if self.lines else ""))


def settle_roles(prof, lines, page_h):
    for l in lines:
        l.role = prof.role(l, page_h)
    body = [l for l in lines if l.role == "body"]
    body_size = Counter(l.size for l in body).most_common(1)[0][0] if body else 9

    def below(l, roles, gap):
        """The nearest line under `l`, in its column, if within `gap` and of these roles."""
        best = None
        for m in lines:
            if m is l or m.top < l.bottom - 1 or _overlap(l.x0, l.x1, m.x0, m.x1) <= 0:
                continue
            if best is None or m.top < best.top:
                best = m
        return best if best is not None and best.top - l.bottom <= gap and best.role in roles else None

    def below_any(l, gap):
        best = None
        for m in lines:
            if m is l or m.top < l.bottom - 1 or _overlap(l.x0, l.x1, m.x0, m.x1) <= 0:
                continue
            if best is None or m.top < best.top:
                best = m
        return best if best is not None and best.top - l.bottom <= gap else None

    def above(l, gap):
        best = None
        for m in lines:
            if m is l or m.bottom > l.top + 1 or _overlap(l.x0, l.x1, m.x0, m.x1) <= 0:
                continue
            if best is None or m.bottom > best.bottom:
                best = m
        return best if best is not None and l.top - best.bottom <= gap else None

    # verse: a poem's title in the department face, its lines one size above the text
    for l in lines:
        if l.role == "rubric?" and below(l, ("verse?", "stand?"), 30) is not None:
            l.role = "poemtitle"
    for _ in range(3):
        for l in lines:
            if l.role in ("verse?", "stand?", "sig"):
                prev = above(l, 30)
                if prev is not None and prev.role in ("poemtitle", "verse") and abs(prev.x0 - l.x0) < 60:
                    l.role = "versesig" if l.role == "sig" else "verse"
    for l in lines:
        if l.role == "verse?":
            l.role = "verse"
    # a rubric is a line just above a headline (or above another rubric line that is)
    for _ in range(2):
        for l in lines:
            if l.role == "rubric?" and below(l, ("head", "rubric", "rubric?", "drop"), 40):
                nxt = below(l, ("head", "rubric", "rubric?", "drop"), 40)
                if nxt.role in ("head", "rubric") or (nxt.role == "rubric?" and below(nxt, ("head",), 40)):
                    l.role = "rubric"
    for l in lines:
        if l.role == "rubric?":
            nxt = below(l, ("body", "drop", "stand?", "byline", "bold?"), 30)
            if isinstance(prof, NewYorker) and nxt is not None and nxt.role != "byline":
                prev = above(l, 60)
                l.role = "head" if prev is not None and prev.role == "rubric" else "rubric"
            else:
                l.role = "skip" if isinstance(prof, Economist) else "rubric"
    # a New Yorker line in the department face above another one: rubric, then the piece's title
    for l in lines:
        if l.role == "rubric" and isinstance(prof, NewYorker):
            nxt = below(l, ("rubric",), 20)
            if nxt is not None and below(nxt, ("body", "drop", "byline", "stand?"), 80):
                nxt.role = "head"
    # standfirsts: under a headline (or its byline); else captions
    heads = [l for l in lines if l.role in ("head", "byline", "dateline")]
    for l in lines:
        if l.role == "bold?" and l.accent and len(l.text) < 70:
            l.role = "sub"          # a heading in the text, set in the magazine's colour
    for l in lines:
        if l.role in ("stand?", "bold?"):
            prev = above(l, 60)
            chain = prev
            while chain is not None and chain.role in (l.role, "stand"):
                chain = above(chain, 60)
            if chain is not None and chain.role in ("head", "byline", "dateline", "rubric"):
                l.role = "stand"
            elif l.role == "bold?":
                run, m = 1, l
                while True:
                    m = below_any(m, 3)
                    if m is None or m.role not in ("bold?", "body") or "Bold" not in m.font and "Medium" not in m.font:
                        break
                    run += 1
                m = l
                while True:
                    m = above(m, 3)
                    if m is None or m.role not in ("bold?", "body") or "Bold" not in m.font and "Medium" not in m.font:
                        break
                    run += 1
                whole = all(any(w in f for w in ("Bold", "Medium", "Demi")) for t, f, _s in l.spans if t.strip())
                l.role = "sub" if whole and run <= 2 and len(l.text) < 70 else "body"
            else:
                l.role = "caption"
    return body_size


def drawn_regions(page, lines, scale=0.75):
    """Where a page drawn as one picture under its text holds pictures: what is not white once
    the text is wiped out, in pieces apart from each other."""
    from PIL import Image, ImageDraw, ImageFilter
    img = page.render(scale=scale).to_pil().convert("L")
    draw = ImageDraw.Draw(img)
    for l in lines:
        draw.rectangle([(l.x0 - 1) * scale, (l.top - 1) * scale, (l.x1 + 1) * scale, (l.bottom + 1) * scale], fill=255)
    ink = img.point(lambda v: 255 if v < 225 else 0).filter(ImageFilter.MaxFilter(5))
    w, h = ink.size
    px = ink.load()
    seen = bytearray(w * h)
    found = []
    for y in range(h):
        for x in range(w):
            if px[x, y] and not seen[y * w + x]:
                stack = [(x, y)]
                seen[y * w + x] = 1
                x0 = x1 = x
                y0 = y1 = y
                n = 0
                while stack:
                    cx, cy = stack.pop()
                    n += 1
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                        if 0 <= nx < w and 0 <= ny < h and px[nx, ny] and not seen[ny * w + nx]:
                            seen[ny * w + nx] = 1
                            stack.append((nx, ny))
                box = (x0 / scale, y0 / scale, (x1 + 1) / scale, (y1 + 1) / scale)
                if box[2] - box[0] >= MIN_PICTURE and box[3] - box[1] >= MIN_PICTURE and n > 0.05 * (x1 - x0 + 1) * (y1 - y0 + 1):
                    found.append(box)
    return found


def find_pictures(prof, lines, images, paths, page_w, page_h, body_size, page=None):
    """Raster pictures, and charts (their text with the paths drawn around it), as boxes; the
    lines inside them are theirs."""
    pics = []
    for x0, top, x1, bottom in images:
        if x1 - x0 < MIN_PICTURE or bottom - top < MIN_PICTURE:
            continue
        if page is not None and (x1 - x0) * (bottom - top) > 0.7 * page_w * page_h:
            # the whole page as one picture, its text laid over it: the pictures are in it
            pics.extend([list(b) + ["photo"] for b in drawn_regions(page, lines)])
            continue
        pics.append([x0, top, x1, bottom, "photo"])
    # merge overlapping pictures
    merged = True
    while merged:
        merged = False
        for i in range(len(pics)):
            for j in range(i + 1, len(pics)):
                a, b = pics[i], pics[j]
                if _overlap(a[0], a[2], b[0], b[2]) > -2 and _overlap(a[1], a[3], b[1], b[3]) > -2:
                    pics[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]), "photo"]
                    del pics[j]
                    merged = True
                    break
            if merged:
                break
    # charts: text of the chart role clustered, then the paths touching the cluster
    chart = [l for l in lines if l.role == "chart"]
    clusters = []
    for l in chart:
        box = [l.x0, l.top, l.x1, l.bottom]
        clusters.append(box)
    pad = 14
    changed = True
    while changed:
        changed = False
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                a, b = clusters[i], clusters[j]
                if _overlap(a[0] - pad, a[2] + pad, b[0], b[2]) > 0 and _overlap(a[1] - pad, a[3] + pad, b[1], b[3]) > 0:
                    clusters[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del clusters[j]
                    changed = True
                    break
            if changed:
                break
    for c in clusters:
        if (c[2] - c[0]) * (c[3] - c[1]) < 600:
            continue
        for _ in range(3):
            for x0, top, x1, bottom in paths:
                if bottom - top > 0.8 * page_h or x1 - x0 > 0.95 * page_w:
                    continue
                if _overlap(c[0] - 6, c[2] + 6, x0, x1) > 0 and _overlap(c[1] - 6, c[3] + 6, top, bottom) > 0:
                    if (x1 - x0) > 3 * (c[2] - c[0]) + 60 or (bottom - top) > 3 * (c[3] - c[1]) + 60:
                        continue
                    c[0], c[1], c[2], c[3] = min(c[0], x0), min(c[1], top), max(c[2], x1), max(c[3], bottom)
        pics.append([c[0] - 2, c[1] - 2, c[2] + 2, c[3] + 2, "chart"])
    # one picture inside another is part of it
    def area(p):
        return max(0, p[2] - p[0]) * max(0, p[3] - p[1])
    pics.sort(key=area, reverse=True)
    kept = []
    for pc in pics:
        inside = False
        for k in kept:
            ov = max(0, _overlap(k[0], k[2], pc[0], pc[2])) * max(0, _overlap(k[1], k[3], pc[1], pc[3]))
            if ov > 0.6 * area(pc):
                k[0], k[1], k[2], k[3] = min(k[0], pc[0]), min(k[1], pc[1]), max(k[2], pc[2]), max(k[3], pc[3])
                inside = True
                break
        if not inside:
            kept.append(pc)
    boxes = []
    for x0, top, x1, bottom, kind in kept:
        boxes.append(Box("picture", x0, top, x1, bottom))
    # a picture keeps the lines inside it, unless they are the magazine's running text
    for l in lines:
        if l.role in ("body", "head", "stand", "byline", "rubric", "drop", "sub"):
            continue
        for b in boxes:
            if _overlap(b.x0, b.x1, l.x0, l.x1) > 0.6 * (l.x1 - l.x0) and _overlap(b.top, b.bottom, l.top, l.bottom) > 0.5 * (l.bottom - l.top):
                if l.role in ("chart", "caption", "skip", "note"):
                    l.role = "inpicture"
                break
    return boxes


def _bold(line):
    ink = [(t, f) for t, f, _s in line.spans if t.strip()]
    n = sum(len(t) for t, f in ink)
    return n and sum(len(t) for t, f in ink if any(w in f for w in ("Bold", "Demi"))) >= 0.8 * n


def bold_panels(lines):
    """Runs of four or more body lines in bold, with those beside them: boxes apart."""
    runs, cur = [], []
    for l in lines:
        if l.role in ("body", "sub") and _bold(l) and not l.accent and (not cur or (_overlap(cur[-1].x0, cur[-1].x1, l.x0, l.x1) > 0
                                                                 and 0 <= l.top - cur[-1].top < 3 * l.size)):
            cur.append(l)
            continue
        if len(cur) >= 4:
            runs.append(cur)
        cur = [l] if l.role in ("body", "sub") and _bold(l) else []
    if len(cur) >= 4:
        runs.append(cur)
    boxes = [[min(l.x0 for l in r), min(l.top for l in r), max(l.x1 for l in r), max(l.bottom for l in r)] for r in runs]
    merged = True
    while merged:
        merged = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if _overlap(a[1], a[3], b[1], b[3]) > 0 and _overlap(a[0] - 20, a[2] + 20, b[0], b[2]) > 0:
                    boxes[i] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    del boxes[j]
                    merged = True
                    break
            if merged:
                break
    return [tuple(b) for b in boxes]


def blocks_of(lines, body_size):
    """Lines of one role that follow each other in the content stream and down the column."""
    blocks, cur = [], []
    for l in lines:
        if cur:
            p = cur[-1]
            ok = (l.role == p.role and _overlap(p.x0, p.x1, l.x0, l.x1) > 0
                  and getattr(l, "panel", None) == getattr(p, "panel", None)
                  and -0.3 * l.size < l.top - p.bottom < 1.2 * max(l.size, p.size)
                  and l.role not in ("drop",))
            if not ok:
                blocks.append(cur)
                cur = []
        cur.append(l)
    if cur:
        blocks.append(cur)
    return [Box.of(b[0].role, b) for b in blocks]


def _cut(boxes, axis):
    """The boxes in groups along an axis, where nothing crosses; and the widest gap between them."""
    lo, hi = (lambda b: b.top, lambda b: b.bottom) if axis == "y" else (lambda b: b.x0, lambda b: b.x1)
    floating = []
    if axis == "x":         # a picture may straddle two columns: it goes with the one it most covers
        solid = [b for b in boxes if b.kind != "picture"]
        if solid:
            floating = [b for b in boxes if b.kind == "picture"]
            boxes = solid
    items = sorted(boxes, key=lo)
    groups, cur, reach, widest = [], [items[0]], hi(items[0]), 0
    for b in items[1:]:
        if lo(b) >= reach - (0.5 if axis == "y" else 1.0):
            groups.append(cur)
            if axis == "x" or not all(c.kind in HEAD_ROLES for c in cur):
                widest = max(widest, lo(b) - reach)     # a headline is one with what it heads
            cur, reach = [b], hi(b)
        else:
            cur.append(b)
            reach = max(reach, hi(b))
    groups.append(cur)
    for pc in floating:
        best = max(groups, key=lambda g: (max(_overlap(pc.x0, pc.x1, b.x0, b.x1) for b in g), -min(b.x0 for b in g)))
        best.append(pc)
    return groups, widest


ENDS = re.compile(r"[.!?:;”\"’)\]■♦…]$")


def _seam(a, b):
    """How wrong it looks to read `b` right after `a`: text cut mid-sentence going on with a
    capital, a finished sentence going on in lower case, a headline over a sentence's end."""
    if a.kind == "picture" or b.kind == "picture":
        return 0
    last, first = a.lines[-1].text, b.lines[0].text
    lower = b.kind == "body" and first[:1].islower()
    if a.kind in ("rubric", "head", "stand", "byline", "dateline", "section", "sub") and lower:
        return 1
    if a.kind == "body":
        cut = last.endswith(("\x02", "-")) or not ENDS.search(last)
        if cut and not lower and b.kind in ("body", "rubric", "head", "sub"):
            return 1
        if not cut and lower:
            return 1
    if b.kind == "rubric" and a.kind in ("rubric", "head", "stand", "byline"):
        return 1
    return 0


def _score(seq):
    text = [b for b in seq if b.kind != "picture"]
    return sum(_seam(a, b) for a, b in zip(text, text[1:]))


def xy_order(boxes):
    """Reading order (XY cut): the page cut where nothing crosses — across into bands read top to
    bottom, or down into columns read left to right. Where both cuts exist, the one whose text
    runs on better from block to block; then the widest gap."""
    if len(boxes) <= 1:
        return list(boxes)
    rows, row_gap = _cut(boxes, "y")
    cols, col_gap = _cut(boxes, "x")
    if len(cols) > 1 and len(rows) > 1:
        by_cols = [x for g in cols for x in xy_order(g)]
        by_rows = [x for g in rows for x in xy_order(g)]
        a, b = _score(by_cols), _score(by_rows)
        if a != b:
            return by_cols if a < b else by_rows
        return by_cols if col_gap > row_gap + 2 else by_rows
    if len(cols) > 1:
        return [x for g in cols for x in xy_order(g)]
    if len(rows) > 1:
        return [x for g in rows for x in xy_order(g)]
    return sorted(boxes, key=lambda b: (b.top, b.x0))


def tail_first(order, open_text):
    """The end of the article that runs on from the page before goes first, wherever the page
    puts it: the topmost text of a column, starting in lower case, before any headline."""
    if not open_text or not (open_text.endswith(("\x02", "-")) or not ENDS.search(open_text)):
        return order
    heads = [i for i, b in enumerate(order) if b.kind in HEAD_ROLES + ("section",)]
    if not heads:
        return order
    for i, b in enumerate(order):
        if i < heads[0]:
            continue
        before = next((o for o in reversed(order[:i]) if o.kind != "picture"), None)
        if before is not None and before.kind == "body" and not ENDS.search(before.lines[-1].text):
            continue                # it goes on from the column before it, on this page
        if b.kind == "body" and b.lines[0].text[:1].islower() and \
                not any(o is not b and o.kind != "picture" and o.bottom <= b.top + 1 and _overlap(o.x0, o.x1, b.x0, b.x1) > 0
                        for o in order):
            run = [b]
            for c in order[i + 1:]:
                if c.kind == "body" and _overlap(c.x0, c.x1, b.x0, b.x1) > 0 and c.top >= run[-1].bottom - 1 \
                        and c.top - run[-1].bottom < 3 * c.lines[0].size and not ENDS.search(run[-1].lines[-1].text):
                    run.append(c)
                else:
                    break
            return run + [o for o in order if not any(o is r for r in run)]
    return order


# ------------------------------------------------------------------------------------------
# Text: words cut at line ends, small capitals, italics
# ------------------------------------------------------------------------------------------

WORD = re.compile(r"[A-Za-zÀ-ÖØ-öø-ÿ’']+")


SUFFIXES = {"ment", "ments", "ness", "tion", "tions", "sion", "ing", "ings", "ed", "ly", "er", "ers", "est", "able",
            "ible", "ful", "less", "ism", "ist", "ists", "ity", "ous", "ive", "al", "ance", "ence", "ship", "dom",
            "ture", "ty", "ry", "cy", "es", "s", "ic", "ical", "ize", "ise", "ised", "ized", "ian", "ians", "ate", "ated"}


def _dictionary():
    """The system's English word list, where there is one: words it knows are joined."""
    words = set()
    for path in ("/usr/share/dict/words", "/usr/share/dict/american-english", "/usr/share/dict/british-english"):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                words.update(w.strip().lower() for w in fh if w.strip().isalpha())
        except OSError:
            continue
    return words


DICTIONARY = _dictionary()


class Vocabulary:
    def __init__(self):
        self.words = Counter()
        self.hyphened = Counter()

    def learn(self, text):
        for token in text.split():
            parts = WORD.findall(token)
            if "-" in token.strip("-"):
                for a, b in zip(parts, parts[1:]):
                    self.hyphened[a.lower() + "-" + b.lower()] += 1
            elif len(parts) == 1:
                self.words[parts[0].lower()] += 1

    def mend(self, left, right):
        """`left` ended a line on a hyphen and `right` began the next: one word, with or
        without its hyphen?"""
        a = WORD.findall(left)
        b = WORD.findall(right)
        if not a or not b:
            return True
        a, b = a[-1].lower(), b[0].lower()
        if right[:1].isupper() and not left[-1:].isupper():
            return True             # anti-|AfD, ex-|Soviet
        if (a + "-" + b) in self.hyphened:
            return True
        if (a + b) in self.words or b in SUFFIXES or (a + b) in DICTIONARY:
            return False            # comput-|er-system, te-|lecoms
        if re.match(r"[A-Za-z]+-", right):
            return True             # eye-|to-eye
        known = lambda w: self.words.get(w, 0) or w in DICTIONARY
        if known(a) and known(b) and len(a) >= 2 and len(b) >= 3:
            return True             # long-|awaited, white-|collar
        return False


def _span_html(text, font, sc_upper=True):
    if "SC" in font.split("-")[0] or font.split("-")[0].endswith("SC"):
        text = text.upper()             # small capitals: the font draws capitals for the lower case
    t = html.escape(text, quote=False)
    if not t.strip():
        return t
    lead, trail = t[:len(t) - len(t.lstrip())], t[len(t.rstrip()):]
    t = t.strip()
    italic = "Italic" in font
    bold = any(w in font for w in ("SemiBold", "Bold", "Demi", "Black")) and "Medium" not in font
    small = "SC" in font.split("-")[0] or font.split("-")[0].endswith("SC")
    if small:
        t = "<small>%s</small>" % t
    if bold:
        t = "<b>%s</b>" % t
    if italic:
        t = "<i>%s</i>" % t
    return lead + t + trail


def line_html(line, skip_first=0):
    out = []
    n = 0
    for text, font, size in line.spans:
        if skip_first and n < skip_first:
            cut = min(len(text), skip_first - n)
            n += len(text)
            text = text[cut:]
            if not text:
                continue
        out.append(_span_html(text.replace("\x02", "\x02"), font))
    s = "".join(out)
    s = re.sub(r"</(i|b)>(\s*)<\1>", r"\2", s)
    s = re.sub(r"</small>(\s*)<small>", r"\1", s)
    return s.strip()


# ------------------------------------------------------------------------------------------
# The issue: pages read, articles cut out
# ------------------------------------------------------------------------------------------

def signature(line):
    """A name in small capitals on a line of its own: who signs a letter."""
    ink = [(t, f) for t, f, _s in line.spans if t.strip()]
    return bool(ink) and len(line.text) < 45 and all("SC" in f for t, f in ink) and not line.text.endswith(("-", "\x02"))


class Article:
    def __init__(self, category):
        self.category = category
        self.rubric = []
        self.title = []
        self.stand = []
        self.byline = []
        self.dateline = None
        self.items = []             # ("p", html, plain) | ("sub", html) | ("picture", Box) | ("note", html)
        self.open = None            # the paragraph being written: [html pieces]
        self.last_line = None
        self.hero = []
        self.waiting = []
        self.column = 0             # the width of the article's columns
        self.pages = set()

    @property
    def has_head(self):
        return bool(self.title)


def smart_title(text):
    """A headline set in capitals, in title case."""
    if not text or not text.isupper():
        return text
    small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with", "vs."}
    words = text.lower().split()
    out = []
    for i, w in enumerate(words):
        if i and w in small:
            out.append(w)
        else:
            out.append("-".join(re.sub(r"^([^\w]*)(\w)", lambda m: m.group(1) + m.group(2).upper(), part)
                                for part in w.split("-")))
    return " ".join(out)


class Builder:
    def __init__(self, prof, vocab, body_size):
        self.prof, self.vocab, self.body_size = prof, vocab, body_size
        self.articles = []
        self.cur = None
        self.section = None
        self.skipping = False
        self.poems = []             # poems met in the article being read, put after it
        self.poem = None

    # --- articles
    def start(self):
        if self.cur is not None:
            self.close_para()
        self.flush_poems()
        self.cur = Article(self.section)
        self.articles.append(self.cur)
        return self.cur

    def flush_poems(self):
        self.articles.extend(p for p in self.poems if p.items)
        self.poems, self.poem = [], None

    def ensure(self):
        if self.cur is None:
            self.start()
        return self.cur

    def close_para(self):
        a = self.cur
        if a is not None and a.open:
            text = "".join(a.open).strip()
            text = re.sub(r"\s+", " ", text)
            text = re.sub(r"</(b|i|small)>(\s*)<\1>", r"\2", text).replace("\x02", "-")
            if text:
                a.items.append(("sig" if getattr(a, "open_class", None) == "signature" else "p", text))
            a.open_class = None
            a.open = None
            a.last_line = None
        if a is not None and a.waiting and not a.open:
            a.items.extend(a.waiting)
            a.waiting = []

    # --- lines
    def add_head(self, box):
        if self.skipping:
            return
        a = self.cur
        role = box.kind
        text = " ".join(l.plain for l in box.lines)
        text = re.sub(r"\s+", " ", text.replace("\x02", "")).strip()
        if a is not None and getattr(a, "section_opener", False) and not a.items and not a.open:
            a.section_opener = False
            a.title = []
        if a is None or a.items or a.open or (role == "rubric" and (a.title or a.stand)) or \
                (role == "head" and (a.title and (a.stand or a.byline))) or \
                (role in ("stand",) and a.stand and a.title and a.byline):
            a = self.start()
        if role == "rubric":
            a.rubric.append(text)
        elif role == "head":
            a.title.append(text)
            if box.lines[0].font.startswith("TNYIrvinPro-Titling") and self.section in ("The Talk of the Town", "Goings On"):
                self.section = a.category = None        # the features after the Talk
        elif role == "stand":
            a.stand.append(text)
        elif role == "byline":
            a.byline.append(re.sub(r"^BY\s+", "", text, flags=re.I))
        elif role == "dateline":
            a.dateline = text

    def add_section(self, box):
        text = re.sub(r"\s+", " ", " ".join(l.plain for l in box.lines)).strip()
        category, title = self.prof.section_title(text, box.lines[0].spans)
        self.close_para()
        self.section = category
        self.skipping = category in self.prof.skip_sections
        if not self.skipping:
            a = self.start()
            a.category = category
            if title:
                a.title.append(title)
            a.section_opener = True

    def add_text(self, box, drops, beside=()):
        if self.skipping:
            return
        a = self.ensure()
        lines = box.lines
        width_right = max(l.x1 for l in lines)
        if len(lines) >= 3:
            a.column = max(a.column, width_right - min(l.x0 for l in lines))
        for i, l in enumerate(lines):
            nxt = lines[i + 1] if i + 1 < len(lines) else None
            indent_ref = nxt.x0 if nxt is not None else (lines[i - 1].x0 if i else l.x0)
            # an indent is about an em; more is text running round a picture
            indented = 0.7 * l.size < l.x0 - indent_ref < 2.2 * l.size and id(l) not in beside
            if nxt is not None and id(nxt) in beside and id(l) in beside:
                indented = False
            drop = drops.pop(id(l), None)
            if box.kind == "sub":
                if i == 0:
                    self.close_para()
                    a.open = []
                self.append_line(a, l)
                if nxt is None:
                    a.items.append(("sub", "".join(a.open).replace("\x02", "-").strip()))
                    a.open = None
                continue
            if box.kind == "note":
                self.close_para()
                a.items.append(("note", line_html(l)))
                continue
            sig = signature(l)
            if sig:
                self.close_para()
                a.open = []
                a.open_class = "signature"
                self.append_line(a, l)
                a.last_line = l
                continue
            if getattr(a, "open_class", None) == "signature" and a.open is not None:
                if not indented and l.x1 - l.x0 < 0.88 * a.column and len(l.text) < 50:
                    a.open.append(" · ")
                    a.open.append(line_html(l))
                    a.last_line = l
                    continue
                self.close_para()
            new = drop is not None or indented
            if a.open is not None and not new and a.last_line is not None:
                prev = a.last_line
                ended = re.search(r"[.!?:”\"’)■]$", prev.text)
                short = prev.x1 < prev_right(prev, a) - 2.5 * prev.size
                if i == 0 and ended and short:
                    new = True
                elif i > 0 and short and ended and not indented and l.x0 <= prev.x0 + 1:
                    new = True
                elif re.match(r"^[—–]\s*[A-Z]", l.text) and ended and l.x1 >= width_right - 2:
                    new = True      # a signature set to the right
            if new or a.open is None:
                self.close_para()
                a.open = []
                if drop is not None:
                    a.open.append('<span class="drop-cap">%s</span>' % html.escape(drop))
                    a.first_para = True
            self.append_line(a, l)
            a._right = max(getattr(a, "_right", 0), l.x1) if i else l.x1
            a.last_line = l
            a.right_of = width_right

    def append_line(self, a, l):
        piece = line_html(l)
        if a.open:
            m = re.search(r"\x02((?:</[a-z]+>)*)$", a.open[-1])
            if m and m.group(1):
                a.open[-1] = a.open[-1][:m.start()] + m.group(1) + "\x02"
        if a.open and a.open[-1].endswith("\x02"):
            left = a.open[-1][:-1]
            keep = self.vocab.mend(re.sub(r"<[^>]+>", "", left), l.text)
            a.open[-1] = left + ("-" if keep else "")
            a.open.append(piece)
        elif a.open and re.search(r"[A-Za-z]-$", a.open[-1]) and l.text[:1].islower():
            left = a.open[-1][:-1]
            keep = self.vocab.mend(re.sub(r"<[^>]+>", "", left), l.text)
            a.open[-1] = left + ("-" if keep else "")
            a.open.append(piece)
        else:
            if a.open and not a.open[-1].endswith(("—", "–", "/", "</span>")):
                a.open.append(" ")
            a.open.append(piece)

    def add_verse(self, box):
        """A poem printed among the pages of an article: an article of its own, after it."""
        if self.skipping:
            return
        if box.kind == "poemtitle":
            poem = Article("Poems")
            poem.title = [smart_title(" ".join(l.plain for l in box.lines))]
            poem.stanzas = []
            self.poems.append(poem)
            self.poem = poem
            return
        poem = self.poem
        if poem is None:            # verse without a title: lines kept in the article itself
            a = self.ensure()
            self.close_para()
            a.items.append(("verse", "<br/>".join(line_html(l) for l in box.lines)))
            return
        if box.kind == "versesig":
            poem.byline = [re.sub(r"^[—–]\s*", "", " ".join(l.plain for l in box.lines)).strip()]
            self.poem = None
            return
        stanza, last = [], None
        for l in box.lines:
            if last is not None and l.top - last.bottom > 0.9 * l.size and stanza:
                poem.items.append(("verse", "<br/>".join(stanza)))
                stanza = []
            stanza.append(line_html(l))
            last = l
        if stanza:
            poem.items.append(("verse", "<br/>".join(stanza)))

    def add_break(self):
        if self.skipping or self.cur is None:
            return
        self.close_para()
        if self.cur.items and self.cur.items[-1][0] == "break":
            return
        self.cur.items.append(("break", ""))

    def add_signed(self, box):
        if self.skipping:
            return
        a = self.ensure()
        self.close_para()
        a.items.append(("sig", " ".join(line_html(l) for l in box.lines)))

    def add_box(self, blocks, drops, beside):
        """A box set apart from the article's text: its own paragraphs, after the paragraph it cuts."""
        if self.skipping:
            return
        a = self.ensure()
        inner = Builder(self.prof, self.vocab, self.body_size)
        inner.cur = Article(None)
        for bl in blocks:
            if bl.kind in ("rubric", "head", "stand"):
                inner.close_para()
                inner.cur.items.append(("sub", html.escape(" ".join(l.plain for l in bl.lines))))
            elif bl.kind in ("body", "sub", "note", "byline", "dateline"):
                if bl.kind in ("byline", "dateline"):
                    bl.kind = "note"
                if bl.kind == "sub" and not all(l.accent for l in bl.lines):
                    bl.kind = "body"
                inner.add_text(bl, drops, beside)
        inner.close_para()
        if inner.cur.items:
            if a.open:
                a.waiting.append(("box", inner.cur.items))
            else:
                a.items.append(("box", inner.cur.items))

    def add_picture(self, box, hero=False):
        if self.skipping:
            return
        a = self.ensure()
        if hero:
            a.hero.append(box)
            return
        # a picture goes between paragraphs: after the one being written
        if a.open:
            a.waiting.append(("picture", box))
        else:
            a.items.append(("picture", box))


def prev_right(prev, a):
    return getattr(a, "right_of", prev.x1)


def read_issue(pdf_path, prof, doc):
    vocab = Vocabulary()
    pages = []
    n = len(doc)
    for p in range(n):
        say(step="reading", page=p + 1, of=n)
        page = doc[p]
        w, h = page.get_width(), page.get_height()
        chars = page_chars(page)
        lines = lines_of(chars)
        images, paths, panels = page_objects(page)
        pages.append((w, h, lines, images, paths, panels))
        cut = False
        for l in lines:
            words = l.text.split()
            if cut and words:
                words = words[1:]
            cut = l.text.endswith(("\x02", "-"))
            if cut and words:
                words = words[:-1]
            vocab.learn(" ".join(words))
    return pages, vocab


def _key(text):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFD", text.lower()))


def page_kind(prof, lines):
    """"article", "ad" or "skip" (contents, puzzles, masthead)."""
    if prof.contents_page(lines):
        return "skip"
    house = sum(len(l.text) for l in lines if l.role not in ("foreign", "furniture"))
    foreign = sum(len(l.text) for l in lines if l.role == "foreign")
    body = sum(len(l.text) for l in lines if l.role == "body")
    heads = any(l.role in ("head", "section") for l in lines)
    if body < 300 and not heads:
        return "ad"
    if foreign > house:
        return "ad"
    return "article"


def build(pdf_path, prof, doc):
    pages, vocab = read_issue(pdf_path, prof, doc)
    sizes = Counter()
    for w, h, lines, _i, _p, _q in pages:
        for l in lines:
            sizes[(l.font, l.size)] += len(l.text)
    body_size = sizes.most_common(1)[0][0][1] if sizes else 9
    b = Builder(prof, vocab, body_size)
    pictures = []
    page_texts = []
    # the table of contents names the pieces whose title is a drawing, not text (fiction)
    folios, entries, seen = {}, [], set()
    for p, (w, h, lines, images, paths, panels) in enumerate(pages):
        settle_roles(prof, lines, h)
        for l in lines:
            if l.role == "furniture" and re.fullmatch(r"\d{1,3}", l.text):
                folios[p] = int(l.text)
            if l.role in ("head", "poemtitle"):
                seen.add(_key(l.plain))
        if p and prof.contents_page(lines):
            entries += prof.contents(lines)
    unseen = [e for e in entries if not any(_key(e["title"]).startswith(k) or k.startswith(_key(e["title"]))
                                            for k in seen if len(k) > 3)]
    for p, (w, h, lines, images, paths, panels) in enumerate(pages):
        page_texts.append(" ".join(l.plain for l in lines))
        if p == 0:
            continue                    # the cover, drawn as the cover
        bs = settle_roles(prof, lines, h)
        kind = page_kind(prof, lines)
        here = [e for e in unseen if folios.get(p) == e["folio"] or
                (p not in folios and folios.get(p - 1, -9) + 1 == e["folio"])]
        for e in here:
            unseen.remove(e)
            a = b.start()
            a.category = None
            a.title, a.byline, a.rubric = [e["title"]], [e["author"]] if e["author"] else [], [e["dept"]] if e["dept"] else []
            if kind != "article":       # its opening page is the drawing with its title
                whole = Box("picture", 0, 0, w, h)
                whole.page = p
                a.hero.append(whole)
        if kind != "article":
            continue
        header = prof.section_of_header(lines)
        if header and not any(l.role == "section" for l in lines):
            b.section = header
        # the parts of the page an advertisement holds
        foreign = [l for l in lines if l.role == "foreign"]
        pics = find_pictures(prof, lines, images, paths, w, h, bs, doc[p])
        pics = [pc for pc in pics if not any(
            _overlap(pc.x0, pc.x1, l.x0, l.x1) > 0 and _overlap(pc.top, pc.bottom, l.top, l.bottom) > 0 for l in foreign)]
        # pictures covered by the running text are backgrounds, not pictures
        kept = []
        for pc in pics:
            area = (pc.x1 - pc.x0) * (pc.bottom - pc.top)
            text_in = sum((l.x1 - l.x0) * (l.bottom - l.top) for l in lines if l.role == "body"
                          and _overlap(pc.x0, pc.x1, l.x0, l.x1) > 0 and _overlap(pc.top, pc.bottom, l.top, l.bottom) > 0)
            if area > 0 and text_in < 0.15 * area:
                kept.append(pc)
        pics = kept
        for pc in pics:
            pc.page = p
        text_lines = [l for l in lines if l.role in ("body", "sub", "head", "rubric", "stand", "byline", "dateline",
                                                     "section", "caption", "note", "drop", "verse", "poemtitle",
                                                     "versesig", "break", "sig")]
        # drop capitals belong to the line at their top, right of them
        drops, beside = {}, set()
        body_lines = [l for l in text_lines if l.role == "body"]
        for d in [l for l in text_lines if l.role == "drop"]:
            cands = [l for l in body_lines if l.x0 >= d.x1 - 2 and l.x0 - d.x1 < 3 * bs and abs(l.top - d.top) < bs]
            if cands:
                first = min(cands, key=lambda l: l.top)
                drops[id(first)] = d.text
                for l in body_lines:
                    if l.x0 >= d.x1 - 2 and l.x0 - d.x1 < 3 * bs and l.top < d.bottom - 2 and l.bottom > d.top:
                        beside.add(id(l))
        text_lines = [l for l in text_lines if l.role != "drop"]
        # captions go with the nearest picture
        captions = [l for l in text_lines if l.role == "caption"]
        text_lines = [l for l in text_lines if l.role != "caption"]
        for cap in blocks_of(captions, bs):
            best, dist = None, 1e9
            for pc in pics:
                ov = _overlap(pc.x0, pc.x1, cap.x0, cap.x1)
                if ov <= 0 and not (cap.top >= h - 60):
                    continue
                d = cap.top - pc.bottom if cap.top >= pc.bottom - 2 else (pc.top - cap.bottom if cap.bottom <= pc.top + 2 else 0)
                if d < -2:
                    continue
                if d < dist:
                    best, dist = pc, d
            if best is not None and dist < 400:
                best.caption = ((best.caption + " ") if best.caption else "") + " ".join(line_html(l) for l in cap.lines)
        for l in text_lines:
            l.panel = None
        panels = list(panels) + bold_panels(text_lines)
        for k, (x0, top, x1, bottom) in enumerate(panels):
            inside = [l for l in text_lines if l.x0 >= x0 - 1 and l.x1 <= x1 + 1 and l.top >= top - 1 and l.bottom <= bottom + 1]
            if inside and not any(l.role in ("head", "section") for l in inside) and \
                    sum(len(l.text) for l in inside if l.role == "body") > 80:
                for l in inside:
                    if l.panel is None:
                        l.panel = k
        blocks = blocks_of(text_lines, bs)
        order = xy_order(blocks + pics)
        cur = b.cur
        open_text = cur.last_line.text if cur is not None and cur.open and cur.last_line is not None else ""
        order = tail_first(order, open_text)
        pending_hero = []
        boxed = set()
        for i, bl in enumerate(order):
            panel = getattr(bl.lines[0], "panel", None) if bl.lines else None
            if panel is not None:
                if panel not in boxed:
                    boxed.add(panel)
                    b.add_box([x for x in order if x.lines and getattr(x.lines[0], "panel", None) == panel], drops, beside)
                continue
            if bl.kind == "picture":
                # a picture right above a headline is the article's own
                nxt = next((x for x in order[i + 1:] if x.kind != "picture"), None)
                if nxt is not None and nxt.kind in ("rubric", "head", "section") and -2 <= nxt.top - bl.bottom < 120:
                    pending_hero.append(bl)
                else:
                    b.add_picture(bl)
                pictures.append(bl)
                continue
            if bl.kind == "head" and prof.section_head(bl):
                bl.kind = "section"
            if bl.kind in ("poemtitle", "verse", "versesig"):
                b.add_verse(bl)
                continue
            if bl.kind == "break":
                b.add_break()
                continue
            if bl.kind == "sig":
                b.add_signed(bl)
                continue
            if bl.kind == "section":
                b.add_section(bl)
            elif bl.kind in HEAD_ROLES:
                b.add_head(bl)
            else:
                b.add_text(bl, drops, beside)
            if pending_hero and b.cur is not None and bl.kind in HEAD_ROLES + ("section",):
                for pc in pending_hero:
                    b.add_picture(pc, hero=True)
                pending_hero = []
        for pc in pending_hero:
            b.add_picture(pc)
        if b.cur is not None:
            b.cur.pages.add(p)
    b.close_para()
    b.flush_poems()
    return b.articles, page_texts, pictures


# ------------------------------------------------------------------------------------------
# Pictures, chapters, the EPUB
# ------------------------------------------------------------------------------------------

def cut_pictures(doc, articles):
    """Every picture box rendered from its page, as JPEG (photographs) or PNG (charts)."""
    from PIL import Image
    by_page = defaultdict(list)
    for a in articles:
        boxes = a.hero + [it[1] for it in a.items if it[0] == "picture"]
        boxes += [v for it in a.items if it[0] == "box" for k, v in it[1] if k == "picture"]
        for box in boxes:
            by_page[box.page].append(box)
    images, n = [], 0
    for p in sorted(by_page):
        page = doc[p]
        bitmap = page.render(scale=RENDER).to_pil().convert("RGB")
        for box in by_page[p]:
            x0, top = max(0, box.x0 - 1) * RENDER, max(0, box.top - 1) * RENDER
            x1, bottom = min(page.get_width(), box.x1 + 1) * RENDER, min(page.get_height(), box.bottom + 1) * RENDER
            if x1 - x0 < 8 or bottom - top < 8:
                continue
            crop = bitmap.crop((int(x0), int(top), int(x1), int(bottom)))
            n += 1
            colours = len(crop.convert("P", palette=Image.ADAPTIVE, colors=256).getcolors(256) or [])
            out = io.BytesIO()
            few = crop.resize((max(1, crop.width // 4), max(1, crop.height // 4))).getcolors(4096)
            if few is not None and len(few) < 200:
                crop.save(out, "PNG", optimize=True)
                name = "img-%03d.png" % n
            else:
                crop.save(out, "JPEG", quality=82, optimize=True)
                name = "img-%03d.jpg" % n
            box.image = name
            images.append((name, out.getvalue()))
    return images


def chapter_html(a):
    esc = lambda s: html.escape(s, quote=False)
    out = []
    if a.category:
        out.append('<p class="category">%s</p>' % esc(a.category))
    if a.rubric:
        out.append('<p class="rubric">%s</p>' % esc(smart_title(" ".join(a.rubric))))
    title = smart_title(" ".join(a.title)) if a.title else (a.category or "")
    out.append("<h1>%s</h1>" % esc(title))
    for box in a.hero:
        out.append(picture_html(box, "hero-img"))
    if a.stand:
        out.append('<p class="lead">%s</p>' % esc(" ".join(a.stand)))
    if a.byline:
        out.append('<p class="author">%s</p>' % esc(smart_title(" ".join(a.byline))))
    first = True
    for kind, value in a.items:
        if kind == "p":
            text = value
            if first and a.dateline:
                text = '<span class="dateline">%s</span> ' % esc(a.dateline.title()) + text
            out.append('<p%s>%s</p>' % (' class="first"' if first else "", text))
            first = False
        elif kind == "sub":
            out.append("<h3>%s</h3>" % value)
            first = True
        elif kind == "note":
            out.append('<p class="note">%s</p>' % value)
        elif kind == "sig":
            out.append('<p class="signature">%s</p>' % value)
        elif kind == "verse":
            out.append('<p class="verse">%s</p>' % value)
        elif kind == "break":
            out.append('<p class="break">•</p>')
            first = True
        elif kind == "picture" and value.image:
            out.append(picture_html(value, "figure"))
        elif kind == "box":
            inner = []
            for k, v in value:
                if k == "p":
                    inner.append("<p>%s</p>" % v)
                elif k == "sub":
                    inner.append("<h3>%s</h3>" % v)
                elif k == "note":
                    inner.append('<p class="note">%s</p>' % v)
                elif k == "sig":
                    inner.append('<p class="signature">%s</p>' % v)
                elif k == "picture" and v.image:
                    inner.append(picture_html(v, "figure"))
            out.append('<div class="box">%s</div>' % "".join(inner))
    out.append('<p class="article-end">&#9830;</p>')
    return title, out


def picture_html(box, cls):
    if not box.image:
        return ""
    cap = '<p class="caption">%s</p>' % box.caption if box.caption else ""
    return '<div class="%s"><img src="%s" alt=""/>%s</div>' % (cls, box.image, cap)


CSS = """body { font-family: Georgia, "Times New Roman", serif; line-height: 1.55; margin: 0; padding: 0; }
h1 { font-size: 1.6em; font-weight: 700; line-height: 1.15; margin: 0 0 0.4em 0; text-align: left; }
h3 { font-size: 1.05em; font-weight: 700; margin: 1em 0 0.3em 0; }
p { margin: 0; text-align: justify; text-indent: 1.2em; }
p.first, p.lead, p.author, p.note, p.caption, h3 + p, p.signature + p { text-indent: 0; }
p.category { font-family: Helvetica, Arial, sans-serif; font-size: 0.75em; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.12em; margin: 0 0 0.3em 0; text-indent: 0; }
p.rubric { font-family: Helvetica, Arial, sans-serif; font-size: 0.85em; font-weight: 600; margin: 0 0 0.2em 0; text-indent: 0; }
p.lead { font-weight: 600; font-size: 1.05em; margin: 0 0 0.8em 0; }
p.author { font-size: 0.9em; font-style: italic; margin: 0 0 1em 0; }
p.note { font-size: 0.85em; font-style: italic; margin: 0.4em 0; }
p.caption { font-size: 0.8em; font-style: italic; margin: 0.3em 0 0; text-align: left; }
p.signature { text-indent: 0; margin: 0.2em 0 0.8em 0; font-size: 0.9em; }
p.verse { text-indent: 0; text-align: left; margin: 0 0 0.9em 1em; }
p.break { text-indent: 0; text-align: center; margin: 0.8em 0; }
p.article-end { text-align: center; text-indent: 0; margin-top: 1em; }
span.drop-cap { font-weight: 700; }
span.dateline { font-family: Helvetica, Arial, sans-serif; font-size: 0.75em; letter-spacing: 0.1em; text-transform: uppercase; }
div.hero-img, div.figure { margin: 0.8em 0; text-align: center; }
div.hero-img img, div.figure img { max-width: 100%; }
div.box { border-top: 1px solid #888; border-bottom: 1px solid #888; margin: 1em 0; padding: 0.4em 0; font-size: 0.92em; }
div.box h3 { margin-top: 0.2em; }
div.box p { text-indent: 0; margin-bottom: 0.4em; }
div.title-page { text-align: center; }
div.title-page img { max-width: 100%; }
"""

XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">
<head>
<meta charset="UTF-8"/>
<title>%s</title>
<link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
%s
</body>
</html>
"""


def write_epub(path, title, publisher, date_iso, cover, chapters, images):
    esc = lambda s: html.escape(s, quote=True)
    book_id = "urn:uuid:%s" % uuid.uuid4()
    files = [("chapter-%02d.xhtml" % (i + 1), c) for i, c in enumerate(chapters)]
    manifest = ['<item id="style" href="style.css" media-type="text/css"/>',
                '<item id="title-page" href="title.xhtml" media-type="application/xhtml+xml"/>',
                '<item id="toc" href="toc.xhtml" media-type="application/xhtml+xml" properties="nav"/>']
    if cover:
        manifest.append('<item id="cover-image" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/>')
    manifest += ['<item id="ch-%d" href="%s" media-type="application/xhtml+xml"/>' % (i + 1, f) for i, (f, _c) in enumerate(files)]
    manifest += ['<item id="img-%d" href="%s" media-type="%s"/>' % (i, n, "image/png" if n.endswith("png") else "image/jpeg")
                 for i, (n, _d) in enumerate(images)]
    spine = ['<itemref idref="title-page"/>'] + ['<itemref idref="ch-%d"/>' % (i + 1) for i in range(len(files))]
    opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">%s</dc:identifier>
    <dc:title>%s</dc:title>
    <dc:language>en</dc:language>
    <dc:publisher>%s</dc:publisher>
    %s
    %s
    <meta property="dcterms:modified">2000-01-01T00:00:00Z</meta>
</metadata>
<manifest>
    %s
</manifest>
<spine>
    %s
</spine>
</package>
""" % (book_id, esc(title), esc(publisher), "<dc:date>%s</dc:date>" % date_iso if date_iso else "",
       '<meta name="cover" content="cover-image"/>' if cover else "", "\n    ".join(manifest), "\n    ".join(spine))
    lis = []
    for f, c in files:
        author = ('\n            <span class="toc-author">%s</span>' % esc(c["author"])) if c.get("author") else ""
        lis.append('<li><a href="%s">\n            <span class="toc-cat">%s</span>\n            <span class="toc-title">%s</span>%s\n        </a></li>'
                   % (f, esc(c["category"] or ""), esc(c["title"]), author))
    nav = XHTML % ("Table of Contents", '<nav epub:type="toc" class="toc">\n    <h2>Table of Contents</h2>\n    <ol>\n        %s\n    </ol>\n</nav>'
                   % "\n".join(lis))
    title_page = XHTML % (esc(publisher), '<div class="title-page">\n%s    <h1>%s</h1>\n    <p class="edition">%s</p>\n</div>' % (
        '    <img src="cover.jpg" alt=""/>\n' if cover else "", esc(publisher.upper()), esc(title.split(" — ", 1)[-1])))
    container = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
<rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>
"""
    tmp = path + ".part"
    with zipfile.ZipFile(tmp, "w") as z:
        z.writestr(zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", container, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/content.opf", opf, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/toc.xhtml", nav, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/title.xhtml", title_page, zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", CSS, zipfile.ZIP_DEFLATED)
        if cover:
            z.writestr("OEBPS/cover.jpg", cover, zipfile.ZIP_STORED)
        for f, c in files:
            z.writestr("OEBPS/" + f, XHTML % (esc(c["title"]), "\n".join(c["body"])), zipfile.ZIP_DEFLATED)
        for name, data in images:
            z.writestr("OEBPS/" + name, data, zipfile.ZIP_STORED)
    os.replace(tmp, path)


MONTHS = {m: i + 1 for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"))}


def iso_date(text):
    if not text:
        return None
    m = re.search(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", text)
    if not m or m.group(1).lower() not in MONTHS:
        return None
    return "%s-%02d-%02d" % (m.group(3), MONTHS[m.group(1).lower()], int(m.group(2)))


def worth_keeping(a):
    text = sum(len(v) for k, v in a.items if k in ("p", "verse"))
    pics = sum(1 for k, v in a.items if k == "picture") + len(a.hero)
    if text < 600 and pics >= 4:
        return False        # a page of the magazine's own advertising
    return text >= 200 or (pics and (a.title or a.category))


def convert(pdf_path, epub_path, prof=None):
    doc = pdfium.PdfDocument(pdf_path)
    try:
        prof = prof or which(pdf_path, doc)
        if prof is None:
            raise ValueError("neither The Economist nor The New Yorker")
        articles, page_texts, _pics = build(pdf_path, prof, doc)
        for a in articles:
            prof.settle(a)
        articles = [a for a in articles if worth_keeping(a)]
        say(step="pictures")
        images = cut_pictures(doc, articles)
        cover = io.BytesIO()
        doc[0].render(scale=1600 / doc[0].get_height()).to_pil().convert("RGB").save(cover, "JPEG", quality=85)
        date = prof.issue_date(page_texts)
        title = "%s — %s" % (prof.name, date) if date else prof.name
        chapters = []
        for a in articles:
            t, body = chapter_html(a)
            chapters.append({"title": t, "category": a.category, "author": smart_title(" ".join(a.byline)) if a.byline else None,
                             "body": body})
        write_epub(epub_path, title, prof.name, iso_date(date), cover.getvalue(), chapters, images)
        return title
    finally:
        doc.close()


def main(argv):
    global PROGRESS
    args = [a for a in argv if a != "--progress"]
    PROGRESS = len(args) != len(argv)
    if len(args) == 2 and args[0] == "--which":
        prof = which(args[1])
        if prof:
            print(prof.key)
        return 0 if prof else 1
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
    say(done=title)
    if not PROGRESS:
        print(args[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
