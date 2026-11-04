"""The parsers, the shelf, the credentials file, the pager and the library page, on books made up
for the purpose. The library page is driven against a small drive served by `rclone serve webdav`
(skipped without rclone); its screenshots go to $READERS_BOOKS_SHOTS when that is set."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
TMP = tempfile.mkdtemp(prefix="readers-books-test-")
os.environ["XDG_CONFIG_HOME"] = os.path.join(TMP, "config")
os.environ["XDG_DATA_HOME"] = os.path.join(TMP, "data")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tests"))
spec = importlib.util.spec_from_file_location("rb", os.path.join(HERE, "readers_books.py"))
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)
import make_books  # noqa: E402
from PyQt5 import QtTest  # noqa: E402

APP = rb.QtWidgets.QApplication.instance() or rb.QtWidgets.QApplication([])
rb.load_bundled_fonts()


def path(name):
    return os.path.join(TMP, name)


def laid_out(block, font, width, base=0):
    """A whole text block as one run, as the pager lays it out."""
    return rb.LaidBlock(block, 0, len(block.paragraphs), base, rb.Frame(font, rb.QtGui.QColor("#888"), width, 10000, None))


class Parsing(unittest.TestCase):
    def test_an_epub_gives_chapters_with_their_titles_and_pictures(self):
        p = make_books.epub(path("a.epub"))
        self.assertEqual(rb.detect(p, "a.epub"), rb.EPUB)
        book = rb.parse_book(p, rb.EPUB, "a")
        self.assertEqual(book.title, "Le Livre d'essai")
        self.assertEqual([c.title for c in book.chapters][:2], ["Chapitre 1", "Chapitre 2"])
        self.assertIsNone(book.magazine)
        first = book.chapters[0].blocks[0]
        self.assertEqual((first.paragraphs[0].kind, first.paragraphs[0].text), (rb.HEADING, "Chapitre 1 — La pluie"))
        second = book.chapters[1]
        pictures = [b.source for b in second.blocks if isinstance(b, rb.ImageBlock)]
        self.assertEqual(pictures, ["OEBPS/img/two.png"])
        last = second.blocks[-1].paragraphs
        self.assertEqual((last[0].kind, last[0].text), (rb.SMALL, "Une légende, en petit."))
        self.assertEqual(last[1].text, "Une ligne\npuis une autre, après un retour.")
        self.assertEqual(book.total, sum(c.length for c in book.chapters))

    def test_a_magazine_opens_on_its_articles(self):
        book = rb.parse_book(make_books.epub(path("m.epub"), "Le Journal", magazine=True), rb.EPUB, "m")
        self.assertEqual(len(book.magazine), 6)
        a = book.magazine[2]
        self.assertEqual((a.category, a.title, a.author, a.image), ("Culture", "Article numéro 3 & ses suites", "Auteur 3", "OEBPS/img/one.png"))
        self.assertEqual(book.chapters[a.chapter].title, "Article numéro 3 & ses suites")
        kinds = [p.kind for b in book.chapters[0].blocks if isinstance(b, rb.TextBlock) for p in b.paragraphs]
        self.assertEqual(kinds[:4], [rb.SMALL, rb.HEADING, rb.SMALL, rb.LEAD])

    def test_a_long_chapter_is_cut_into_parts_that_keep_its_name(self):
        ch = rb.Chapter("Long", [rb.TextBlock([rb.Para("mot " * 1000) for _i in range(8)])])
        parts, first = rb._split_long([rb.Chapter("Court", [rb.TextBlock([rb.Para("x")])]), ch])
        self.assertEqual(first, [0, 1])
        self.assertEqual([p.title for p in parts], ["Court", "Long", "Long · 2", "Long · 3", "Long · 4"])
        self.assertTrue(all(p.length <= 12100 for p in parts))

    def test_mobi_fb2_and_plain_text(self):
        m = make_books.mobi(path("b.mobi"))
        self.assertEqual(rb.detect(m, "b.mobi"), rb.MOBI)
        book = rb.parse_book(m, rb.MOBI, "b")
        self.assertEqual((book.title, [c.title for c in book.chapters]), ("Un Mobi", ["Premier", "Second"]))
        self.assertEqual(book.chapters[1].blocks[0].paragraphs[-1].text, "Fin — été.")
        f = make_books.fb2(path("c.fb2"))
        self.assertEqual(rb.detect(f, "c.fb2"), rb.FB2)
        book = rb.parse_book(f, rb.FB2, "c")
        self.assertEqual((book.title, [c.title for c in book.chapters]), ("Un FB2", ["Un", "Deux"]))
        t = make_books.txt(path("d.txt"))
        book = rb.parse_book(t, rb.detect(t, "d.txt"), "d")
        self.assertEqual([p.text for p in book.chapters[0].blocks[0].paragraphs],
                         ["Premier paragraphe.", "Second paragraphe,\nsur deux lignes.", "Troisième."])

    def test_palmdoc_compression(self):
        # a literal run, a space-and-letter pair, and a copy of what came before
        self.assertEqual(rb._palmdoc(bytes([0x61, 0x62, 0x63, 0xE4, 0x80, 0x2B])), b"abc dabc da")

    def test_what_cannot_be_read_says_so(self):
        with open(path("bad.epub"), "wb") as fh:
            fh.write(b"PK\x03\x04 not a zip")
        with self.assertRaises(rb.Unsupported):
            rb.parse_book(path("bad.epub"), rb.EPUB, "bad")
        with open(path("empty.txt"), "w") as fh:
            fh.write("  \n")
        with self.assertRaises(rb.Unsupported):
            rb.parse_book(path("empty.txt"), rb.TXT, "empty")


class Shelf(unittest.TestCase):
    def test_a_book_keeps_its_place_when_it_is_opened_again(self):
        lib = rb.Library()
        e = lib.add(make_books.epub(path("s.epub"), "Sur l'étagère"), "s.epub")
        self.assertTrue(os.path.exists(path("s.epub")))             # the original stays where it was
        self.assertEqual((e["title"], e["format"], e["magazine"], e["opened"]), ("Sur l'étagère", "EPUB", False, 0))
        lib.save_position(e["id"], 3, 420, 51)
        again = lib.add(path("s.epub"), "s.epub", source="ref-1")
        self.assertEqual((again["chapter"], again["charOffset"], again["progress"]), (3, 420, 51))
        self.assertEqual([b["id"] for b in lib.books if b["title"] == "Sur l'étagère"], [again["id"]])
        self.assertFalse(os.path.exists(os.path.join(rb.BOOKS_DIR, e["fileName"])))
        self.assertEqual(lib.by_source("ref-1")["id"], again["id"])
        self.assertEqual(rb.Library().get(again["id"])["charOffset"], 420)          # and it is on disk
        with self.assertRaises(Exception):
            lib.add(path("empty.txt"), "empty.txt")
        lib.remove(again["id"])
        self.assertIsNone(lib.get(again["id"]))

    def test_the_menu_of_the_shelf_opens_with_its_orders_and_leads_to_the_settings(self):
        # 1.5.0 and 1.6.0: the « order » submenu made the ⋮ menu fail before it showed — settings out of reach.
        main = rb.Main()
        menu = main.build_menu(main.menu_items)
        labels = [a.text() for a in menu.actions()]
        self.assertIn(rb._("settings"), labels)
        order = next(a for a in menu.actions() if a.text().startswith(rb._("order")))
        self.assertEqual(len(order.menu().actions()), len(rb.SHELF_ORDERS))
        next(a for a in menu.actions() if a.text() == rb._("settings")).trigger()
        self.assertEqual(main.screen[0], rb.SETTINGS)
        main.close()


class Themes(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(rb.CONFIG_FILE):
            os.remove(rb.CONFIG_FILE)

    def test_the_inks_come_first_then_the_plume_palettes_and_every_name_is_translated(self):
        keys = [p[0] for p in rb.PALETTES]
        self.assertEqual(keys, ["DARK", "LIGHT", "LAVANDE", "SAUGE", "NORDIQUE", "TERRACOTTA", "COQUETTE", "MILITANTE", "TORRIDE", "NATURE"])
        self.assertEqual([rb.next_theme(k) for k in keys], keys[1:] + keys[:1])
        self.assertEqual(rb.next_theme("bogus"), "DARK")
        for ink in ("DARK", "LIGHT"):                 # the inks look as they always did: the accent is the text colour
            self.assertEqual(rb.palette(ink)["accent"], rb.palette(ink)["fg"])
            self.assertEqual(rb.palette(ink)["on_accent"], rb.palette(ink)["bg"])
        self.assertEqual(rb.palette("TERRACOTTA"), {"bg": "#e6d9cc", "fg": "#2b211b", "accent": "#c25e38", "on_accent": "#ffffff",
                                                     "tile": "#fcf7f1", "tile2": "#c8b6a5", "press": "#c8b6a5", "tiles": True})
        self.assertEqual(rb.palette("bogus"), rb.palette("DARK"))
        for ink in ("DARK", "LIGHT"):                 # no tiles in the inks: text on the page, as always
            self.assertFalse(rb.palette(ink)["tiles"])
            self.assertEqual((rb.palette(ink)["tile"], rb.palette(ink)["press"]), (rb.palette(ink)["bg"], rb.palette(ink)["bg"]))
        self.assertTrue(all(rb.palette(k)["tiles"] for k in keys[2:]))
        for lang, table in rb.STRINGS.items():
            for key in keys:
                self.assertIn(rb.THEME_NAMES[key], table, "%s has no name for %s" % (lang, key))
        self.assertEqual(rb.rgba("#2b211b", 0.55), "rgba(43,33,27,0.55)")
        self.assertTrue(rb.is_dark("#1f1a2e") and not rb.is_dark("#e6d9cc"))

    def test_a_config_from_before_the_themes_keeps_its_ink(self):
        os.makedirs(rb.CONFIG_DIR, exist_ok=True)
        for saved, theme in (({"dark": False}, "LIGHT"), ({"dark": True}, "DARK"), ({}, "DARK"),
                             ({"theme": "SAUGE", "dark": True}, "SAUGE"), ({"theme": "bogus"}, "DARK")):
            with open(rb.CONFIG_FILE, "w") as fh:
                json.dump(saved, fh)
            self.assertEqual(rb.load_config()["theme"], theme, saved)

    def test_the_menu_entry_names_the_next_theme_and_moves_to_it(self):
        main = rb.Main()
        self.assertEqual(main.theme, "DARK")
        self.assertEqual(main.theme_item()[0], rb._("black on white"))
        main.next_theme()
        self.assertEqual((main.theme, main.colors["bg"], main.delegate.accent.name()), ("LIGHT", "#ffffff", "#000000"))
        self.assertEqual(main.theme_item()[0], rb._("lavender"))
        main.next_theme()
        self.assertEqual((main.theme, main.delegate.accent.name(), main.delegate.on_accent.name()), ("LAVANDE", "#b8a4ff", "#1f1a2e"))
        self.assertIn("background: #b8a4ff; color: #1f1a2e", main.styleSheet())
        self.assertTrue(main.delegate.tiles)          # a palette: the rows, buttons and menus are cards
        self.assertEqual((main.delegate.tile.name(), main.delegate.press.name()), ("#3b3352", "#5a4f78"))
        self.assertIn("QMenu { background: #3b3352", main.styleSheet())
        self.assertIn("border-radius: 10px", main.styleSheet())
        main.theme = "LIGHT"
        main.apply_style()
        self.assertFalse(main.delegate.tiles)         # an ink: no card anywhere
        self.assertNotIn("border-radius: 10px", main.styleSheet())
        saved = rb.load_config()
        self.assertEqual((saved["theme"], saved["dark"]), ("LAVANDE", True))
        main.close()


class Pages(unittest.TestCase):
    def test_every_line_is_on_one_page_and_no_page_overflows(self):
        book = rb.parse_book(make_books.epub(path("p.epub")), rb.EPUB, "p")
        store = rb.ImageStore(path("p.epub"))
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(18)
        for width, height in ((500, 700), (320, 410), (700, 300)):
            for chapter in book.chapters[:3]:
                pages = rb.paginate(chapter, rb.Frame(font, rb.QtGui.QColor("#888"), width, height, store))
                starts = [rb.page_start(p) for p in pages]
                self.assertEqual(starts, sorted(starts))
                self.assertEqual(len(set(starts)), len(starts))
                seen = {}
                for page in pages:
                    for piece in page:
                        if isinstance(piece, rb.Lines):
                            bottom = piece.y + piece.block.bottoms[piece.last] - piece.block.tops[piece.first]
                            for i in range(piece.first, piece.last + 1):
                                seen.setdefault(id(piece.block), []).append(i)
                        else:
                            bottom = piece.y + piece.height
                            self.assertLessEqual(piece.width, width)
                        self.assertLessEqual(bottom, height)
                for lines in seen.values():
                    self.assertEqual(lines, list(range(len(lines))))            # each line once, in order
                self.assertEqual(rb.page_for(pages, starts[-1]), len(pages) - 1)
                self.assertEqual(rb.page_for(pages, 1 << 30), len(pages) - 1)

    def test_the_characters_of_a_block_are_counted_as_the_layout_counts_them(self):
        block = rb.TextBlock([rb.Para("Titre", rb.HEADING), rb.Para("Un 😀 deux"), rb.Para("Trois\nquatre")])
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(16)
        laid = laid_out(block, font, 300)
        # one for one: the reader's own indent is a margin, not characters
        self.assertEqual(len(laid.layout.text().encode("utf-16-le")) // 2, block.length - 1)


class Credentials(unittest.TestCase):
    def test_export_merges_and_import_reads_our_section_or_a_neighbour_s(self):
        target = path("cred.json")
        with open(target, "w") as fh:
            json.dump({"format": "readers-credentials", "version": 1, "readers-notes": {"server": "https://dav.example/", "folder": "notes", "username": "u", "password": "p"}}, fh)
        cfg = {"url": "", "username": "", "password": ""}
        self.assertTrue(rb.import_credentials(cfg, target))             # from a neighbour
        self.assertEqual((cfg["url"], cfg["username"], cfg["password"]), ("https://dav.example/", "u", "p"))
        self.assertEqual(cfg["notes_url"], "https://dav.example/notes/")
        rb.export_credentials({"url": "https://drive.example/dav", "username": "moi", "password": "s", "notes_url": "https://drive.example/dav/Notes"}, target)
        with open(target) as fh:
            data = json.load(fh)
        self.assertEqual(data["readers-books"], {"url": "https://drive.example/dav", "username": "moi", "password": "s", "notes_url": "https://drive.example/dav/Notes"})
        self.assertIn("readers-notes", data)
        self.assertFalse(rb.import_credentials(cfg, target))
        self.assertEqual((cfg["url"], cfg["username"], cfg["notes_url"]), ("https://drive.example/dav", "moi", "https://drive.example/dav/Notes"))
        # a file that only names a share link says nothing a library can be made of
        with open(path("share.json"), "w") as fh:
            json.dump({"format": "readers-credentials", "readers-books": {"share": "https://kdrive.infomaniak.com/app/share/1/ab"}}, fh)
        with self.assertRaises(rb.NothingForUs):
            rb.import_credentials(dict(cfg), path("share.json"))
        with open(path("other.json"), "w") as fh:
            fh.write('{"hello": 1}')
        with self.assertRaises(rb.NotCredentials):
            rb.import_credentials(cfg, path("other.json"))
        with self.assertRaises(rb.NotCredentials):
            rb.export_credentials(cfg, path("other.json"))

    def test_what_the_drive_says_of_a_book(self):
        b = {"name": "Simenon - Le_chien_jaune.epub", "folder": "Romans/Maigret"}
        self.assertEqual((rb.remote_title(b), rb.remote_author(b), rb.remote_folder_name(b)),
                         ("Simenon - Le chien jaune", "Simenon", "Maigret"))
        self.assertEqual(rb.remote_author({"name": "Sans auteur.epub", "folder": "Romans/Maigret"}), "Maigret")
        self.assertTrue(rb.skip_folder(".cache") and rb.skip_folder("Trash") and not rb.skip_folder("Livres"))
        self.assertEqual([rb.n_books(n) for n in (1, 2)], ["1 book", "2 books"] if rb.LANG == "en" else [rb.n_books(1), rb.n_books(2)])


MULTISTATUS = b"""<?xml version="1.0" encoding="utf-8"?>
<D:multistatus xmlns:D="DAV:">
 <D:response><D:href>/dav/</D:href><D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop></D:propstat></D:response>
 <D:response><D:href>/dav/Romans/</D:href><D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype>
   <D:getlastmodified>Thu, 08 Oct 2026 10:00:00 GMT</D:getlastmodified></D:prop></D:propstat></D:response>
 <D:response><D:href>/dav/.cache/</D:href><D:propstat><D:prop><D:resourcetype><D:collection/></D:resourcetype></D:prop></D:propstat></D:response>
 <D:response><D:href>/dav/Un%20livre%20%2B%20un.epub</D:href><D:propstat><D:prop><D:resourcetype/>
   <D:getcontentlength>1234567</D:getcontentlength><D:getlastmodified>Thu, 08 Oct 2026 10:00:00 GMT</D:getlastmodified></D:prop></D:propstat></D:response>
 <D:response><D:href>/dav/notes.txt</D:href><D:propstat><D:prop><D:resourcetype/><D:getcontentlength>3</D:getcontentlength></D:prop></D:propstat></D:response>
</D:multistatus>"""


class FakeDrive:
    """A drive of three folders that refuses the login until told otherwise, and one folder
    that fails twice before it answers."""
    def __init__(self):
        self.locked = False
        self.calls = {}

    def roots(self):
        return ["/"]

    def folder_ref(self, path):
        return "/" + path

    def folder_path(self, ref):
        return ref.strip("/")

    def list_all(self):
        return None

    def list(self, folder):
        self.calls[folder] = self.calls.get(folder, 0) + 1
        if self.locked:
            raise rb.WrongLogin("wrong login")
        if folder == "/b" and self.calls[folder] < 3:
            raise IOError("HTTP 503")
        if folder == "/broken":
            raise IOError("HTTP 500")
        tree = {"/": (["/a", "/b", "/broken"], []), "/a": ([], [self.book("a", "Un.epub")]), "/b": ([], [self.book("b", "Deux.epub"), self.book("b", "Trois.mobi")])}
        return tree[folder]

    @staticmethod
    def book(folder, name):
        return {"name": name, "folder": folder, "ref": folder + "/" + name, "size": 1, "modified": 0}


class Drive(unittest.TestCase):
    def test_a_webdav_answer(self):
        dav = rb.WebDav("https://example.org/dav", "u", "p")
        import io
        items = dav._parse(io.BytesIO(MULTISTATUS), "https://example.org/dav/")
        self.assertEqual([i[0] for i in items if i[1]], ["https://example.org/dav/Romans/", "https://example.org/dav/.cache/"])
        books = [b for b in (dav._book(i) for i in items if not i[1]) if b]
        self.assertEqual(len(books), 1)
        self.assertEqual((books[0]["name"], books[0]["folder"], books[0]["size"]), ("Un livre + un.epub", "", 1234567))
        self.assertEqual(books[0]["modified"], 1791453600000)
        self.assertEqual(books[0]["ref"], "https://example.org/dav/Un%20livre%20%2B%20un.epub")

    def scan(self, remote, drive, cfg, fresh):
        original, rb.remote_for = rb.remote_for, lambda _cfg: drive
        pause, rb.RETRY_PAUSE = rb.RETRY_PAUSE, 0.01
        try:
            remote.scan(cfg, fresh)
            remote.thread.join(20)
        finally:
            rb.remote_for, rb.RETRY_PAUSE = original, pause

    def test_a_scan_retries_notes_what_failed_and_carries_on_after_a_refused_login(self):
        cfg = {"url": "https://example.org/dav", "username": "u", "password": "p"}
        drive, remote = FakeDrive(), rb.RemoteLibrary()
        remote.forget()
        drive.locked = True
        self.scan(remote, drive, cfg, True)
        self.assertIsInstance(remote.error, rb.WrongLogin)
        self.assertFalse(remote.index["complete"])
        self.assertEqual(remote.index["frontier"], ["/"])           # not lost: this is where it carries on
        drive.locked = False
        self.assertTrue(remote.matches(cfg))
        self.scan(remote, drive, cfg, False)
        self.assertIsNone(remote.error)
        self.assertTrue(remote.index["complete"])
        self.assertEqual(sorted(b["name"] for b in remote.index["books"]), ["Deux.epub", "Trois.mobi", "Un.epub"])
        self.assertEqual((remote.index["failed"], remote.index["folders"], drive.calls["/b"]), (["/broken"], 3, 3))
        self.assertEqual([f[:2] for f in remote.folders(cfg)], [("a", 1), ("b", 2)])
        self.assertEqual([f[:2] for f in remote.folders(dict(cfg, library_folders=["b"]))], [("b", 2)])
        self.assertEqual(rb.RemoteLibrary().index["failed"], ["/broken"])       # and it is on disk

    def test_the_transcripts_folder_is_looked_at_again_without_a_scan(self):
        cfg = {"url": "https://example.org/dav", "username": "u", "password": "p"}

        class Drive:
            base = "https://example.org/dav/"

            def folder_ref(self, path):
                return self.base + rb.quote(path, safe="") + "/"

            def list(self, folder):
                if folder == self.base + "transcriptions/":
                    return [self.base + "transcriptions/Une%20cha%C3%AEne/"], []
                if folder.endswith("/Une%20cha%C3%AEne/"):
                    return [], [{"name": "Nouveau.epub", "folder": "transcriptions/Une chaîne", "ref": "new", "size": 1, "modified": 0}]
                raise IOError("HTTP 404")

        remote = rb.RemoteLibrary()
        remote.index = dict(rb.EMPTY_INDEX, source=rb.source_key(cfg), scannedAt=1, books=[
            {"name": "Roman.epub", "folder": "Romans", "ref": "r", "size": 1, "modified": 0},
            {"name": "Parti.epub", "folder": "transcriptions/Ancien", "ref": "old", "size": 1, "modified": 0}])
        original, rb.remote_for = rb.remote_for, lambda _cfg: Drive()
        try:
            remote.refresh_folder(cfg)
            for _i in range(100):
                if not remote.refreshing:
                    break
                rb.time.sleep(0.02)
            self.assertEqual(sorted(b["ref"] for b in remote.index["books"]), ["new", "r"])
            remote.refresh_folder(cfg, "nowhere")          # a folder that is not there takes nothing else with it
            rb.time.sleep(0.2)
            self.assertEqual(sorted(b["ref"] for b in remote.index["books"]), ["new", "r"])
        finally:
            rb.remote_for = original


class Highlights(unittest.TestCase):
    def test_a_place_in_the_chapter_and_its_place_on_the_page(self):
        block = rb.TextBlock([rb.Para("Un"), rb.Para("Deux\ntrois"), rb.Para("Quatre 😀 cinq")])
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(16)
        laid = laid_out(block, font, 400, base=100)
        text = rb.Text16(laid.layout.text())
        chapter = rb.Text16(rb.chapter_text(rb.Chapter("c", [block])))
        self.assertEqual(chapter.length, block.length)
        for word in ("Un", "Deux", "trois", "Quatre", "cinq"):
            at = rb.u16(rb.chapter_text(rb.Chapter("c", [block])).split(word)[0])
            self.assertEqual(text.cut(laid.to_laid(100 + at), laid.to_laid(100 + at) + len(word)), word)
            self.assertEqual(laid.to_chapter(laid.to_laid(100 + at)), 100 + at)
        # the indented lines begin further on the page, with nothing put in the text
        self.assertEqual(laid.layout.lineAt(0).x(), 0)
        self.assertGreater(laid.layout.lineAt(1).x(), 0)

    def test_a_passage_is_widened_to_whole_words(self):
        t = rb.Text16("Il pleuvait sur la ville, aujourd'hui.\n")
        self.assertEqual(t.cut(*t.words(5, 13)), "pleuvait sur")
        self.assertEqual(t.cut(*t.words(13, 5)), "pleuvait sur")
        self.assertEqual(t.cut(*t.words(27, 30)), "aujourd'hui")
        self.assertEqual(t.cut(*t.words(24, 26)), ",")

    def test_two_devices_fold_their_highlights(self):
        a = rb.new_highlight(1, 10, 20, "dix mots")
        b = rb.new_highlight(0, 5, 9, "cinq")
        newer = dict(a, comment="vu", modified=a["modified"] + 5)
        removed = dict(b, deleted=True, text="", modified=b["modified"] + 9)
        merged = rb.merge_highlights([a, b], [newer, removed])
        self.assertEqual([(h["id"], h.get("comment"), h["deleted"]) for h in merged], [(b["id"], "", True), (a["id"], "vu", False)])
        self.assertEqual(rb.merge_highlights([newer, removed], [a, b]), merged)         # whichever side asks
        self.assertEqual([h["id"] for h in rb.live_highlights(merged)], [a["id"]])

    def test_the_note_lists_the_passages_in_the_order_of_the_book(self):
        hs = [rb.new_highlight(2, 5, 9, "plus  loin\ndans le livre", "Une remarque."), rb.new_highlight(0, 50, 60, "au début"),
              dict(rb.new_highlight(0, 1, 2, "ôté"), deleted=True)]
        opening, closing = rb._QUOTES.get(rb.LANG, ("«", "»"))
        self.assertEqual(rb.note_text("Simenon - Le chien jaune.epub", hs),
                         "Simenon - Le chien jaune\n\n%sau début%s\n\n%splus loin dans le livre%s\n\nUne remarque.\n" % (opening, closing, opening, closing))
        self.assertEqual(rb.note_file_name('Un: "titre"?.epub'), "Un titre.txt")

    def test_a_highlight_follows_its_words(self):
        book = rb.Book("b", [rb.Chapter("c", [rb.TextBlock([rb.Para("Un mot de plus. Il pleuvait sur la ville.")])])])
        good = rb.new_highlight(0, 16, 27, "Il pleuvait")
        moved = rb.new_highlight(0, 0, 11, "Il pleuvait")
        lost = rb.new_highlight(0, 0, 5, "absent")
        shown = rb.anchor_highlights([good, moved, lost], book)
        self.assertEqual([(h["start"], h["end"]) for h in shown], [(16, 27), (16, 27)])

    def test_a_passage_goes_to_the_clipboard_as_it_is(self):
        main = rb.Main()
        main.copy_text("Il pleuvait sur la ville.")
        self.assertEqual(rb.QtWidgets.QApplication.clipboard().text(), "Il pleuvait sur la ville.")
        for lang, table in rb.STRINGS.items():
            self.assertIn("copy", table, lang)
        main.close()

    def test_where_the_notes_go(self):
        cfg = {"url": "https://dav.example/", "username": "u", "password": "p", "notes_url": "https://dav.example/Notes"}
        self.assertEqual(rb.notes_account(cfg), ("https://dav.example/Notes/", "u", "p"))
        self.assertIsNone(rb.notes_account(dict(cfg, notes_url="")))
        self.assertEqual(rb.notes_account(dict(cfg, notes_username="n", notes_password="q")), ("https://dav.example/Notes/", "n", "q"))
        entry = {"id": "x", "source": "https://dav.example/Livres/Un.epub"}
        self.assertEqual(rb.sidecar_address(cfg, entry), "https://dav.example/Livres/Un.epub.highlights.json")
        # a book opened from a file, or fetched through a share link by an older version, has none
        self.assertIsNone(rb.sidecar_address(cfg, {"id": "x", "source": None}))
        self.assertIsNone(rb.sidecar_address(cfg, {"id": "x", "source": "4242"}))
        self.assertIsNone(rb.sidecar_address(dict(cfg, password=""), entry))
        text = json.dumps({"format": "readers-credentials", "readers-notes": {"server": "https://dav.example", "folder": "Mes notes", "username": "n", "password": "q"}})
        self.assertEqual(rb.read_notes_account(text), {"notes_url": "https://dav.example/Mes%20notes/", "notes_username": "n", "notes_password": "q"})


def book(folder, name):
    return {"name": name, "folder": folder, "ref": "ref:%s/%s" % (folder, name), "size": 1, "modified": 1}


class Folders(unittest.TestCase):
    """The choice of folders and the merge of one folder listed again into the books known so far."""
    def test_nothing_chosen_is_the_whole_drive(self):
        self.assertTrue(rb.in_library([], ""))
        self.assertTrue(rb.in_library([], "a/b"))
        self.assertEqual(rb.library_roots([]), [""])

    def test_a_folder_left_out_is_out_with_what_is_inside_whatever_is_chosen(self):
        excluded = ["Books/Old"]
        self.assertTrue(rb.left_out(excluded, "Books/Old"))
        self.assertTrue(rb.left_out(excluded, "Books/Old/Deeper"))
        self.assertFalse(rb.left_out(excluded, "Books/Older"))      # a prefix of the name is not inside
        self.assertFalse(rb.left_out(excluded, "Books"))
        self.assertFalse(rb.left_out([], "Books/Old"))
        # the whole drive, less that folder
        self.assertTrue(rb.in_library([], "Books", excluded))
        self.assertFalse(rb.in_library([], "Books/Old/Deeper", excluded))
        # a chosen folder with a part of it left out
        self.assertTrue(rb.in_library(["Books"], "Books/Maigret", excluded))
        self.assertFalse(rb.in_library(["Books"], "Books/Old", excluded))
        # even the transcripts' folder, when it is the one left out
        self.assertFalse(rb.in_library(["Books"], rb.TRANSCRIPTS_FOLDER + "/x", [rb.TRANSCRIPTS_FOLDER]))
        self.assertEqual(rb.excluded_folders({"library_excluded": ["b", "", "a", 3]}), ["a", "b"])

    def test_a_chosen_folder_stands_for_what_is_inside(self):
        chosen = ["Books"]
        self.assertTrue(rb.in_library(chosen, "Books"))
        self.assertTrue(rb.in_library(chosen, "Books/Maigret"))
        self.assertFalse(rb.in_library(chosen, "Bookshelf"))        # a prefix of the name is not inside
        self.assertFalse(rb.in_library(chosen, ""))
        self.assertEqual(rb.part_of(chosen, "Books/Maigret"), "Books")
        self.assertIsNone(rb.part_of(chosen, "Books"))
        self.assertIsNone(rb.part_of(chosen, "Other"))

    def test_the_transcripts_folder_always_stays(self):
        chosen, t = ["Books"], rb.TRANSCRIPTS_FOLDER
        self.assertTrue(rb.in_library(chosen, t))
        self.assertTrue(rb.in_library(chosen, t + "/Huberman"))
        self.assertEqual(rb.part_of(chosen, t + "/Huberman"), t)
        self.assertEqual(rb.library_roots(chosen), ["Books", t])
        self.assertEqual(rb.library_roots([t]), [t])

    def test_listing_a_folder_again_replaces_its_own_books_only(self):
        known = [book("a", "old.epub"), book("a", "kept.epub"), book("a/sub", "deep.epub"), book("b", "other.epub")]
        merged = rb.merge_folder(known, "a", ["a/sub"], [book("a", "kept.epub"), book("a", "new.epub")])
        self.assertEqual(sorted(b["folder"] + "/" + b["name"] for b in merged), sorted(["a/sub/deep.epub", "b/other.epub", "a/kept.epub", "a/new.epub"]))

    def test_a_subfolder_gone_from_the_drive_takes_its_books_away(self):
        known = [book("a/gone", "x.epub"), book("a/gone/deeper", "y.epub"), book("a/sub", "z.epub"), book("b", "w.epub")]
        merged = rb.merge_folder(known, "a", ["a/sub"], [])
        self.assertEqual(sorted(b["folder"] + "/" + b["name"] for b in merged), ["a/sub/z.epub", "b/w.epub"])

    def test_the_top_of_the_drive_merges_the_same_way(self):
        known = [book("", "top.epub"), book("gone", "x.epub"), book("stays", "y.epub")]
        merged = rb.merge_folder(known, "", ["stays"], [book("", "top2.epub")])
        self.assertEqual(sorted(b["folder"] + "/" + b["name"] for b in merged), ["/top2.epub", "stays/y.epub"])

    def test_books_found_elsewhere_are_not_mixed_in(self):
        # a listing only ever carries the folder's own books; anything else in `found` is ignored
        merged = rb.merge_folder([], "a", [], [book("a", "ok.epub"), book("b", "stray.epub")])
        self.assertEqual([b["folder"] + "/" + b["name"] for b in merged], ["a/ok.epub"])

    DRIVE = [dict(name=n, folder=f, ref="ref:%s/%s" % (f, n), size=1, modified=m) for f, n, m in (
        ("Books/novels/Roald Dahl", "Matilda.epub", 30), ("Books/novels", "Dune.epub", 10), ("Books/science", "Cosmos.epub", 50),
        ("Books/science", "Carl Sagan - Contact.epub", 20), ("transcriptions/Huberman", "Sleep.epub", 60), ("", "Loose.epub", 40))]

    def test_every_folder_or_the_top_ones(self):
        self.assertEqual([f[0] for f in rb.sort_folders(rb.grouped_folders(self.DRIVE, False), "NAME")],
                         ["", "Books/novels", "Books/novels/Roald Dahl", "Books/science", "transcriptions/Huberman"])
        top = rb.sort_folders(rb.grouped_folders(self.DRIVE, True), "NAME")
        self.assertEqual(top, [("", 1, 40, 1), ("Books", 4, 50, 3), ("transcriptions", 1, 60, 1)])
        self.assertEqual([f[0] for f in rb.sort_folders(top, "NEWEST")], ["transcriptions", "Books", ""])
        self.assertEqual([f[0] for f in rb.sort_folders(top, "COUNT")], ["Books", "", "transcriptions"])
        self.assertEqual((rb.relative_folder("Books", "Books/novels/Roald Dahl"), rb.relative_folder("Books", "Books"), rb.relative_folder("", "Books/science")),
                         ("novels/Roald Dahl", "", "Books/science"))

    def test_books_in_every_order(self):
        b = [x for x in self.DRIVE if rb.folder_under("Books", x["folder"])]
        names = lambda order, opened=None: [x["name"] for x in rb.sort_books(b, order, opened)]
        self.assertEqual(names("NEWEST"), ["Cosmos.epub", "Matilda.epub", "Carl Sagan - Contact.epub", "Dune.epub"])
        self.assertEqual(names("OLDEST"), ["Dune.epub", "Carl Sagan - Contact.epub", "Matilda.epub", "Cosmos.epub"])
        self.assertEqual(names("NAME"), ["Carl Sagan - Contact.epub", "Cosmos.epub", "Dune.epub", "Matilda.epub"])
        self.assertEqual(names("AUTHOR"), ["Carl Sagan - Contact.epub", "Dune.epub", "Matilda.epub", "Cosmos.epub"])
        self.assertEqual(names("OPENED", {"ref:Books/novels/Dune.epub": 5, "ref:Books/science/Cosmos.epub": 9}),
                         ["Cosmos.epub", "Dune.epub", "Carl Sagan - Contact.epub", "Matilda.epub"])

    def test_a_search_finds_every_word_in_name_author_or_folder(self):
        b = [book("Books/1950s", "Simenon - Maigret et la vieille dame.epub"), book("Books/Élie", "Les Thibault.epub"), book("", "Dune.epub")]
        names = lambda q: [x["name"] for x in rb.search_books(b, q)]
        self.assertEqual(names(""), [])
        self.assertEqual(names("   "), [])
        self.assertEqual(names("MAIGRET 1950"), ["Simenon - Maigret et la vieille dame.epub"])   # case, folder
        self.assertEqual(names("simenon dame"), ["Simenon - Maigret et la vieille dame.epub"])   # author, two words
        self.assertEqual(names("elie"), ["Les Thibault.epub"])                                   # accent in the folder
        self.assertEqual(names("Thibault, les"), ["Les Thibault.epub"])                          # punctuation
        self.assertEqual(names("dune"), ["Dune.epub"])                                           # a book of the top
        self.assertEqual(names("maigret dune"), [])                                              # every word, in one book
        self.assertEqual(rb.plain_text("L’Étranger — d'Albert_Camus."), "l etranger d albert camus")

    def test_the_search_page_lists_what_was_found_and_offers_to_search_again(self):
        main = rb.Main()
        main.remote.index = dict(rb.EMPTY_INDEX, books=list(self.DRIVE))
        main.search("  sagan  ")
        self.assertEqual(main.screen, (rb.SEARCH, "sagan"))
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Carl Sagan - Contact"])
        self.assertEqual(main.rows[0].title, "sagan · " + rb.n_books(1) + " · " + rb.order_name("NEWEST"))
        self.assertIn(rb._("search again"), [m[0] for m in main.menu_items if m])
        main.search("nothing of the kind")        # the open search is replaced, not stacked
        self.assertEqual(main.screen, (rb.SEARCH, "nothing of the kind"))
        self.assertEqual(main.stack.count(main.screen), 1)
        self.assertEqual([r.title for r in main.rows if r.kind == rb.HINT], [rb._("no book matches")])
        main.search("   ")                        # nothing asked: nothing changes
        self.assertEqual(main.screen, (rb.SEARCH, "nothing of the kind"))

    def test_another_drive_drops_the_choice(self):
        cfg = {"url": "https://a.example/", "library_folders": ["Books"], "library_folders_asked": True}
        rb.set_library_url(cfg, "https://a.example/ ")
        self.assertEqual(cfg["library_folders"], ["Books"])
        rb.set_library_url(cfg, "https://b.example/")
        self.assertEqual((cfg["url"], cfg["library_folders"], cfg["library_folders_asked"]), ("https://b.example/", [], False))


class LibraryPage(unittest.TestCase):
    """The library page against a drive of four folders served by rclone: the sync-now row, the
    offer to keep only some folders, the choice kept to, the whole drive back."""
    PORT = 8093
    BASE = "http://127.0.0.1:%d" % PORT
    FILES = ("Romans/Maigret/Le chien jaune.epub", "Romans/Un roman.epub", "Essais/Un essai.epub", "transcriptions/Une chaîne/Un épisode.epub")

    @classmethod
    def setUpClass(cls):
        if not shutil.which("rclone"):
            raise unittest.SkipTest("rclone is needed to serve the test drive")
        drive = path("drive")
        for f in cls.FILES:
            os.makedirs(os.path.dirname(os.path.join(drive, f)), exist_ok=True)
            open(os.path.join(drive, f), "wb").close()
        cls.server = subprocess.Popen(["rclone", "serve", "webdav", drive, "--addr", "127.0.0.1:%d" % cls.PORT, "--user", "u", "--pass", "p"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _i in range(100):
            try:
                rb.requests.get(cls.BASE, timeout=1)
                return
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait()

    def settle(self, main, until, what):
        deadline = time.time() + 30
        while time.time() < deadline:
            APP.processEvents()
            if until():
                APP.processEvents()
                return
            time.sleep(0.05)
        self.fail("still waiting for " + what)

    def synced(self, main):
        self.settle(main, lambda: not main.remote.scanning and main.remote.index["complete"] and main.remote.index["scannedAt"] > 0, "the sync")
        main.show_screen()

    def shot(self, main, name):
        where = os.environ.get("READERS_BOOKS_SHOTS")
        if where:
            APP.processEvents()
            main.grab().save(os.path.join(where, name + ".png"))

    def test_a_book_of_the_shelf_goes_to_the_drive_and_is_a_book_of_the_library(self):
        rb.save_config(dict(rb.DEFAULTS, url=self.BASE, username="u", password="p"))
        try:
            os.remove(rb.INDEX_FILE)
        except OSError:
            pass
        book = path("shelf.epub")
        make_books.epub(book, title="Un essai")         # the drive has an "Un essai.epub" in Essais already
        main = rb.Main()
        main.resize(760, 900)
        main.show()
        entry = main.library.add(book, "Un essai.epub")
        main.library.save_position(entry["id"], 0, 0, 0)        # opened once: it has a place to send
        self.assertTrue(rb.can_send(main.cfg, entry))
        self.assertEqual(rb.send_name(entry), "Un essai.epub")
        self.assertEqual(main.stack, [(rb.LIBRARY,)])          # a library set up: the app opens on it
        self.synced(main)
        main.push((rb.SHELF,))
        # the shelf's row menu offers it
        row = next(r for r in main.rows if r.title == "Un essai")
        item = next(m for m in row.menu() if m and m[0] == rb._("add to the library"))
        item[1]()
        self.assertEqual(main.screen[0], rb.ADD_TO_LIBRARY)
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], [rb._("top of the drive"), "Essais", "Romans", "Romans/Maigret"])
        self.shot(main, "add_to_library")
        next(r for r in main.rows if r.title == "Essais").action()
        self.settle(main, lambda: main.sent is not None or main.send_error, "the upload")
        self.assertEqual(main.send_error, "")
        sent = os.path.join(path("drive"), "Essais", "Un essai (2).epub")
        self.assertTrue(os.path.exists(sent))                   # the drive's own file was left alone
        self.assertEqual(os.path.getsize(sent), os.path.getsize(book))
        linked = main.library.get(entry["id"])
        self.assertEqual(linked["sourceName"], "Un essai (2).epub")
        self.assertTrue(rb.from_library(linked))
        self.assertFalse(rb.can_send(main.cfg, linked))
        self.assertIn("Un essai (2).epub", [b["name"] for b in main.remote.books(main.cfg, "Essais")])
        self.assertEqual(main.cfg["send_folder"], "Essais")
        self.assertEqual(main.rows[1].title, rb._("“%s” is now in the library, in %s.", "Un essai", "Essais"))
        self.shot(main, "sent")
        # its place goes next to it at once
        self.settle(main, lambda: os.path.exists(sent + rb.HIGHLIGHTS_SUFFIX), "the place next to the book")
        # next time, the folder used last comes first
        main.pop()
        other = main.library.add(book, "Un autre.epub")
        main.push((rb.ADD_TO_LIBRARY, other["id"]))
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW][:2], ["Essais", rb._("top of the drive")])
        self.assertEqual(main.rows[2].secondary, rb.n_books(2) + " · " + rb._("last time"))
        main.library.remove(other["id"])
        main.library.remove(entry["id"])
        # cleared through the server: a file removed behind rclone's back stays in its listing for minutes
        for name in ("Un essai (2).epub", "Un essai (2).epub" + rb.HIGHLIGHTS_SUFFIX):
            rb.requests.delete(self.BASE + "/Essais/" + rb.quote(name, safe=""), auth=("u", "p"), timeout=10)
        self.assertFalse(os.path.exists(sent))

    def test_the_library_page_offers_the_folders_and_keeps_to_the_choice(self):
        rb.save_config(dict(rb.DEFAULTS, url=self.BASE, username="u", password="p"))
        try:
            os.remove(rb.INDEX_FILE)
        except OSError:
            pass
        main = rb.Main()
        main.resize(760, 900)
        main.show()
        self.assertEqual(main.stack, [(rb.LIBRARY,)])          # a library set up: the app opens on it
        # at its top, the books on this computer (no book read yet: nothing to carry on), then the sync
        self.assertEqual([r.title for r in main.rows[:2]], [rb._("on this computer"), rb._("sync now")])
        self.synced(main)
        titles = [r.title for r in main.rows]
        self.assertEqual(titles[:2], [rb._("on this computer"), rb._("sync now")])
        self.assertEqual(main.rows[1].secondary, rb._("scanned on %s", rb.date_label(main.remote.index["scannedAt"])))
        self.assertIn(rb._("keep only some folders?"), titles)
        self.assertEqual([t for t in titles if "/" in t or t in ("Essais", "Romans")], ["Essais", "Romans", "Romans/Maigret", "transcriptions/Une chaîne"])
        self.assertEqual(next(r.secondary for r in main.rows if r.title == rb._("all books")), rb.n_books(4))
        self.shot(main, "library")
        # the offer opens the chooser, with the whole drive chosen
        next(r for r in main.rows if r.title == rb._("keep only some folders?")).action()
        self.assertEqual(main.screen[0], rb.LIBRARY_FOLDERS)
        self.assertTrue(main.cfg["library_folders_asked"])
        self.assertEqual((main.rows[1].title, main.rows[1].inverted), (rb._("the whole drive"), True))
        next(r for r in main.rows if r.title == "Essais").action()
        self.assertEqual(main.cfg["library_folders"], ["Essais"])
        by_title = {r.title: r for r in main.rows}
        self.assertEqual([(t, by_title[t].inverted) for t in ("Essais", "Romans", "Romans/Maigret", "transcriptions/Une chaîne")],
                         [("Essais", True), ("Romans", False), ("Romans/Maigret", False), ("transcriptions/Une chaîne", True)])
        self.assertEqual(by_title["transcriptions/Une chaîne"].secondary, rb.n_books(1) + " · " + rb._("in %s", rb.TRANSCRIPTS_FOLDER))
        self.assertFalse(main.rows[1].inverted)
        self.shot(main, "folders")
        # back in the library: a quiet sync of the chosen folders, and only their books
        before = main.remote.index["scannedAt"]
        main.pop()
        self.assertEqual(main.screen[0], rb.LIBRARY)
        self.synced(main)
        self.assertGreater(main.remote.index["scannedAt"], before)
        titles = [r.title for r in main.rows]
        self.assertNotIn(rb._("keep only some folders?"), titles)
        self.assertEqual([t for t in titles if "/" in t or t in ("Essais", "Romans")], ["Essais", "transcriptions/Une chaîne"])
        self.assertEqual(next(r.secondary for r in main.rows if r.title == rb._("all books")), rb.n_books(2))
        self.assertEqual(len(main.remote.index["books"]), 4)           # the others are known still, for the chooser
        main.push((rb.ALL_BOOKS,))
        self.assertEqual(sorted(r.title for r in main.rows if r.kind == rb.ROW), ["Un essai", "Un épisode"])
        main.pop()
        # the whole drive brings them back
        main.push((rb.LIBRARY_FOLDERS,))
        main.rows[1].action()
        self.assertEqual(main.cfg["library_folders"], [])
        main.pop()
        self.synced(main)
        titles = [r.title for r in main.rows]
        self.assertEqual([t for t in titles if "/" in t or t in ("Essais", "Romans")], ["Essais", "Romans", "Romans/Maigret", "transcriptions/Une chaîne"])
        self.assertNotIn(rb._("keep only some folders?"), titles)      # offered once
        # a folder left out, by its row's menu: out of the list and of the syncs, known still
        row = next(r for r in main.rows if r.title == "Romans/Maigret")
        next(m for m in row.menu() if m[0] == rb._("leave this folder out"))[1]()
        self.assertEqual(main.cfg["library_excluded"], ["Romans/Maigret"])
        titles = [r.title for r in main.rows]
        self.assertEqual([t for t in titles if "/" in t or t in ("Essais", "Romans")], ["Essais", "Romans", "transcriptions/Une chaîne"])
        self.assertEqual(next(r.secondary for r in main.rows if r.title == rb._("all books")), rb.n_books(3))
        # with Romans chosen, Maigret stays out; the walk skips it and its book stays known
        main.push((rb.LIBRARY_FOLDERS,))
        by_title = {r.title: r for r in main.rows}
        self.assertEqual(by_title["Romans/Maigret"].secondary, rb.n_books(1) + " · " + rb._("left out"))
        by_title["Romans"].action()
        self.assertEqual(main.cfg["library_folders"], ["Romans"])
        by_title = {r.title: r for r in main.rows}
        self.assertEqual([(t, by_title[t].inverted) for t in ("Essais", "Romans", "Romans/Maigret")], [("Essais", False), ("Romans", True), ("Romans/Maigret", False)])
        self.shot(main, "folders_left_out")
        main.pop()
        self.synced(main)
        self.assertEqual(len(main.remote.index["books"]), 4)
        self.assertEqual([t for t in [r.title for r in main.rows] if "/" in t or t in ("Essais", "Romans")], ["Romans", "transcriptions/Une chaîne"])
        # taken back in through the chooser's menu
        main.push((rb.LIBRARY_FOLDERS,))
        row = next(r for r in main.rows if r.title == "Romans/Maigret")
        next(m for m in row.menu() if m[0] == rb._("take this folder back in"))[1]()
        self.assertEqual(main.cfg["library_excluded"], [])
        main.pop()
        self.synced(main)
        self.assertEqual([t for t in [r.title for r in main.rows] if "/" in t or t in ("Essais", "Romans")], ["Romans", "Romans/Maigret", "transcriptions/Une chaîne"])
        main.set("library_folders", [])
        # a folder alone, then with the folders inside it, each book naming its folder
        main.push((rb.FOLDER, "Romans"))
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Un roman"])
        self.assertEqual(main.rows[0].title, rb._("by name"))
        next(m for m in main.menu_items if m and m[0] == rb._("with subfolders"))[1]()
        self.assertEqual([(r.title, r.secondary.startswith("Maigret · ")) for r in main.rows if r.kind == rb.ROW], [("Le chien jaune", True), ("Un roman", False)])
        self.assertEqual(main.rows[0].title, rb._("by name") + " · " + rb._("with subfolders"))
        next(m for m in main.menu_items if m and m[0] == rb._("this folder only"))[1]()
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Un roman"])
        main.pop()
        main.push((rb.FOLDER, "Essais"))
        self.assertNotIn(rb._("with subfolders"), [m[0] for m in main.menu_items if m])     # Essais has no subfolder
        main.pop()
        # grouped by top folder: one line per top folder, with everything inside it, in the chosen order
        next(m for m in main.menu_items if m and m[0] == rb._("group by top folder"))[1]()
        self.assertTrue(main.cfg["library_top_folders"])
        by_title = {r.title: r for r in main.rows}
        self.assertEqual([t for t in by_title if "/" in t or t in ("Essais", "Romans", "transcriptions")], ["Essais", "Romans", "transcriptions"])
        self.assertEqual(by_title["Romans"].secondary, rb.n_books(2) + " · " + rb.n_folders(2))
        self.assertEqual(by_title["Essais"].secondary, rb.n_books(1))
        next(m for m in main.menu_items if m and m[0].startswith(rb._("order")))[1][2][1]()      # by number of books
        self.assertEqual(main.cfg["folder_sort"], "COUNT")
        self.assertEqual([r.title for r in main.rows if r.title in ("Essais", "Romans", "transcriptions")], ["Romans", "Essais", "transcriptions"])
        by_title["Romans"].action()
        self.assertEqual(main.screen, (rb.FOLDER, "Romans", True))
        self.assertEqual([(r.title, r.secondary.startswith("Maigret · ")) for r in main.rows if r.kind == rb.ROW], [("Le chien jaune", True), ("Un roman", False)])
        self.assertNotIn(rb._("this folder only"), [m[0] for m in main.menu_items if m])      # a group always has them
        next(m for m in main.menu_items if m and m[0] == rb._("newest first"))[1]()
        self.assertEqual(main.cfg["library_sort"], "NEWEST")
        self.shot(main, "top_folder")
        main.pop()
        next(m for m in main.menu_items if m and m[0] == rb._("every folder"))[1]()
        self.assertFalse(main.cfg["library_top_folders"])
        main.close()

    def test_the_shelf_is_ordered_as_asked(self):
        rb.save_config(dict(rb.DEFAULTS))
        main = rb.Main()
        main.library.books[:] = []
        now = int(time.time() * 1000)
        for title, added, opened in (("Zèbre", now - 3000, now - 1000), ("Abc", now - 2000, 0), ("Milieu", now - 1000, now - 2000)):
            main.library.books.append(dict(id=title, fileName=title + ".txt", title=title, format="TXT", added=added, opened=opened, progress=0))
        main.library._save()
        main.show_screen()
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Zèbre", "Milieu", "Abc"])     # last opened or added first
        order = next(m for m in main.menu_items if m and m[0].startswith(rb._("order")))[1]
        order[1][1]()
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Abc", "Milieu", "Zèbre"])
        order[2][1]()
        self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW], ["Milieu", "Abc", "Zèbre"])
        self.assertEqual(main.cfg["shelf_sort"], "ADDED")
        main.close()


class ShelfHighlights(unittest.TestCase):
    """Highlights in a book of the shelf alone: kept here in the contract's form, its note in
    Reader's Notes, and taken into the library's file when the same book comes from the drive."""

    def test_the_same_book_is_the_same_file_or_the_same_epub_identifier_and_title(self):
        def epub(name, uid, title, extra=""):
            p = path(name)
            with rb.zipfile.ZipFile(p, "w") as z:
                z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
                z.writestr("OEBPS/content.opf", '<package unique-identifier="pub-id"><metadata><dc:identifier id="isbn">978-0</dc:identifier>'
                           '<dc:identifier id="pub-id">%s</dc:identifier><dc:title>%s</dc:title>%s</metadata></package>' % (uid, title, extra))
            return {"title": title, "fingerprint": rb.book_fingerprint(p), "bookId": rb.epub_id(p, rb.EPUB)}
        a = epub("id-a.epub", "urn:uuid:1234", "Le Livre")
        self.assertEqual(a["bookId"], "urn:uuid:1234")
        self.assertEqual(len(a["fingerprint"]), 64)
        shutil.copyfile(path("id-a.epub"), path("id-copy.epub"))
        self.assertTrue(rb.same_book(a, {"title": "Le Livre", "fingerprint": rb.book_fingerprint(path("id-copy.epub"))}))   # same bytes
        self.assertTrue(rb.same_book(a, epub("id-b.epub", "urn:uuid:1234", "Le Livre", "<dc:subject>x</dc:subject>")))         # rewritten
        self.assertFalse(rb.same_book(a, epub("id-c.epub", "urn:uuid:1234", "Un autre")))      # one stamp on many books
        self.assertFalse(rb.same_book(a, epub("id-d.epub", "urn:uuid:9999", "Le Livre")))      # a title alone is not enough
        self.assertFalse(rb.same_book({"title": "T"}, {"title": "T"}))                          # never learnt: never the same by accident
        self.assertEqual(rb.package_id("<opf:package unique-identifier='bookid'><dc:identifier id='bookid'> abc </dc:identifier></opf:package>"), "abc")
        self.assertEqual(rb.epub_id(path("id-a.epub"), rb.FB2), "")

    def test_a_shelf_book_keeps_its_highlights_in_the_contract_s_form_and_hands_them_over(self):
        lib = rb.Library()
        shelf = lib.add(make_books.epub(path("hand.epub"), "À passer"), "À passer.epub")
        mine = rb.new_highlight(0, 1, 5, "mine")
        both = rb.new_highlight(1, 3, 9, "both")
        rb.save_highlights(shelf, [mine, dict(both, deleted=True, text="", modified=both["modified"] + 10)], True)
        with open(os.path.join(rb.HIGHLIGHTS_DIR, rb.highlight_key(shelf) + ".json"), encoding="utf-8") as fh:
            data = json.load(fh)
        self.assertEqual((data["format"], data["version"], data["book"]), ("readers-highlights", 1, "À passer.epub"))
        self.assertEqual(sorted(data["highlights"][0]), ["chapter", "comment", "created", "deleted", "end", "id", "modified", "start", "text"])
        # the same file comes from the library: it takes the shelf's copy's place, and its highlights
        theirs = rb.new_highlight(3, 0, 4, "drive")
        library_side = {"id": "z", "source": "https://dav.example/Livres/À passer.epub"}
        rb.save_highlights(library_side, [both, theirs], False)
        fetched = lib.add(path("hand.epub"), "À passer.epub", source=library_side["source"])
        self.assertIsNone(lib.get(shelf["id"]))
        self.assertEqual(lib.moved[-1][0]["id"], shelf["id"])
        merged, dirty = rb.load_highlights(fetched)
        self.assertEqual([h["id"] for h in merged], [mine["id"], both["id"], theirs["id"]])
        self.assertTrue(next(h for h in merged if h["id"] == both["id"])["deleted"])        # the later removal wins
        self.assertTrue(dirty)                                                                # still to be sent
        self.assertEqual(rb.load_highlights(shelf), ([], False))
        # a book of the library never adopts another copy of the drive
        other = lib.add(path("hand.epub"), "À passer.epub", source="https://dav.example/Ailleurs/À passer.epub")
        self.assertIsNotNone(lib.get(fetched["id"]))
        lib.remove(other["id"])
        lib.remove(fetched["id"])

    def test_the_home_screen_is_the_library_once_there_is_one(self):
        rb.save_config(dict(rb.DEFAULTS))
        main = rb.Main()
        self.assertEqual(main.stack, [(rb.SHELF,)])
        self.assertEqual(main.title.text(), rb._("books"))
        self.assertTrue(main.foot_invite.isVisibleTo(main))
        self.assertIn(rb._("set up a library"), main.foot_invite.text())
        main.foot_invite.clicked.emit()                       # the invitation opens the library's account page
        self.assertEqual(main.screen, (rb.LIBRARY,))
        self.assertEqual(main.rows[0].title, rb.LIBRARY_HINT())
        # set up: the library becomes the home screen, at once
        main.cfg.update(url="http://127.0.0.1:9/", username="u", password="p")
        main.remote.scan = lambda cfg, fresh: None           # no drive to walk here
        main.show_screen()
        self.assertEqual(main.stack, [(rb.LIBRARY,)])
        self.assertFalse(main.back.isVisibleTo(main))
        e = main.library.add(make_books.epub(path("home.epub"), "Lu hier"), "home.epub")
        main.library.save_position(e["id"], 0, 0, 42)
        main.show_screen()
        self.assertEqual([(r.title, r.secondary) for r in main.rows[:2]],
                         [("Lu hier", rb._("continue reading") + " · 42%"), (rb._("on this computer"), rb.n_books(len(main.library.books)))])
        main.rows[1].action()
        self.assertEqual(main.stack, [(rb.LIBRARY,), (rb.SHELF,)])
        self.assertEqual(main.title.text(), rb._("on this computer"))
        self.assertFalse(main.foot_invite.isVisibleTo(main))
        main.pop()
        main.rows[0].action()                                  # one click: the book read last, at its page
        self.assertEqual(main.stack, [(rb.LIBRARY,), (rb.BOOK, e["id"])])
        self.assertEqual(main.back_label(), rb._("library"))
        main.pop()
        # forgotten: the shelf is home again
        main.push((rb.SETTINGS,))
        main.forget_library()
        self.assertEqual(main.stack, [(rb.SHELF,), (rb.SETTINGS,)])
        main.pop()
        self.assertTrue(main.foot_invite.isVisibleTo(main))
        main.library.remove(e["id"])
        main.close()
        rb.save_config(dict(rb.DEFAULTS))


class ShelfToLibrary(unittest.TestCase):
    """Against a drive served by rclone: the note of a shelf book written into Reader's Notes,
    then the same book fetched from the library bringing its highlights to the drive's file."""
    PORT = 8094
    BASE = "http://127.0.0.1:%d" % PORT

    @classmethod
    def setUpClass(cls):
        if not shutil.which("rclone"):
            raise unittest.SkipTest("rclone is needed to serve the test drive")
        cls.drive = path("drive2")
        os.makedirs(os.path.join(cls.drive, "Livres"), exist_ok=True)
        os.makedirs(os.path.join(cls.drive, "Notes"), exist_ok=True)
        make_books.epub(os.path.join(cls.drive, "Livres", "Le même.epub"), "Le même")
        cls.server = subprocess.Popen(["rclone", "serve", "webdav", cls.drive, "--addr", "127.0.0.1:%d" % cls.PORT, "--user", "u", "--pass", "p"],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _i in range(100):
            try:
                rb.requests.get(cls.BASE, timeout=1)
                return
            except Exception:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.terminate()
        cls.server.wait()

    def settle(self, until, what):
        deadline = time.time() + 30
        while time.time() < deadline:
            APP.processEvents()
            if until():
                APP.processEvents()
                return
            time.sleep(0.05)
        self.fail("still waiting for " + what)

    def test_a_shelf_book_s_note_then_its_highlights_on_the_drive(self):
        notes = os.path.join(self.drive, "Notes", rb.BOOKS_FOLDER)
        # no library, a notes folder only
        rb.save_config(dict(rb.DEFAULTS, notes_url=self.BASE + "/Notes", notes_username="u", notes_password="p"))
        main = rb.Main()
        local = os.path.join(self.drive, "Livres", "Le même.epub")
        entry = main.library.add(local, "copie.epub")          # the very file, opened from this computer
        self.assertEqual(main.stack, [(rb.SHELF,)])
        main.push((rb.BOOK, entry["id"]))
        self.settle(lambda: main.reader.book is not None, "the book")
        h = rb.new_highlight(0, 0, 8, main.reader.text_of(0).cut(0, 8), "à garder")
        main.change_highlights([h])
        self.settle(lambda: os.path.exists(os.path.join(notes, "copie.txt")), "the note")
        with open(os.path.join(notes, "copie.txt"), encoding="utf-8") as fh:
            self.assertIn("à garder", fh.read())
        self.settle(lambda: not rb.load_highlights(entry)[1], "the note marked as written")
        main.pop()
        # now a library: the same book fetched from it takes the highlights to the drive's file
        main.cfg.update(url=self.BASE + "/", username="u", password="p")
        rb.save_config(main.cfg)
        main.show_screen(reset=True)
        self.assertEqual(main.stack, [(rb.LIBRARY,)])
        self.settle(lambda: not main.remote.scanning and main.remote.index["complete"] and main.remote.index["scannedAt"] > 0, "the sync")
        found = next(b for b in main.remote.index["books"] if b["name"] == "Le même.epub")
        main.fetch(found)
        sidecar = local + rb.HIGHLIGHTS_SUFFIX
        self.settle(lambda: os.path.exists(sidecar), "the highlights next to the book")
        with open(sidecar, encoding="utf-8") as fh:
            self.assertEqual([x["id"] for x in json.load(fh)["highlights"]], [h["id"]])
        self.assertIsNone(main.library.get(entry["id"]))
        # its note moved to the book's name on the drive
        self.settle(lambda: os.path.exists(os.path.join(notes, "Le même.txt")) and not os.path.exists(os.path.join(notes, "copie.txt")), "the note under its new name")
        main.close()
        rb.save_config(dict(rb.DEFAULTS))


# ------------------------------------------------------------------------------------------
# Magazines: the issues of one magazine grouped, a followed folder of the drive, the contents as
# pages, the article bar — against a drive of issues served by rclone.
# ------------------------------------------------------------------------------------------

class Magazines(unittest.TestCase):
    PORT = 8114
    BASE = "http://127.0.0.1:%d" % PORT
    DAY = 24 * 3600

    def test_the_issues_of_one_magazine_share_its_name(self):
        # the phone's MagazinesTest, case for case
        for title, name in [
                ("24 heures — Edition du mardi 3 novembre 2026", "24 heures"), ("NZZ — Édition du vendredi 24 avril 2026", "NZZ"),
                ("Courrier International — Édition du 2026-04-25", "Courrier International"), ("The Economist — Apr 25th 2026", "The Economist"),
                ("Informed with Aaron Siri | Substack — Édition du 02.11.2026", "Informed with Aaron Siri | Substack"),
                ("Huberman Lab — Access the Sublime & Live Your Best Life | Robert Greene — Édition du mardi 3 novembre 2026", "Huberman Lab"),
                ("Le Monde du 25 avril 2026", "Le Monde"), ("Der Spiegel vom 3. November 2026", "Der Spiegel"),
                ("The Guardian, Wednesday November 4, 2026", "The Guardian"), ("Le Temps 2026-11-04", "Le Temps"),
                ("La Revue N° 42", "La Revue"), ("A book without a date", "A book without a date")]:
            self.assertEqual(rb.magazine_name(title), name, title)
        self.assertEqual(rb.magazine_key("24 heures — Edition du mardi 3 novembre 2026"), rb.magazine_key("24 Heures — Édition du jeudi 5 novembre 2026"))
        self.assertEqual(rb.magazine_issue("24 heures — Edition du mercredi 4 novembre 2026"), "Edition du mercredi 4 novembre 2026")
        self.assertEqual(rb.magazine_issue("Le Monde du 25 avril 2026"), "25 avril 2026")

    def test_a_folder_followed_gives_its_latest_day_at_once(self):
        import datetime as dt
        day = 24 * 3600_000
        t0 = 1_793_000_000_000 - 1_793_000_000_000 % day + 6 * 3600_000
        books = [{"name": n, "folder": f, "ref": "http://d/%s/%s" % (f, n), "modified": m} for n, f, m in [
            ("2026-11-02-24heures.epub", "journaux", t0 - 2 * day), ("2026-11-03-24heures.epub", "journaux", t0 - day),
            ("2026-11-04-24heures.epub", "journaux", t0), ("2026-11-04-nzz.epub", "journaux", t0 + 3600_000),
            ("2026-11-04-courrier.epub", "journaux/hebdos", t0 + 7200_000), ("Maigret.epub", "Books", t0 + day)]]
        seen = rb.first_seen(books, "journaux", dt.timezone.utc)
        self.assertEqual(sorted(r.rsplit("/", 1)[1] for r in seen), ["2026-11-02-24heures.epub", "2026-11-03-24heures.epub"])
        f = {"folder": "journaux", "seen": seen}
        self.assertEqual([b["name"] for b in rb.fresh_books(books, f, set())], ["2026-11-04-courrier.epub", "2026-11-04-nzz.epub", "2026-11-04-24heures.epub"])
        self.assertEqual(len(rb.fresh_books(books, f, {"http://d/journaux/2026-11-04-nzz.epub"})), 2)
        kept = rb.prune_seen({"folder": "journaux", "seen": ["http://d/journaux/2026-11-04-24heures.epub", "http://d/journaux/gone.epub"]}, books)
        self.assertEqual(kept["seen"], ["http://d/journaux/2026-11-04-24heures.epub"])

    def put(self, name, title):
        """An issue sent through the server, as the newspapers pipeline does."""
        make_books.epub(path("issue.epub"), title=title, chapters=12, magazine=True)
        with open(path("issue.epub"), "rb") as fh:
            r = rb.requests.put(self.BASE + "/journaux/" + rb.quote(name), data=fh.read(), auth=("u", "p"))
        self.assertIn(r.status_code, (200, 201, 204))

    def test_a_followed_folder_brings_its_new_issues_in_one_click(self):
        if not shutil.which("rclone"):
            self.skipTest("rclone is needed to serve the test drive")
        drive = path("magazines-drive")
        os.makedirs(os.path.join(drive, "journaux"), exist_ok=True)
        now = time.time()
        for n, (name, title) in enumerate([("2026-11-02-24heures.epub", "24 heures — Edition du lundi 2 novembre 2026"),
                                           ("2026-11-03-24heures.epub", "24 heures — Edition du mardi 3 novembre 2026"),
                                           ("2026-11-04-24heures.epub", "24 heures — Edition du mercredi 4 novembre 2026")]):
            target = os.path.join(drive, "journaux", name)
            make_books.epub(target, title=title, chapters=12, magazine=True)
            os.utime(target, (now - (2 - n) * self.DAY, now - (2 - n) * self.DAY))
        server = subprocess.Popen(["rclone", "serve", "webdav", drive, "--addr", "127.0.0.1:%d" % self.PORT, "--user", "u", "--pass", "p", "--dir-cache-time", "1s"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _i in range(100):
                try:
                    rb.requests.get(self.BASE, timeout=1)
                    break
                except Exception:
                    time.sleep(0.1)
            for f in (rb.INDEX_FILE, rb.FOLLOW_FILE, rb.LIBRARY_FILE):
                try:
                    os.remove(f)
                except OSError:
                    pass
            rb.save_config(dict(rb.DEFAULTS, url=self.BASE, username="u", password="p"))
            main = rb.Main()
            main.resize(760, 900)
            main.show()
            page = LibraryPage.settle
            page(self, main, lambda: not main.remote.scanning and main.remote.index["scannedAt"] > 0, "the sync")
            main.show_screen()
            row = next(r for r in main.rows if r.title == "journaux")
            follow = next(m for m in row.menu() if m and m[0].startswith(rb._("follow this folder")))
            follow[1]()
            # the latest day's issue is new at once; nothing was fetched
            self.assertEqual(main.rows[0].title, "journaux · " + rb.n_new(1))
            self.assertEqual(main.library.books, [])
            LibraryPage.shot(self, main, "mag_followed")
            # one click: fetched, and its contents open, as pages
            main.rows[0].action()
            page(self, main, lambda: main.screen[0] == rb.CHAPTERS, "the new issue")
            entry = main.library.get(main.screen[1])
            self.assertEqual(entry["title"], "24 heures — Edition du mercredi 4 novembre 2026")
            self.assertTrue(main.paged and main.paged[2] > 1, main.paged)
            self.assertEqual(main.listing.verticalScrollBar().maximum(), 0)     # the page fits: nothing scrolls
            first = [r.title for r in main.rows if r.kind == rb.ROW]
            LibraryPage.shot(self, main, "mag_contents_1")
            main.turn_contents(True)
            self.assertEqual(main.paged[1], 1)
            self.assertNotEqual([r.title for r in main.rows if r.kind == rb.ROW], first)
            self.assertEqual(main.rows[0].kind, rb.SECTION)         # a page names its section first
            LibraryPage.shot(self, main, "mag_contents_2")
            # a side click turns back; a click in the middle opens the article
            vp = main.listing.viewport()
            QtTest.QTest.mouseClick(vp, rb.QtCore.Qt.LeftButton, pos=rb.QtCore.QPoint(10, 100))
            self.assertEqual(main.paged[1], 0)
            article = next(r for r in main.rows if r.kind == rb.ROW and r.title.startswith("Article numéro 2 "))
            article.action()
            self.assertEqual(main.screen, (rb.BOOK, entry["id"]))
            reader = main.reader
            page(self, main, lambda: reader.book is not None, "the issue")
            reader.repaint()
            self.assertEqual(reader.chapter, 1)
            reader.turn(True)
            reader.turn(True)
            left_at = (reader.chapter, reader.page)
            LibraryPage.shot(self, main, "mag_article")
            # the bar: next article, then back to the previous one, where it was left
            zone = reader.bar_zone()
            QtTest.QTest.mouseClick(reader, rb.QtCore.Qt.LeftButton, pos=rb.QtCore.QPoint(zone.right() - 5, zone.center().y()))
            reader.repaint()
            self.assertEqual(reader.chapter, 2)
            QtTest.QTest.mouseClick(reader, rb.QtCore.Qt.LeftButton, pos=rb.QtCore.QPoint(zone.left() + 5, zone.center().y()))
            reader.repaint()
            self.assertEqual((reader.chapter, reader.page), left_at)
            QtTest.QTest.mouseClick(reader, rb.QtCore.Qt.LeftButton, pos=rb.QtCore.QPoint(zone.center().x(), zone.center().y()))
            self.assertEqual(main.screen, (rb.CHAPTERS, entry["id"]))
            self.assertTrue(next(r for r in main.rows if r.current).title.startswith("Article numéro 2 "))
            # two more issues on the drive: one click brings both, and their list opens
            self.put("2026-11-05-24heures.epub", "24 heures — Edition du jeudi 5 novembre 2026")
            self.put("2026-11-06-24heures.epub", "24 heures — Edition du vendredi 6 novembre 2026")
            main.home()
            main.show_screen(reset=True)
            next(r for r in main.rows if r.title.startswith("journaux")).action()
            page(self, main, lambda: main.screen[0] == rb.ISSUES, "the new issues")
            self.assertEqual([r.title for r in main.rows if r.kind == rb.ROW][:3],
                             ["24 heures — Edition du vendredi 6 novembre 2026", "24 heures — Edition du jeudi 5 novembre 2026",
                              "24 heures — Edition du mercredi 4 novembre 2026"])
            LibraryPage.shot(self, main, "mag_issues")
            main.pop()
            followed = next(r for r in main.rows if r.title.startswith("journaux"))
            self.assertEqual((followed.title, followed.secondary), ("journaux", rb._("nothing new · %s", rb.when_label(main.following.get("journaux")["checkedAt"]))))
            # on the shelf: one row for the magazine, the latest issue a click away
            main.push((rb.SHELF,))
            rows = [r for r in main.rows if r.kind == rb.ROW]
            self.assertEqual(rows[0].title, "24 heures · " + rb.n_issues(3))
            LibraryPage.shot(self, main, "mag_shelf")
            rows[0].menu()[0][1]()
            self.assertEqual(main.screen, (rb.ISSUES, "magazine", rb.magazine_key(entry["title"])))
            self.assertEqual(main.rows[1].title, "Edition du vendredi 6 novembre 2026")
            # removed, an issue does not come back as new
            removed = main.library.books[0]
            main.remove(removed["id"])
            self.assertIn(removed["source"], main.following.get("journaux")["seen"])
            main.close()
        finally:
            server.terminate()
            server.wait()
            for f in (rb.FOLLOW_FILE, rb.LIBRARY_FILE, rb.INDEX_FILE):      # the other tests start without them
                try:
                    os.remove(f)
                except OSError:
                    pass


# ------------------------------------------------------------------------------------------
# Italic and bold are runs beside the text, never in it: a highlight is a place in the text of its
# chapter, the same on the phone and here. Each case compares the text with what the app made of
# the same page before it knew of emphasis (legacy_to_blocks, the earlier code word for word).
# ------------------------------------------------------------------------------------------

def legacy_to_blocks(text, image):
    """Paragraphs with their kind, and the pictures between them. `image` maps an `src` to what
    the reader can load, or None to drop it. Kinds are marked with control characters before the
    tags are stripped."""
    s = rb._COMMENTS.sub("", text)
    s = rb._SVG_IMAGE.sub(lambda m: '<img src="%s"/>' % m.group(1), s)

    def picture(m):
        found = image(m.group(1))
        return "\n\n%s%s\n\n" % (rb.IMG, found) if found else " "
    s = rb._IMG.sub(picture, s)
    s = rb._DROP.sub(" ", s)
    s = rb._HEADING_OPEN.sub(lambda m: m.group(0) + rb.MARK + "H", s)

    def classed(m):
        c = m.group(2).lower()
        if rb._LEAD.search(c):
            return m.group(0) + rb.MARK + "L"
        if rb._SMALLPRINT.search(c):
            return m.group(0) + rb.MARK + "S"
        return m.group(0)
    s = rb._CLASSED.sub(classed, s)
    s = rb._BR.sub("\n", s)
    s = rb._PARA_BREAK.sub("\n\n", s)
    s = rb._ANY_TAG.sub("", s)
    s = rb.decode_entities(s)
    s = rb._SPACES.sub(" ", s)
    blocks, paras = [], []
    for raw in rb._BLANK_LINE.split(s):
        para = "\n".join(line.strip() for line in raw.split("\n") if line.strip())
        if not para:
            continue
        if para.startswith(rb.IMG):
            if paras:
                blocks.append(rb.TextBlock(paras))
                paras = []
            blocks.append(rb.ImageBlock(para[1:].split("\n")[0].strip()))
            continue
        kind, t = rb.NORMAL, para
        while len(t) > 1 and t[0] == rb.MARK:
            kind = {"H": rb.HEADING, "L": rb.LEAD, "S": rb.SMALL}.get(t[1], kind)
            t = t[2:].lstrip()
        t = rb._MARKS.sub("", t)
        if t in ("---", "♦"):       # the pipeline's separators
            continue
        if t:
            paras.append(rb.Para(t, kind))
    if paras:
        blocks.append(rb.TextBlock(paras))
    return blocks



def describe(blocks):
    return "|".join("IMG:" + b.source if isinstance(b, rb.ImageBlock) else "¶".join(p.kind + ":" + p.text for p in b.paragraphs) for b in blocks)


def runs(p):
    return [(p.text[a:b], f, a) for a, b, f in (p.styles or ())]


class Emphasis(unittest.TestCase):
    def same(self, html):
        self.assertEqual(describe(legacy_to_blocks(html, lambda s: s)), describe(rb.to_blocks(html, lambda s: s)))

    def test_italic_and_bold_are_runs_and_the_text_is_what_it_was(self):
        html = ("<p>Il a dit <i>  oui </i>, puis <b>non</b> et <em>peut-<strong>être</strong></em>.</p>"
                "<p><i>Tout en italique</i></p><h2>Un <i>titre</i></h2><p class=\"lead\">Le <b>chapô</b></p>")
        self.same(html)
        paras = rb.to_blocks(html, lambda s: s)[0].paragraphs
        self.assertEqual(paras[0].text, "Il a dit oui , puis non et peut-être.")
        # the same runs as the phone's (EmphasisTest)
        self.assertEqual(runs(paras[0]), [("oui ", rb.ITALIC, 9), ("non", rb.BOLD, 20), ("peut-", rb.ITALIC, 27), ("être", rb.ITALIC | rb.BOLD, 32)])
        self.assertEqual(runs(paras[1]), [("Tout en italique", rb.ITALIC, 0)])
        self.assertEqual((paras[2].kind, runs(paras[2])), (rb.HEADING, [("titre", rb.ITALIC, 3)]))
        # a lead is in bold as a whole: its bold words have nothing more to set
        self.assertEqual((paras[3].kind, runs(paras[3]), paras[3].look.flags & rb.BOLD), (rb.LEAD, [], rb.BOLD))

    def test_marks_at_the_edges_of_lines_and_paragraphs_change_nothing(self):
        for html in ["<p><i> </i></p><p>a</p>", "<p>a <i>\n b</i>\n c</p>", "<p>un<br/><i>deux</i><br/> trois</p>",
                     "<i><p>across</p><p>paragraphs</p></i><p>after</p>", "<p>x</p><b>\n\n</b><p>y</p>",
                     "<p>&nbsp;<i>&nbsp;espace&nbsp;</i>&nbsp;</p>", "<h1><i>Titre</i></h1><p class=\"author\"><b>Par</b> X</p>",
                     "<p>---</p><p><i>♦</i></p><p>fin</p>", "<p><b/>vide <b />et <i></i>rien</p>", "<p>un <img src=\"a.png\"/> <i>deux</i></p>",
                     "<p>unclosed <i>italic</p><p>goes on</p>", "<p>stray </i> close</p>", "<P><I>UPPER</I> <B CLASS=\"x\">case</B></P>",
                     "<p>\u0003 already there <i>x</i></p>", "<div><blockquote><em>cite</em> — <strong>auteur</strong></blockquote></div>",
                     "<p>😀 <i>émoji</i> 😀 <b>gras</b></p>"]:
            self.same(html)

    def test_a_highlight_lands_on_the_same_words_with_emphasis(self):
        plain = rb.to_blocks("<p>Il dit bonjour à tous.</p><p>Puis il part.</p>", lambda s: None)
        styled = rb.to_blocks("<p>Il <i>dit</i> <b>bonjour</b> à <em>tous</em>.</p><p><strong>Puis</strong> il part.</p>", lambda s: None)
        a, b = rb.chapter_text(rb.Chapter("c", plain)), rb.chapter_text(rb.Chapter("c", styled))
        self.assertEqual(a, b)
        self.assertIsNone(plain[0].paragraphs[0].styles)
        # laid out: the italic word is italic, the place of every word unchanged
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(20)
        laid = laid_out(styled[0], font, 600)
        self.assertEqual(laid.layout.text().replace(rb.LINE_BREAK, "\n"), a.rstrip("\n"))
        italic = [r for r in laid.layout.formats() if r.format.fontItalic()]
        self.assertEqual([laid.layout.text()[r.start:r.start + r.length] for r in italic], ["dit", "tous"])
        bold = [r for r in laid.layout.formats() if r.format.fontWeight() == rb.QtGui.QFont.Bold]
        self.assertEqual([laid.layout.text()[r.start:r.start + r.length] for r in bold], ["bonjour", "Puis"])

    def test_a_long_paragraph_cut_in_two_keeps_its_runs(self):
        html = "<p>" + " ".join("<i>mot%d</i>" % i if i % 100 == 0 else "mot%d" % i for i in range(1, 3001)) + "</p>"
        chapters, _ = rb._split_long([rb.Chapter("c", rb.to_blocks(html, lambda s: None))])
        self.assertGreater(len(chapters), 1)
        for ch in chapters:
            for p in ch.blocks[0].paragraphs:
                for text, flags, _ in runs(p):
                    self.assertEqual(flags, rb.ITALIC)
                    self.assertTrue(text.startswith("mot"), text)
        self.assertEqual(sum(len(runs(p)) for ch in chapters for p in ch.blocks[0].paragraphs), 30)

    def test_every_page_of_real_books_reads_the_same(self):
        """The EPUBs of $EMPHASIS_BOOKS (folders, separated by ':'), when set: magazines, books."""
        import zipfile
        for folder in filter(None, os.environ.get("EMPHASIS_BOOKS", "").split(":")):
            for name in sorted(os.listdir(folder)):
                if not name.endswith(".epub"):
                    continue
                with zipfile.ZipFile(os.path.join(folder, name)) as z:
                    pages = [n for n in z.namelist() if n.lower().endswith(("html", ".htm"))]
                    for n in pages:
                        self.same(z.read(n).decode("utf-8", "replace"))
                print("==", name, len(pages), "pages read the same")


if __name__ == "__main__":
    unittest.main()


LAYOUT_CASES = [
    # (css, html): the publisher's presentation; the text must come out as it did without it
    ("p { text-indent: 1.5em; text-align: justify; margin: 0 }", "<p>Un</p><p>Deux\ntrois</p>"),
    ("ul { list-style: square } ol { list-style-type: lower-roman }",
     "<ul><li>a</li><li>b<ul><li>c</li></ul></li></ul><ol start=\"3\"><li>x</li><li value=\"9\">y</li></ol>"),
    ("", "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td><p>deux</p><p>lignes</p></td></tr></table><p>après</p>"),
    ("", "<table><tr><td>A</td>\n<td>B</td></tr><tr><td colspan=\"2\">C</td></tr></table>"),
    (".poem p { text-indent: -1em; margin-left: 1em }", "<div class=\"poem\"><p>vers un</p><p>vers deux</p></div>"),
    ("", "<pre>ligne un\n  ligne deux\n\nligne trois</pre><p>a<br/>b\nc</p>"),
    ("p.first::first-letter { font-size: 3em; float: left }", "<p class=\"first\">«Lettrine» au début.</p>"),
    (".drop-cap { font-size: 2.8em; float: left }", "<p class=\"first\"><span class=\"drop-cap\">M</span>arie</p>"),
    (".sc { font-variant: small-caps } .note { vertical-align: super }",
     "<p>La <span class=\"sc\">Petite</span> note<sup>1</sup><span class=\"note\">2</span> H<sub>2</sub>O <u>u</u> <s>s</s> <code>c</code></p>"),
    ("", "<p>avant</p><hr/><p>après</p><div class=\"separator\">---</div><p>fin</p>"),
    (".saut { page-break-before: always } h1 { text-align: center }", "<h1>Titre</h1><p class=\"saut\">page</p>"),
    ("", "<figure><img src=\"a.png\" width=\"120\"/><figcaption>Légende</figcaption></figure><p class=\"caption\">x</p>"),
    ("p { color: red; float: right; font-size: 30px; position: absolute } @media x { p { margin: 9em } }",
     "<p style=\"text-align:right; margin-left: 50%\">droite</p><p align=\"center\">centre</p>"),
    ("", "<p>\u0007 un caractère de contrôle <i>x</i></p>"),
    ("a > b, [x] p, p:hover, #id p { font-size: 4em }", "<p>rien</p>"),
]


class Layout(unittest.TestCase):
    """The book's presentation (Look) beside the text: the text of every case is what it was."""

    def blocks(self, css, html):
        return rb.to_blocks(html, lambda s: s, rb.css_parse(css))

    def test_the_text_is_what_it_was_whatever_the_style_sheet(self):
        for css, html in LAYOUT_CASES:
            self.assertEqual(describe(legacy_to_blocks(html, lambda s: s)), describe(self.blocks(css, html)), html)
        book = make_books.layout_epub(path("layout.epub"))
        import zipfile
        with zipfile.ZipFile(book) as z:
            for name in z.namelist():
                if name.endswith(".xhtml"):
                    html = z.read(name).decode("utf-8")
                    self.assertEqual(describe(legacy_to_blocks(html, lambda s: s)),
                                     describe(rb.to_blocks(html, lambda s: s, rb.css_parse(make_books.LAYOUT_CSS))), name)

    def test_what_the_book_sets(self):
        ps = self.blocks(*LAYOUT_CASES[0])[0].paragraphs
        self.assertEqual((ps[0].look.align, ps[0].look.indent, ps[1].look.soft), (rb.JUSTIFY, 1.5, [4]))
        ps = self.blocks(*LAYOUT_CASES[1])[0].paragraphs
        self.assertEqual([(p.text, p.look.marker, p.look.number) for p in ps],
                         [("a", rb.SQUARE, 1), ("b", rb.SQUARE, 2), ("c", rb.SQUARE, 1), ("x", rb.LOWER_ROMAN, 3), ("y", rb.LOWER_ROMAN, 9)])
        self.assertEqual([p.look.left for p in ps], [1.5, 1.5, 3.0, 1.5, 1.5])
        ps = self.blocks(*LAYOUT_CASES[2])[0].paragraphs
        self.assertEqual(ps[0].text, "AB")
        self.assertEqual(ps[0].look.cells, [(0, 1, 0, 0, 1, 1), (1, 2, 0, 1, 1, 1)])
        self.assertEqual([p.look.cells for p in ps[1:3]], [[(0, 1, 1, 0, 1, 0)], [(0, 4, 1, 1, 1, 0)]])
        self.assertEqual(ps[3].look.cells, [(0, 6, 1, 1, 1, 0)])
        self.assertIsNone(ps[4].look.cells)
        ps = self.blocks(*LAYOUT_CASES[3])[0].paragraphs
        self.assertEqual([c[3:5] for c in ps[1].look.cells], [(0, 2)])
        ps = self.blocks(*LAYOUT_CASES[4])[0].paragraphs
        self.assertEqual([(p.look.left, p.look.indent) for p in ps], [(1.0, -1.0), (1.0, -1.0)])
        ps = self.blocks(*LAYOUT_CASES[5])[0].paragraphs
        self.assertEqual([p.text for p in ps], ["ligne un\nligne deux", "ligne trois", "a\nb\nc"])
        self.assertEqual((ps[0].look.soft, ps[0].look.flags & rb.MONO, ps[2].look.soft), (None, rb.MONO, [3]))
        self.assertEqual(self.blocks(*LAYOUT_CASES[6])[0].paragraphs[0].look.drop_cap, 2)
        self.assertEqual(self.blocks(*LAYOUT_CASES[7])[0].paragraphs[0].look.drop_cap, 1)
        p = self.blocks(*LAYOUT_CASES[8])[0].paragraphs[0]
        self.assertEqual([(p.text[a:b], f & rb.FLAGS) for a, b, f in p.styles],
                         [("Petite", rb.SMALL_CAPS), ("12", rb.SUPER), ("2", rb.SUB), ("u", rb.UNDERLINE),
                          ("s", rb.STRIKE), ("c", rb.MONO)])
        ps = self.blocks(*LAYOUT_CASES[9])[0].paragraphs
        self.assertEqual([(p.text, p.look.rule) for p in ps], [("avant", False), ("après", True), ("fin", True)])
        ps = self.blocks(*LAYOUT_CASES[10])[0].paragraphs
        self.assertEqual([(p.look.align, p.look.level, p.look.page_break, p.look.size) for p in ps],
                         [(rb.CENTER, 1, False, 1.6), (rb.AUTO, 0, True, 1.0)])
        blocks = self.blocks(*LAYOUT_CASES[11])
        self.assertEqual((blocks[0].look.pixels, blocks[0].look.align), (120, rb.AUTO))
        self.assertEqual([(p.look.align, p.look.size) for p in blocks[1].paragraphs], [(rb.CENTER, 0.85), (rb.CENTER, 0.8)])
        ps = self.blocks(*LAYOUT_CASES[12])[0].paragraphs
        self.assertEqual([(p.look.align, p.look.left, p.look.size, p.look.flags) for p in ps], [(rb.RIGHT, 4.0, 1.0, 0), (rb.CENTER, 0.0, 1.0, 0)])
        self.assertIsNone(self.blocks(*LAYOUT_CASES[13])[0].paragraphs[0].look)
        self.assertEqual(self.blocks(*LAYOUT_CASES[14])[0].paragraphs[0].look.size, 1.0)

    def test_the_pages_of_a_book_with_a_style_sheet(self):
        book = rb.parse_book(make_books.layout_epub(path("layout.epub")), rb.EPUB, "layout")
        store = rb.ImageStore(path("layout.epub"))
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(18)
        for width, height in ((500, 700), (320, 480)):
            kinds = set()
            for c, chapter in enumerate(book.chapters):
                pages = rb.paginate(chapter, rb.Frame(font, rb.QtGui.QColor("#888"), width, height, store))
                text = rb.Text16(rb.chapter_text(chapter))
                starts = [rb.page_start(p) for p in pages]
                self.assertEqual(starts, sorted(starts))
                for page in pages:
                    for piece in page:
                        kinds.add(type(piece).__name__)
                        if isinstance(piece, rb.Lines):
                            laid = piece.block
                            self.assertLessEqual(piece.y + laid.bottoms[piece.last] - laid.tops[piece.first], height)
                            # every line shows the chapter's own characters where the map says they are
                            for i in range(piece.first, piece.last + 1):
                                line = laid.layout.lineAt(i)
                                a = laid.to_chapter(line.textStart())
                                word = text.cut(a, a + 3).strip()
                                if word and "\n" not in word and word.isalpha():
                                    shown = rb.Text16(laid.layout.text()).cut(laid.to_laid(a), laid.to_laid(a) + 3)
                                    self.assertEqual(shown.lower(), text.cut(a, a + 3).lower())
                        elif not isinstance(piece, (rb.Rule, rb.Grid)):
                            self.assertLessEqual(piece.y + piece.height, height)
                # the paragraph its style sheet sends to a new page begins one
                if c == 3:
                    first = rb.Text16(rb.chapter_text(chapter)).cut(starts[-1], starts[-1] + 15)
                    self.assertTrue(any(rb.Text16(rb.chapter_text(chapter)).cut(s, s + 2) == "Ce" for s in starts), starts)
            self.assertTrue({"Lines", "Picture", "Rule", "Grid"} <= kinds, kinds)
