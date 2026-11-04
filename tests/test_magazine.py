"""Magazines in PDF: magazine2epub.py's rules on made-up lines and boxes (no PDF needed — the
issues themselves cannot be shipped), and the EPUB it writes as the reader reads it: a magazine,
its articles with section, title and author."""
import importlib.util
import os
import sys
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = tempfile.mkdtemp(prefix="readers-books-magazine-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "data")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m2e = load("magazine2epub", "magazine2epub.py")


def box(kind, x0, top, x1, bottom, first="Text", last="text."):
    class L:
        def __init__(self, text):
            self.text, self.size = text, 9
    b = m2e.Box(kind, x0, top, x1, bottom, [L(first), L(last)])
    return b


class Words(unittest.TestCase):
    def test_a_word_cut_at_a_line_end_keeps_its_hyphen_only_where_it_has_one(self):
        v = m2e.Vocabulary()
        v.learn("telecoms firm white collar workers a long-awaited Modi report")
        self.assertFalse(v.mend("a te", "lecoms firm"))         # a word cut in two
        self.assertFalse(v.mend("Mr Mo", "di for"))
        self.assertFalse(v.mend("advance", "ment in"))          # a suffix
        self.assertTrue(v.mend("long", "awaited prospectus"))    # met with its hyphen
        self.assertTrue(v.mend("white", "collar jobs"))         # two words, the whole is none
        self.assertTrue(v.mend("anti", "AfD firewall"))         # a capital after the cut
        self.assertTrue(v.mend("eye", "to-eye"))                # a compound goes on

    def test_a_headline_in_capitals_reads_in_title_case(self):
        self.assertEqual(m2e.smart_title("THE ALZHEIMER’S WARS"), "The Alzheimer’s Wars")
        self.assertEqual(m2e.smart_title("THEATRE OF WAR"), "Theatre of War")
        self.assertEqual(m2e.smart_title("Lula scares the markets"), "Lula scares the markets")


class ReadingOrder(unittest.TestCase):
    def test_a_band_across_the_page_then_its_columns(self):
        # an article in two columns, then a headline across the page and the next article's columns
        a1 = box("body", 30, 50, 270, 430, "large economy", "is welcome")
        a2 = box("body", 290, 50, 535, 430, "to high tariffs", "to thrive. ■")
        rubric = box("rubric", 240, 460, 330, 470, "Brazil’s comeback king", "Brazil’s comeback king")
        head = box("head", 160, 475, 406, 495, "Lula scares the markets", "Lula scares the markets")
        b1 = box("body", 30, 535, 277, 735, "Lula was a goner", "ran away.")
        b2 = box("body", 290, 535, 535, 735, "More significant", "extensive")
        order = m2e.xy_order([b2, head, a2, b1, rubric, a1])
        self.assertEqual(order, [a1, a2, rubric, head, b1, b2])

    def test_two_articles_side_by_side_are_read_one_after_the_other(self):
        # rubric, headline and standfirst of each at the same heights: not one band each
        r1, h1 = box("rubric", 32, 54, 93, 62), box("head", 32, 67, 111, 80)
        s1, t1 = box("stand", 32, 123, 188, 142), box("body", 31, 153, 192, 552, "According", "the market")
        t2 = box("body", 203, 233, 364, 730, "when required", "lower.")
        r2, h2 = box("rubric", 376, 54, 417, 60), box("head", 376, 66, 495, 100)
        s2, u = box("stand", 376, 123, 516, 142), box("body", 376, 153, 536, 392, "Eight months", "peak. ■")
        order = m2e.xy_order([r2, h2, s2, u, r1, h1, s1, t1, t2])
        self.assertEqual(order, [r1, h1, s1, t1, t2, r2, h2, s2, u])

    def test_the_end_of_the_article_before_goes_first(self):
        head = box("head", 36, 362, 362, 379, "COMMON SCAMS", "COMMON SCAMS")
        body = box("body", 35, 431, 193, 742, "The doorbell rings", "calls you up.")
        tail = box("body", 374, 35, 532, 58, "ping the floor and", "for quitting time.")
        order = m2e.tail_first([head, body, tail], "watching the clock and drop-")
        self.assertEqual(order[0], tail)


def chars(text, x=10.0, advance=6.0, gap=0.0, size=10.0, font="HelveticaNeueLTPro-Bd-SC750"):
    """Glyphs on one baseline, `gap` points apart (a letter-spaced line when it is wide)."""
    out = []
    for c in text:
        if c == " ":
            x += advance
            continue
        out.append(m2e.Char(c, x, 100, x + advance, 110, 108, size, font))
        x += advance + gap
    return out


class Diplo(unittest.TestCase):
    def test_a_letter_spaced_line_reads_as_words(self):
        line = m2e.Line(chars("Par  notre  envoyé", gap=2.5))
        self.assertEqual(line.text, "Par notre envoyé")
        # a formula's few letters among spaces are not letter-spaced text
        self.assertEqual(m2e.Line(chars("x + y = z", gap=0.2, font="Times")).text.replace(" ", ""), "x+y=z")

    def test_words_a_ligature_cut_are_mended_and_others_left(self):
        if not m2e._dictionary("fr"):
            self.skipTest("no French word list")
        self.assertEqual(m2e.mend_words("Intelligence artifi cielle"), "Intelligence artificielle")
        self.assertEqual(m2e.mend_words("une lourdeur jugée ine cace"), "une lourdeur jugée inefficace")
        self.assertEqual(m2e.mend_words("le <i>système édu catif</i>"), "le <i>système éducatif</i>")
        self.assertEqual(m2e.mend_words("il a ce que Jean Dupont veut"), "il a ce que Jean Dupont veut")

    def test_bylines_and_issue_date(self):
        self.assertEqual(m2e.clean_byline("Par notre envoyé spécial Pierre Daum *"), "Pierre Daum")
        self.assertEqual(m2e.clean_byline("Par Magali Della Sudda * et Grégory Rzepski"), "Magali Della Sudda et Grégory Rzepski")
        d = m2e.Diplo()
        date = d.issue_date(["No 872 - 73 e année. Novembre 2026 Mensuel - 28 pages"])
        self.assertEqual((date, d.iso(date)), ("Novembre 2026", "2026-11-01"))

    def article(self, title, items, page, byline=None, stand=None):
        a = m2e.Article(None)
        a.title, a.items, a.first_page = [title] if title else [], list(items), page
        a.byline, a.stand = [byline] if byline else [], [stand] if stand else []
        return a

    def test_an_article_from_the_front_page_goes_on_where_it_says(self):
        front = self.article("La dislocation de l’Occident", [("p", "Lorsque l’on dit M.\xa0Trump capable de s’allier avec"),
                                                             ("p", "<i>(Lire la suite page 13.)</i>")], 0, "Emmanuel Todd")
        other = self.article("Paix improbable", [("p", "Qui veut la paix ?")], 6)
        tail = self.article("La dislocation de l’Occident", [("p", "<i>(Suite de la première page.)</i> M.\xa0Poutine, on oublie"),
                                                            ("p", "Fin.")], 12)
        out = m2e.Diplo().stitch([front, other, tail])
        self.assertEqual([a.title[0] for a in out], ["La dislocation de l’Occident", "Paix improbable"])
        self.assertEqual([v for _k, v in out[0].items], ["Lorsque l’on dit M.\xa0Trump capable de s’allier avec M.\xa0Poutine, on oublie", "Fin."])

    def test_a_headline_read_apart_from_its_article_is_put_back(self):
        # the columns first (standfirst, byline), the headline on the facing page after them
        body = self.article(None, [("p", "Malgré mon admiration pour Cézanne, l’image a parcouru la"),
                                   ("picture", None)], 13, "Ernest Pignon-Ernest", "Dessinateur hors pair…")
        head = self.article("De Santiago à Port-au-Prince", [("p", "ville en flottant sur l’eau.")], 14)
        out = m2e.Diplo().stitch([body, head])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0].title, ["De Santiago à Port-au-Prince"])
        self.assertEqual(out[0].items[0], ("p", "Malgré mon admiration pour Cézanne, l’image a parcouru la ville en flottant sur l’eau."))
        self.assertEqual(out[0].items[1][0], "picture")

    def test_the_issue_is_french(self):
        path = os.path.join(TMP, "diplo.epub")
        m2e.write_epub(path, "Le Monde diplomatique — Novembre 2026", "Le Monde diplomatique", "2026-11-01", None,
                       [{"title": "Soudain, la solidarité", "category": "Dossier", "author": "Benoît Bréville",
                         "body": ["<h1>Soudain, la solidarité</h1>", "<p>Texte.</p>"]}], [], "fr")
        import zipfile
        with zipfile.ZipFile(path) as z:
            self.assertIn("<dc:language>fr</dc:language>", z.read("OEBPS/content.opf").decode())
            self.assertIn('xml:lang="fr"', z.read("OEBPS/chapter-01.xhtml").decode())


class Epub(unittest.TestCase):
    def test_the_issue_is_a_magazine_with_its_sections_titles_and_authors(self):
        rb = load("rb_magazine", "readers_books.py")
        chapters = []
        for cat, title, author in (("Leaders", "A bold PM with big ideas", None), ("Europe", "Here comes everyone", None),
                                   ("Profiles", "Theatre of War", "Joshua Yaffa")):
            a = m2e.Article(cat)
            a.title = [title]
            a.byline = [author] if author else []
            a.items = [("p", "First paragraph of %s." % title), ("p", "And a second one.")]
            t, body = m2e.chapter_html(a)
            chapters.append({"title": t, "category": cat, "author": author, "body": body})
        path = os.path.join(TMP, "issue.epub")
        m2e.write_epub(path, "The Economist — October 31st 2026", "The Economist", "2026-10-31", None, chapters, [])
        book = rb.parse_book(path, rb.EPUB, "issue")
        self.assertEqual(book.title, "The Economist — October 31st 2026")
        self.assertEqual([(a.category, a.title) for a in book.magazine],
                         [("Leaders", "A bold PM with big ideas"), ("Europe", "Here comes everyone"), ("Profiles", "Theatre of War")])
        self.assertEqual(book.magazine[2].author, "Joshua Yaffa")
        self.assertEqual(rb.magazine_key(book.title), "the economist")


if __name__ == "__main__":
    unittest.main()
