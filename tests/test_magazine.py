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

    def test_the_end_of_the_article_before_goes_first_from_under_a_column(self):
        # the band at the foot of the page is the end of the article before, under the three
        # columns of a full-page column (The Economist marks its first line ▸, its last ■)
        rubric = box("rubric", 232, 64, 334, 75, "BACK STORY", "BACK STORY")
        head = box("head", 193, 81, 373, 99, "The talentless Mr Ripleys", "The talentless Mr Ripleys")
        c1 = box("body", 37, 143, 191, 592, "HE IS A philandering tech baron", "distrusts her son’s brassy")
        c2 = box("body", 203, 143, 363, 412, "new love interest.", "So did many of")
        c3 = box("body", 375, 143, 529, 592, "their predecessors:", "by and large, they don’t.")
        t1 = box("body", 31, 613, 191, 732, "sinated, and Christian", "Marine barracks, killing")
        t2 = box("body", 203, 613, 363, 732, "hundreds. Kerr’s murder", "in 1982, defend\x02")
        t3 = box("body", 375, 613, 535, 730, "ing Israel’s invasion", "learn from them. ■")
        order = m2e.xy_order([rubric, head, c1, c2, c3, t1, t2, t3])
        self.assertEqual(order, [rubric, head, c1, c2, c3, t1, t2, t3])
        m2e.END_MARK = "■"
        try:
            self.assertEqual(m2e.tail_first(list(order), "president-elect was assas\x02"), [t1, t2, t3, rubric, head, c1, c2, c3])
            t1.lines[0].continued = True        # the sign read: the same, whatever the text says
            self.assertEqual(m2e.tail_first(list(order), "killed or wounded.", jumps=True), [t1, t2, t3, rubric, head, c1, c2, c3])
        finally:
            m2e.END_MARK = ""

    def test_a_column_of_the_article_before_then_the_next_one_in_bands(self):
        # the article before fills the left column and the top of the two others; the next one's
        # headline spans those two only: that column, then the rest in bands
        a1 = box("body", 31, 53, 192, 442, "its spending plans.", "Mr Healey could have")
        a2 = box("body", 203, 53, 363, 232, "gone much further.", "the chancellor made the")
        a3 = box("body", 375, 53, 535, 232, "system more complicated.", "only goals win games. ■")
        rubric = box("rubric", 209, 253, 258, 261, "Energy policy", "Energy policy")
        head = box("head", 209, 266, 367, 284, "Danger! Low voltage", "Danger! Low voltage")
        b2 = box("body", 209, 343, 362, 722, "BRITISH HOUSEHOLDS and busi\x02", "zero-carbon sources by")
        b3 = box("body", 375, 343, 529, 722, "2030, which looks", "if the lights go off.")
        m2e.END_MARK = "■"
        try:
            order = m2e.xy_order([b3, head, a3, b2, rubric, a2, a1])
        finally:
            m2e.END_MARK = ""
        self.assertEqual(order, [a1, a2, a3, rubric, head, b2, b3])

    def test_a_justified_line_cut_by_wide_gaps_is_one_line(self):
        def row(text, x, base, font="EconomistSerif-Light"):
            out = []
            for c in text:
                if c != " ":
                    out.append(m2e.Char(c, x, base - 8, x + 5, base + 2, base, 9.0, font))
                x += 5 if c != " " else 3
            return out
        # the words of a line set wide apart, under a line that spans the column
        lines = m2e.lines_of(row("metrics such as economic competitive", 375, 400) + row("ness,", 375, 410)
                             + row("intercity", 410, 410) + row("mobility,", 470, 410))
        self.assertEqual([l.text for l in lines], ["metrics such as economic competitive", "ness, intercity mobility,"])
        # the last lines of two columns' paragraphs, as near: apart
        lines = m2e.lines_of(row("the end of it", 31, 400) + row("all.", 31, 410) + row("goes on and on", 80, 400) + row("ting", 80, 410))
        self.assertEqual([l.text for l in lines], ["the end of it", "all.", "goes on and on", "ting"])

    def test_the_signs_of_a_jump_are_read_off_the_lines(self):
        def row(text, x, base, font="EconomistSerif-Light"):
            out = []
            for c in text:
                if c != " ":
                    out.append(m2e.Char(c, x, base - 8, x + 5, base + 2, base, 9.0, font))
                x += 5 if c != " " else 3
            return out
        lines = m2e.mark_jumps(m2e.lines_of(row("▸", 22, 400) + row("sinated, and Christian", 31, 400)
                                            + row("president-elect was assas-", 375, 723) + row("⏩", 503, 723)
                                            + row("would do well to learn from them.", 375, 500) + row("■", 545, 500)), "▸", "⏩", "■")
        self.assertEqual([(l.text, l.continued, l.jumps) for l in lines],
                         [("sinated, and Christian", True, False), ("president-elect was assas-", False, True),
                          ("would do well to learn from them. ■", False, False)])
        lines = m2e.mark_jumps(m2e.lines_of(row("▸ its spending plans.", 22, 53)), "▸", "⏩", "■")
        self.assertEqual([(l.text, l.continued, round(l.x0)) for l in lines], [("its spending plans.", True, 30)])

    def test_two_facing_pages_are_read_in_bands_a_page_at_a_time(self):
        # a headline across the fold (at 892), the article's columns on both pages; under a second
        # headline across, the next article; a column at the left edge runs on past that headline
        h1 = box("head", 300, 100, 1300, 140, "De Keir Starmer", "relève de la garde")
        side_h = box("head", 45, 300, 246, 340, "Chronique", "libérale (II)")
        s1 = box("body", 45, 350, 246, 760, "La recommandation", "il y en a.")
        s2 = box("body", 45, 780, 246, 1000, "Pour accoucher", "la tyrannie. »")
        l1 = box("body", 300, 160, 560, 700, "Monsieur Andrew", "ne va plus.")
        r1 = box("body", 934, 160, 1189, 700, "Ces politiques", "la même chose. »")
        h2 = box("head", 300, 768, 1300, 800, "Le soutien intéressé", "de Londres à Kiev")
        l2 = box("body", 300, 820, 560, 1000, "C’est un labyrinthe", "indispensable.")
        r2 = box("body", 934, 820, 1189, 1000, "Les tories", "sa reconstruction.")
        order = m2e.sheet_order([r2, l2, h2, r1, l1, s2, s1, side_h, h1], 892)
        at = {id(b): i for i, b in enumerate(order)}
        self.assertEqual(at[id(s2)], at[id(s1)] + 1)          # the side column, whole
        self.assertLess(at[id(h1)], at[id(l1)])
        self.assertLess(at[id(l1)], at[id(r1)])             # the left page, then the right
        self.assertLess(at[id(r1)], at[id(h2)])             # before the next article
        self.assertLess(at[id(s2)], at[id(h2)])
        self.assertEqual([at[id(h2)] < at[id(l2)], at[id(l2)] < at[id(r2)]], [True, True])

    def test_an_articles_last_column_beside_the_next_piece_goes_on_from_the_word_cut(self):
        # a review in three columns, a shorter one set under its first two: the third column is
        # read after the short piece, unless the word cut at the second's foot says otherwise
        if not m2e._dictionary("fr"):
            self.skipTest("no French word list")
        c1 = box("body", 70, 790, 263, 946, "’ai pris, du premier", "de la même année.")
        c2a = box("body", 279, 790, 473, 878, "« Que de mensonges André »", "même pleurer…»")
        c2b = box("body", 280, 890, 473, 948, "«Nadja n’est pas un roman", "familiaux, corres\x02")
        rubric = box("rubric", 42, 974, 216, 990, "Roman graphique", "Roman graphique")
        head = box("head", 87, 1005, 218, 1050, "Martin Eden", "à Waikiki")
        m1 = box("body", 70, 1073, 263, 1291, "ACK London à Hawaï", "George Freeth, «un")
        m2 = box("body", 280, 1226, 473, 1244, "dieu vivant», première légende", "est un métis.")
        sig_m = box("sig", 397, 1249, 464, 1256, "Daniel Matias.", "Daniel Matias.")
        c3 = box("body", 490, 790, 674, 898, "pondances accessibles(3).", "plus insaisissable.")
        c4 = box("body", 488, 910, 674, 1068, "Ella Balaert veut", "répond Balaert.")
        sig_c = box("sig", 552, 1183, 666, 1190, "Philippe Pataud Célérier.", "Philippe Pataud Célérier.")
        m2e.VOCAB = m2e.Vocabulary("fr")
        try:
            order = m2e.repair_flow([c1, c2a, c2b, rubric, head, m1, m2, sig_m, c3, c4, sig_c])
        finally:
            m2e.VOCAB = None
        self.assertEqual(order, [c1, c2a, c2b, c3, c4, sig_c, rubric, head, m1, m2, sig_m])


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
