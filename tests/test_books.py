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

APP = rb.QtWidgets.QApplication.instance() or rb.QtWidgets.QApplication([])
rb.load_bundled_fonts()


def path(name):
    return os.path.join(TMP, name)


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


class Pages(unittest.TestCase):
    def test_every_line_is_on_one_page_and_no_page_overflows(self):
        book = rb.parse_book(make_books.epub(path("p.epub")), rb.EPUB, "p")
        store = rb.ImageStore(path("p.epub"))
        font = rb.QtGui.QFont(rb.SANS_FAMILY)
        font.setPixelSize(18)
        for width, height in ((500, 700), (320, 410), (700, 300)):
            for chapter in book.chapters[:3]:
                pages = rb.paginate(chapter, font, rb.QtGui.QColor("#888"), width, height, store)
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
        laid = rb.LaidBlock(block, font, rb.QtGui.QColor("#888"), 300)
        # the two em spaces of the third paragraph's indent, twice (it holds a line break)
        self.assertEqual(len(laid.layout.text().encode("utf-16-le")) // 2, block.length - 1 + 4)


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
        laid = rb.LaidBlock(block, font, rb.QtGui.QColor("#888"), 400, base=100)
        text = rb.Text16(laid.layout.text())
        chapter = rb.Text16(rb.chapter_text(rb.Chapter("c", [block])))
        self.assertEqual(chapter.length, block.length)
        for word in ("Un", "Deux", "trois", "Quatre", "cinq"):
            at = rb.u16(rb.chapter_text(rb.Chapter("c", [block])).split(word)[0])
            self.assertEqual(text.cut(laid.to_laid(100 + at), laid.to_laid(100 + at) + len(word)), word)
            self.assertEqual(laid.to_chapter(laid.to_laid(100 + at)), 100 + at)
        # a place inside an indent is the character that follows it
        self.assertEqual(laid.to_chapter(laid.indents[0] + 1), laid.to_chapter(laid.indents[0] + 2))

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
        main.push((rb.LIBRARY,))
        self.synced(main)
        main.pop()
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
        main.push((rb.LIBRARY,))
        self.assertEqual(main.rows[0].title, rb._("sync now"))
        self.synced(main)
        titles = [r.title for r in main.rows]
        self.assertEqual(titles[0], rb._("sync now"))
        self.assertEqual(main.rows[0].secondary, rb._("scanned on %s", rb.date_label(main.remote.index["scannedAt"])))
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


if __name__ == "__main__":
    unittest.main()
