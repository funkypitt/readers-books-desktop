"""Papers in PDF: paper2epub.py on pages as Marker gives them (made up here, with a page renderer
that draws nothing, so neither Marker nor pdfium is needed), the EPUB it writes as the reader
reads it, the shelf's way with a PDF (the converter faked), and the picture on the whole window."""
import importlib.util
import os
import sys
import tempfile
import time
import unittest
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = tempfile.mkdtemp(prefix="readers-books-papers-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "data")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rb = load("rb_papers", "readers_books.py")
p2e = load("paper2epub", "paper2epub.py")
import make_books  # noqa: E402
from PyQt5 import QtTest  # noqa: E402

APP = rb.QtWidgets.QApplication.instance() or rb.QtWidgets.QApplication([])
rb.load_bundled_fonts()
PNG = make_books.picture(400, 120, 230)


def path(name):
    return os.path.join(TMP, name)


def block(kind, bbox, html="", children=None):
    return {"block_type": kind, "bbox": bbox, "html": html, "children": children}


LONG = "Les pluies d'automne lavent les pavés de la ville et les passants pressent le pas sous les auvents. " * 2

# A journal's first page: a banner, the title, the authors, a sidebar in the left margin, the
# abstract, the first section cut at the bottom of the page. Then a second page: a figure with its
# caption, the rest of the paragraph, an equation and its "where", a subsection, a footnote, a
# second section, the references.
PAGES = [
    {"block_type": "Page", "bbox": [0, 0, 612, 792], "children": [
        block("PageHeader", [30, 20, 150, 50]),
        block("SectionHeader", [200, 90, 300, 103], "<h4>RESEARCH ARTICLE</h4>"),
        block("SectionHeader", [200, 106, 570, 150], "<h1>La pluie et le beau temps</h1>"),
        block("Text", [200, 160, 560, 190], "<p>Anne Martin<sup>1</sup>, Paul Durand<sup>2</sup></p>"),
        block("Text", [30, 300, 180, 420], "<p><b>Citation:</b> Martin A, Durand P (2017) La pluie et le beau temps. "
                                           "Revue des nuages 12(3): e0185809, with a licence that lets anyone share it,</p>"),
        block("SectionHeader", [200, 285, 260, 300], "<h2>Abstract</h2>"),
        block("Text", [200, 310, 580, 500], "<p>" + LONG + "</p>"),
        block("SectionHeader", [200, 560, 280, 575], "<h2>1 Introduction</h2>"),
        block("Text", [200, 580, 580, 710], "<p>" + LONG + "Nous montrons que les nuages trans-</p>"),
        block("PageFooter", [550, 745, 575, 756]),
    ]},
    {"block_type": "Page", "bbox": [0, 0, 612, 792], "children": [
        block("Text", [30, 70, 180, 200], "<p>listed in full, with every name, on the second page of the sidebar.</p>"),
        block("FigureGroup", [200, 60, 580, 330], "", [
            block("Figure", [210, 60, 570, 300]),
            block("Caption", [200, 305, 580, 330], "<p>Fig 1. Un nuage, vu d'en dessous.</p>"),
        ]),
        block("Text", [200, 340, 580, 400], "<p>portent l'eau des mers jusqu'aux montagnes, d<sub>k</sub> fois par an.</p>"),
        block("Equation", [260, 405, 520, 430], "<p>E = mc<sup>2</sup> (1)</p>"),
        block("Text", [200, 435, 580, 460], "<p>where E is the energy, Mu¨ller's way.</p>"),
        block("SectionHeader", [200, 470, 320, 485], "<h3>1.1 Les orages</h3>"),
        block("Text", [200, 490, 580, 560], "<p>" + LONG + "</p>"),
        block("Footnote", [200, 700, 580, 715], "<p><sup>1</sup>Une note en bas de page.</p>"),
        block("SectionHeader", [200, 570, 300, 585], "<h2>2 Méthode</h2>"),
        block("Text", [200, 590, 580, 650], "<p>On compte les gouttes.</p>"),
        block("SectionHeader", [200, 655, 300, 670], "<h2>References</h2>"),
        block("ListGroup", [200, 672, 580, 698], "", [
            block("ListItem", [200, 672, 580, 684], "<li>1. Durand P. Les nuages. 2001.</li>"),
            block("ListItem", [200, 686, 580, 698], "<li>2. Martin A. La pluie. 2005.</li>"),
        ]),
    ]},
]


class NoPdf:
    """Stands for the PDF: metadata, and a white picture for every cut-out."""
    def __init__(self, _path):
        self.cuts = []

    def metadata(self):
        return {"Title": "La pluie et le beau temps", "Author": "Anne Martin, Andreas M#_#x00FC;ller"}

    def __len__(self):
        return len(PAGES)

    def cut(self, number, bbox, _box, width=None):
        self.cuts.append((number, bbox, width))
        return PNG, "png"


def converted(name="paper.epub"):
    p2e.Pages, p2e.marker_pages = NoPdf, lambda _path: PAGES
    epub = path(name)
    p2e.convert(path("paper.pdf"), epub)
    return epub


class Converter(unittest.TestCase):
    def setUp(self):
        p2e.Pages, p2e.marker_pages = NoPdf, lambda _path: PAGES

    def test_the_paper_has_a_title_page_and_a_chapter_per_section(self):
        title, authors, chapters, images = p2e.build(path("paper.pdf"))
        self.assertEqual(title, "La pluie et le beau temps")
        self.assertEqual(authors, "Anne Martin, Andreas Müller")
        self.assertEqual([t for t, _b in chapters], ["La pluie et le beau temps", "Abstract", "1 Introduction", "2 Méthode", "References"])
        front = "\n".join(chapters[0][1])
        self.assertIn('<p class="author">RESEARCH ARTICLE</p>', front)          # the banner is small print
        self.assertIn('<p class="author">Anne Martin¹, Paul Durand²</p>', front)
        # the sidebar of both pages, joined, at the end of the title page
        self.assertIn("lets anyone share it, listed in full", front)
        self.assertEqual(len(images), 2)        # the figure and the equation

    def test_a_paragraph_cut_by_the_page_is_joined_and_the_figure_follows_it(self):
        _title, _authors, chapters, _images = p2e.build(path("paper.pdf"))
        body = [b for b in dict(chapters)["1 Introduction"] if b]
        joined = next(i for i, b in enumerate(body) if "transportent" in b)
        self.assertIn("transportent l'eau des mers", body[joined])            # "trans-" + "portent"
        self.assertIn("dₖ fois par an", body[joined])
        self.assertTrue(body[joined + 1].startswith('<div class="figure"><img src="images/001.png" alt="Fig 1. Un nuage'))
        self.assertTrue(body[joined + 1].endswith('<p class="caption">Fig 1. Un nuage, vu d\'en dessous.</p>'))
        self.assertTrue(body[joined + 2].startswith('<div class="equation"><img src="images/002.png" alt="E = mc² (1)"'))
        self.assertEqual(body[joined + 3], "<p>where E is the energy, Müller's way.</p>")
        self.assertEqual(body[joined + 4], "<h2>1.1 Les orages</h2>")
        self.assertEqual(body[-1], '<p class="footnote">¹Une note en bas de page.</p>')     # the notes close the chapter

    def test_a_cut_out_is_as_wide_as_a_column_and_a_wide_one_as_the_text(self):
        pages = NoPdf("")
        p2e.Pages = lambda _path: pages
        p2e.build(path("paper.pdf"))
        widths = {round(bbox[0]): width for _n, bbox, width in pages.cuts}
        self.assertAlmostEqual(widths[210], 380)        # the column's width
        self.assertAlmostEqual(widths[260], 380)

    def test_the_epub_reads_as_a_book_with_its_pictures_and_small_print(self):
        epub = converted()
        book = rb.parse_book(epub, rb.EPUB, "x")
        self.assertEqual(book.title, "La pluie et le beau temps")
        self.assertEqual([c.title for c in book.chapters], ["La pluie et le beau temps", "Abstract", "1 Introduction", "2 Méthode", "References"])
        intro = book.chapters[2]
        pictures = [b.source for b in intro.blocks if isinstance(b, rb.ImageBlock)]
        self.assertEqual(pictures, ["OEBPS/images/001.png", "OEBPS/images/002.png"])
        kinds = {p.text: p.kind for b in intro.blocks if isinstance(b, rb.TextBlock) for p in b.paragraphs}
        self.assertEqual(kinds["Fig 1. Un nuage, vu d'en dessous."], rb.SMALL)
        self.assertEqual(kinds["¹Une note en bas de page."], rb.SMALL)
        with zipfile.ZipFile(epub) as z:
            self.assertEqual(z.namelist()[0], "mimetype")
            self.assertEqual(z.getinfo("mimetype").compress_type, zipfile.ZIP_STORED)

    def test_what_the_text_layer_gets_wrong(self):
        self.assertEqual(p2e.accents("Mu¨ller, Du¨sseldorf, don´t, cafe´"), "Müller, Düsseldorf, don´t, café")
        self.assertTrue(p2e.garbled("Tðt; s; kÞ ¼ fkðkÞ þ ftðtÞ"))
        self.assertFalse(p2e.garbled("Þórður and Guðrún went home"))
        self.assertEqual(p2e.inline('<p>x<sup>2</sup> + e<sup>-iπ</sup>, <a href="#r1">[1]</a></p>'), "x² + e<sup>-iπ</sup>, [1]")

    def test_chapters_by_numbers_or_by_levels(self):
        numbered = [(2, "Abstract"), (2, "1 Introduction"), (3, "1.1 Detail"), (2, "2. Related Work"), (4, "Encoder"),
                    (2, "3 Results"), (4, "References"), (2, "A. Proofs"), (2, "PASCAL VOC")]
        self.assertEqual(p2e.chapter_depths(numbered), [1, 1, 2, 1, 3, 1, 1, 1, 2])
        unnumbered = [(4, "RESEARCH"), (2, "Abstract"), (3, "Introduction"), (4, "Data"), (3, "Results"), (4, "References")]
        self.assertEqual(p2e.chapter_depths(unnumbered), [2, 1, 1, 2, 1, 1])

    def test_a_two_column_page_has_no_margin(self):
        page = {"children": [block("Text", [48, 70, 288, 700], "<p>" + LONG + "</p>"), block("Text", [306, 70, 549, 700], "<p>" + LONG * 2 + "</p>"),
                             block("SectionHeader", [48, 60, 120, 70], "<h2>3. Deep</h2>")]}
        left, column = p2e.main_column([page])
        self.assertEqual(left, 305)
        self.assertIsNone(p2e.margin_of(page, left, column))
        self.assertEqual(p2e.margin_of(PAGES[0], *p2e.main_column(PAGES)), 197)


# A novel, as Marker gives some: its chapter lines as plain text, a line of dialogue taken for a
# heading, lines it lost (empty blocks whose text only the PDF's text layer has), dialogue taken
# for a list with its dashes eaten, a printed table of contents, a proof's crop marks.
STORY = "Il marchait ainsi qu'au temps où il portait l'uniforme des hussards, la poitrine bombée, les jambes un peu entrouvertes. "


def novel_page(*blocks):
    return {"block_type": "Page", "bbox": [0, 0, 420, 600], "children": list(blocks)}


NOVEL = [
    novel_page(block("SectionHeader", [100, 200, 320, 230], "<h1>Bel-Ami</h1>"),
               block("TableOfContents", [60, 300, 360, 500], "<p>– I – 3 – II – 5</p>")),
    novel_page(block("SectionHeader", [120, 40, 300, 60], "<h1>Première Partie</h1>"),
               block("Text", [190, 80, 230, 95], "<p>– I –</p>"),
               block("Text", [60, 110, 360, 300], "<p>" + STORY * 3 + "</p>"),
               block("SectionHeader", [60, 310, 220, 325], "<h2>Il répondit sans hésiter :</h2>"),
               block("Text", [60, 330, 360, 400], "<p>« Je viens de me mettre sous la protection de saint Antoine. »</p>"),
               block("Text", [60, 410, 360, 425], "<p>❚❘❙❚❘❙❚❘❙</p>"),
               block("Text", [60, 430, 360, 445], ""),
               block("Text", [60, 450, 360, 560], "<p>" + STORY + "Il était tard, comme il disait,</p>"),
               block("Text", [60, 562, 360, 580], "<p>Mais personne ne l'écoutait plus dans la rue.</p>")),
    novel_page(block("Text", [190, 40, 230, 55], "<p>– II –</p>"),
               block("Text", [60, 70, 360, 200], "<p>" + STORY * 2 + "</p>"),
               block("ListGroup", [60, 210, 360, 250], "", [
                   block("ListItem", [60, 210, 360, 250], "<li> Oui, monsieur.</li>")])),
    novel_page(block("Text", [190, 40, 230, 55], "<p>– III –</p>"),
               block("Text", [60, 70, 360, 200], "<p>" + STORY + "</p>"),
               block("SectionHeader", [60, 210, 360, 225], "<h1>Table des matières</h1>"),
               block("Text", [60, 230, 360, 260], "<p>– I – 3</p>")),
]
NOVEL[3:3] = [novel_page(block("Text", [60, 40, 360, 560], "<p>" + STORY * 4 + "</p>")) for _ in range(6)]     # a book's length
LAYER = {(1, 430): "« Où vas-tu ? »", (1, 410): "❚❘❙❚❘❙❚❘❙",
         (2, 210): "– Oui, monsieur.\r\n– Mais qui êtes-vous ?\r\n« Personne. »"}


class NovelPdf(NoPdf):
    outlined = []

    def metadata(self):
        return {"Title": "Bel-Ami", "Author": "Guy de Maupassant"}

    def __len__(self):
        return len(NOVEL)

    def text_in(self, number, bbox):
        return LAYER.get((number, round(bbox[1])), "")

    def outline(self):
        return self.outlined


class Book(unittest.TestCase):
    def setUp(self):
        p2e.Pages, p2e.marker_pages = NovelPdf, lambda _path: NOVEL
        NovelPdf.outlined = []

    def text_of(self, chapters):
        return "\n".join("\n".join(b for b in body if b) for _t, body in chapters)

    def test_a_novel_without_bookmarks_has_its_chapters_and_all_its_lines(self):
        title, _authors, chapters, images = p2e.build(path("bel-ami.pdf"))
        self.assertEqual(title, "Bel-Ami")
        # "– I –" lines open the chapters; the printed contents are gone, the reader has its own
        self.assertEqual([t for t, _b in chapters], ["Bel-Ami", "Première Partie", "– I –", "– II –", "– III –"])
        text = self.text_of(chapters)
        self.assertNotIn("3 – II – 5", text)
        self.assertNotIn("Table des matières", text)
        # a line of dialogue is not a heading; what Marker lost comes from the text layer, as text
        self.assertIn("<p>Il répondit sans hésiter :</p>", text)
        self.assertIn("<p>« Où vas-tu ? »</p>", text)
        self.assertEqual(images, [])
        self.assertNotIn("❚", text)
        # dialogue taken for a list: a line each, with its dash
        self.assertIn("<p>– Oui, monsieur.</p>\n<p>– Mais qui êtes-vous ?</p>\n<p>« Personne. »</p>", text)
        # two paragraphs of the same page stay two, whatever their last and first words
        self.assertIn("comme il disait,</p>\n<p>Mais personne", text)

    def test_the_bookmarks_give_the_chapters(self):
        NovelPdf.outlined = [(0, "Première Partie", 1), (1, "– I –", 1), (1, "– II –", 2), (1, "Épilogue", 9)]
        _title, _authors, chapters, _images = p2e.build(path("bel-ami.pdf"))
        # a bookmark with no line of its own opens its chapter at the top of its page; "– III –",
        # not a bookmark, is a line of that chapter
        self.assertEqual([t for t, _b in chapters], ["Bel-Ami", "Première Partie", "– I –", "– II –", "Épilogue"])
        self.assertIn("<p>Il répondit sans hésiter :</p>", self.text_of(chapters))

    def test_bookmarks_numbered_otherwise_than_the_headings_and_what_they_leave_out(self):
        pieces = [("h", 2, "Abstract", 0), ("p", "Texte.", "", 0, None), ("h", 1, "CHAPTER THREE: Catalogs", 1),
                  ("p", "Texte.", "", 1, None), ("h", 2, "Let's pause for a moment.", 1), ("h", 2, "Film", 1), ("h", 2, "References", 2)]
        out, depth = p2e.by_outline(pieces, [(0, "3: Catalogs", 1), (1, "Film", 1)], 40)
        headings = [(p[2], d) for p, d in zip([p for p in out if p[0] == "h"], depth)]
        self.assertEqual(headings, [("Abstract", 1), ("CHAPTER THREE: Catalogs", 1), ("Film", 1), ("References", 1)])
        self.assertIn(("p", "Let's pause for a moment.", "", 1, None), out)


class Shelf(unittest.TestCase):
    def settle(self, main, until, what, seconds=20):
        end = time.time() + seconds
        while time.time() < end:
            APP.processEvents()
            if until():
                return
            time.sleep(0.02)
        self.fail("no end to " + what)

    def test_a_pdf_waits_for_the_converter_then_becomes_a_book_of_the_shelf(self):
        pdf = path("Un article.pdf")
        with open(pdf, "wb") as fh:
            fh.write(b"%PDF-1.4\n%made up\n")
        made = converted("made.epub")
        set_up, steps = [], []

        def fake_set_up(step):
            step(1, 2)
            os.makedirs(rb.PAPERS_ENV, exist_ok=True)
            with open(os.path.join(rb.PAPERS_ENV, "ready"), "w") as fh:
                fh.write(rb._pins())
            set_up.append(True)

        def fake_convert(source, step):
            self.assertEqual(source, pdf)
            for s in ("models", "pages", "book"):
                step(s)
            steps.append(source)
            out = path("out.epub")
            with open(made, "rb") as a, open(out, "wb") as b:
                b.write(a.read())
            return out

        rb.set_up_converter, rb.convert_paper = fake_set_up, fake_convert
        main = rb.Main()
        main.resize(760, 900)
        main.show()
        self.assertFalse(rb.converter_ready())
        # the open dialog says a PDF is turned into an EPUB, and so does the empty shelf
        asked = []
        real = rb.QtWidgets.QFileDialog.getOpenFileName
        rb.QtWidgets.QFileDialog.getOpenFileName = lambda *a: asked.append(a[3]) or ("", "")
        try:
            main.pick_book()
        finally:
            rb.QtWidgets.QFileDialog.getOpenFileName = real
        self.assertIn(rb._("books, or a PDF to turn into an EPUB"), asked[0])
        self.assertIn("%s (*.pdf)" % rb._("a PDF, turned into an EPUB"), asked[0])
        self.assertTrue(any("EPUB" in r.title for r in main.rows))
        main.import_files([pdf])
        self.assertEqual(main.papers, [pdf])
        titles = [r.title for r in main.rows]
        self.assertIn(rb._("A PDF is not read as it is: it is turned into an EPUB, a book of the shelf, its figures, tables and equations as pictures; the PDF itself is left as it was. The converter is set up once: about 2 GB downloaded."), titles)
        self.assertIn(rb._("set up the converter"), titles)
        row = next(r for r in main.rows if r.title == rb._("set up the converter"))
        self.assertEqual(row.secondary, rb.n_papers(1))
        row.action()
        self.settle(main, lambda: main.screen[0] == rb.BOOK, "the conversion")
        self.assertEqual((set_up, steps, main.papers, main.paper_error), ([True], [pdf], [], ""))
        entry = main.library.get(main.screen[1])
        self.assertEqual(entry["title"], "La pluie et le beau temps")
        self.assertEqual(entry["sourceName"], "Un article.epub")      # the name it will have on the drive
        # a paper that fails says so on the shelf, and the next one is not held up
        rb.convert_paper = lambda _s, _step: (_ for _ in ()).throw(IOError("no text"))
        main.import_files([pdf])
        self.settle(main, lambda: main.paper_error, "the failure")
        self.assertIn("no text", main.paper_error)
        self.assertIn(main.paper_error, [r.title for r in main.rows])
        main.close()

    def test_a_picture_opens_on_the_whole_window_zooms_and_closes(self):
        main = rb.Main()
        main.resize(760, 900)
        main.show()
        entry = main.library.add(converted("view.epub"), "view.epub")
        main.open_entry(entry, from_home=True)
        reader = main.reader
        self.settle(main, lambda: reader.book is not None, "the book")
        reader.go_to(2, 0)
        APP.processEvents()
        pages = reader.layout_pages()
        page = next(i for i, pg in enumerate(pages) if any(isinstance(x, rb.Picture) for x in pg))
        reader.page = page
        piece = next(x for x in pages[page] if isinstance(x, rb.Picture))
        _font, area = reader.frame()
        at = rb.QtCore.QPoint(area.left() + area.width() // 2, area.top() + piece.y + piece.height // 2)
        self.assertEqual(reader.picture_at(at), piece.source)
        self.assertIsNone(reader.picture_at(rb.QtCore.QPoint(area.left() + 2, area.top() + piece.y + piece.height + 30)))
        for kind in (rb.QtCore.QEvent.MouseButtonPress, rb.QtCore.QEvent.MouseButtonRelease):
            APP.sendEvent(reader, rb.QtGui.QMouseEvent(kind, rb.QtCore.QPointF(at), rb.QtCore.Qt.LeftButton,
                                                       rb.QtCore.Qt.LeftButton, rb.QtCore.Qt.NoModifier))
        view = next(v for v in main.findChildren(rb.PictureView) if v.isVisible())
        self.assertEqual(view.geometry(), main.rect())
        fitted = view.scale
        view.zoom(2.0, rb.QtCore.QPointF(100, 100))
        self.assertAlmostEqual(view.scale, fitted * 2)
        QtTest.QTest.keyClick(view, rb.QtCore.Qt.Key_0)
        self.assertAlmostEqual(view.scale, fitted)
        QtTest.QTest.keyClick(view, rb.QtCore.Qt.Key_Escape)
        self.assertFalse(view.isVisible())
        self.assertEqual(main.screen[0], rb.BOOK)          # still in the book
        main.close()


if __name__ == "__main__":
    unittest.main()
