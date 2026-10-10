#!/usr/bin/env python3
"""The synchronisation, in all its forms, against a real WebDAV server.

Two devices (two separate stores of this app's own code) share one drive served by `rclone serve
webdav`: the library in one folder, the Reader's Notes folder in another. Every case below is a
thing two devices can do to each other; the bench says what it expected when one fails.

    python3 tests/bench_sync.py            # needs rclone; Reader's Notes desktop next to this repo
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TMP = tempfile.mkdtemp(prefix="readers-books-bench-")
os.environ["XDG_CONFIG_HOME"], os.environ["XDG_DATA_HOME"] = TMP + "/config", TMP + "/data"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rb = load("rb", os.path.join(HERE, "readers_books.py"))
NOTES = os.path.join(os.path.dirname(HERE), "readers-notes-desktop", "readers_notes.py")
rn = load("rn", NOTES) if os.path.exists(NOTES) else None

PORT = 8097
DRIVE = TMP + "/drive"
BASE = "http://127.0.0.1:%d" % PORT
BOOK = "Zoé d'Arc + l'été: «essai».epub"          # a name with everything a name can hold
CFG = {"url": BASE + "/Livres", "username": "lecteur", "password": "mot de passe é",
       "notes_url": BASE + "/Mes notes", "notes_username": "", "notes_password": ""}
server = None
passed = []


def serve():
    global server
    server = subprocess.Popen(["rclone", "serve", "webdav", DRIVE, "--addr", "127.0.0.1:%d" % PORT, "--user", CFG["username"],
                               "--pass", CFG["password"]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _i in range(50):
        try:
            rb.requests.get(BASE, timeout=1)
            return
        except Exception:
            time.sleep(0.1)


def stop():
    global server
    if server:
        server.terminate()
        server.wait()
        server = None


class Device:
    """One installation of the app: its own copy of the highlights and its own shelf entry."""
    def __init__(self, name, cfg=None, book=BOOK):
        self.name, self.cfg, self.dir = name, dict(cfg or CFG), os.path.join(TMP, name)
        from urllib.parse import quote
        self.entry = {"id": name, "title": "Essai", "source": self.cfg["url"] + "/" + quote(book, safe=""), "sourceName": book,
                      "chapter": 0, "charOffset": 0, "progress": 0, "opened": 0}

    def _here(self):
        rb.HIGHLIGHTS_DIR = self.dir

    def highlights(self):
        self._here()
        return rb.load_highlights(self.entry)[0]

    def live(self):
        return [(h["text"], h["comment"]) for h in rb.live_highlights(self.highlights())]

    def add(self, start, text, comment="", chapter=0):
        self._here()
        h = rb.new_highlight(chapter, start, start + len(text), text, comment)
        rb.save_highlights(self.entry, self.highlights() + [h], True)
        return h["id"]

    def edit(self, hid, **fields):
        self._here()
        rb.save_highlights(self.entry, [dict(h, modified=rb._now(), **fields) if h["id"] == hid else h for h in self.highlights()], True)

    def remove(self, hid):
        self.edit(hid, deleted=True, text="", comment="")

    def read_to(self, chapter, offset, progress, when=None):
        self.entry.update(chapter=chapter, charOffset=offset, progress=progress, opened=when or rb._now())

    def sync(self):
        """As the window does it; a place read later elsewhere is taken, as on the shelf."""
        self._here()
        result = rb.sync_book(self.cfg, self.entry, self.entry["sourceName"])
        if result and result[1]:
            there = result[1]
            self.entry.update(chapter=there["chapter"], charOffset=there["charOffset"], progress=there.get("progress", 0), opened=there["modified"])
        return result

    def place(self):
        return self.entry["chapter"], self.entry["charOffset"], self.entry["progress"]


def drive_file(folder, name):
    path = os.path.join(DRIVE, folder, name)
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def sidecar():
    text = drive_file("Livres", BOOK + rb.HIGHLIGHTS_SUFFIX)
    return json.loads(text) if text else None


def note():
    return drive_file("Mes notes/" + rb.BOOKS_FOLDER, rb.note_file_name(BOOK))


def quoted(text):
    opening, closing = rb._QUOTES.get(rb.LANG, ("«", "»"))
    return opening + text + closing


def check(label, got, expected):
    if got != expected:
        raise AssertionError("%s\n   expected: %r\n        got: %r" % (label, expected, got))


def put(folder, name, text):
    """Written through the server, as another device would: a file changed behind its back is
    served with the length it remembers."""
    from urllib.parse import quote
    r = rb.requests.put("%s/%s/%s" % (BASE, quote(folder), quote(name, safe="")), data=text.encode("utf-8"),
                        auth=(CFG["username"], CFG["password"].encode("utf-8")))
    r.raise_for_status()


def case(fn):
    stop()
    for folder in ("Livres", "Mes notes"):
        shutil.rmtree(os.path.join(DRIVE, folder), ignore_errors=True)
        os.makedirs(os.path.join(DRIVE, folder))
    open(os.path.join(DRIVE, "Livres", BOOK), "w").write("a book")
    for name in ("A", "B", "C"):
        shutil.rmtree(os.path.join(TMP, name), ignore_errors=True)
    serve()
    fn()
    passed.append(fn.__doc__.strip().split("\n")[0])
    print("  ok  " + passed[-1], flush=True)


def tick():
    time.sleep(0.003)       # two changes never carry the same millisecond


# ---------------------------------------------------------------------------------------------

def a_highlight_crosses():
    """a highlight made on one device appears on the other, and in the note"""
    a, b = Device("A"), Device("B")
    a.add(10, "premier passage")
    a.sync()
    check("the other device", (b.sync() or [None])[0] and b.live(), [("premier passage", "")])
    check("the note", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n" % quoted("premier passage"))
    check("the file names the book", sidecar()["book"], BOOK)


def a_comment_crosses_back():
    """a comment written on the second device comes back to the first, under its passage"""
    a, b = Device("A"), Device("B")
    hid = a.add(10, "un passage")
    a.sync(); b.sync(); tick()
    b.edit(hid, comment="Bien vu.")
    b.sync(); a.sync()
    check("first device", a.live(), [("un passage", "Bien vu.")])
    check("the note", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n\nBien vu.\n" % quoted("un passage"))


def a_removal_crosses_and_stays():
    """a highlight removed on one device goes on the other, and does not come back"""
    a, b = Device("A"), Device("B")
    keep, gone = a.add(10, "à garder"), a.add(50, "à retirer")
    a.sync(); b.sync(); tick()
    b.remove(gone)
    b.sync(); a.sync()
    check("first device", a.live(), [("à garder", "")])
    a.sync(); b.sync(); a.sync()
    check("still gone after more rounds", (a.live(), b.live()), ([("à garder", "")], [("à garder", "")]))
    check("the note", quoted("à retirer") in note(), False)
    check("the removal is remembered on the drive", [h["deleted"] for h in sidecar()["highlights"]].count(True), 1)


def both_offline_then_both_sync():
    """two devices each highlight while cut off: once back, both have both, in the order of the book"""
    a, b = Device("A"), Device("B")
    stop()
    a.add(200, "plus loin (A)")
    b.add(20, "au début (B)", "note de B")
    for d in (a, b):
        try:
            d.sync()
            raise AssertionError("a sync with no server should fail")
        except rb.requests.RequestException:
            pass
    check("kept for later", (a.live(), b.live()), ([("plus loin (A)", "")], [("au début (B)", "note de B")]))
    serve()
    a.sync(); b.sync(); a.sync()
    both = [("au début (B)", "note de B"), ("plus loin (A)", "")]
    check("both devices", (a.live(), b.live()), (both, both))
    check("the note", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n\nnote de B\n\n%s\n" % (quoted("au début (B)"), quoted("plus loin (A)")))


def the_same_comment_edited_twice():
    """the same comment rewritten on both devices: the one written last is kept on both"""
    a, b = Device("A"), Device("B")
    hid = a.add(10, "un passage", "premier jet")
    a.sync(); b.sync(); tick()
    a.edit(hid, comment="version de A"); tick()
    b.edit(hid, comment="version de B, plus tard")
    b.sync(); a.sync(); b.sync()
    check("both devices", (a.live(), b.live()), ([("un passage", "version de B, plus tard")],) * 2)


def removed_here_edited_there():
    """removed on one device, commented later on the other: the later of the two wins on both"""
    a, b = Device("A"), Device("B")
    hid = a.add(10, "un passage")
    a.sync(); b.sync(); tick()
    a.remove(hid); tick()
    b.edit(hid, comment="commenté après le retrait")
    a.sync(); b.sync(); a.sync()
    check("the comment came last", (a.live(), b.live()), ([("un passage", "commenté après le retrait")],) * 2)
    a2, b2 = Device("A", book=BOOK), Device("B", book=BOOK)
    tick(); b2.edit(hid, comment="encore"); tick(); a2.remove(hid)
    a2.sync(); b2.sync(); a2.sync()
    check("the removal came last", (a2.live(), b2.live()), ([], []))
    check("no note for a book with nothing left", note(), None)


def two_devices_at_the_same_moment():
    """two devices write the drive's file at the same moment: nothing is lost, and the note is whole"""
    a, b = Device("A"), Device("B")
    a.add(10, "celui de A")
    b.add(60, "celui de B")
    a.sync()
    mine = drive_file("Livres", BOOK + rb.HIGHLIGHTS_SUFFIX)
    b.sync()
    # A's file put back over B's, as when A wrote a moment after B read: B's highlight is missing there
    put("Livres", BOOK + rb.HIGHLIGHTS_SUFFIX, mine)
    check("the drive lacks B's for a while", len(sidecar()["highlights"]), 1)
    b.sync(); a.sync()
    both = [("celui de A", ""), ("celui de B", "")]
    check("both devices", (a.live(), b.live()), (both, both))
    check("the drive", len(sidecar()["highlights"]), 2)
    check("the note", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n\n%s\n" % (quoted("celui de A"), quoted("celui de B")))


def the_place_follows_the_reader():
    """a book left at a page on one device opens there on the other, and the later place always wins"""
    a, b = Device("A"), Device("B")
    a.read_to(3, 1200, 41)
    a.sync()
    check("the drive", sidecar()["position"]["chapter"], 3)
    b.sync()
    check("second device", b.place(), (3, 1200, 41))
    tick(); b.read_to(5, 80, 63); b.sync(); a.sync()
    check("first device, later", a.place(), (5, 80, 63))
    # an older place on the drive never pulls a device back
    tick(); a.read_to(6, 0, 70)
    stale = sidecar()
    a.sync()
    put("Livres", BOOK + rb.HIGHLIGHTS_SUFFIX, json.dumps(stale))
    result = a.sync()
    check("not pulled back", (a.place(), result[1]), ((6, 0, 70), None))
    check("and the drive is put right", sidecar()["position"]["chapter"], 6)


def a_place_and_highlights_do_not_step_on_each_other():
    """reading on one device while the other highlights: neither the page nor the passages are lost"""
    a, b = Device("A"), Device("B")
    a.read_to(2, 300, 20); a.sync(); b.sync(); tick()
    a.read_to(2, 900, 24)
    b.add(40, "pendant que A lit")
    b.sync(); a.sync(); b.sync()
    check("A has the passage", a.live(), [("pendant que A lit", "")])
    check("B has the page", b.place(), (2, 900, 24))
    check("a place alone does not rewrite the note", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n" % quoted("pendant que A lit"))


def the_note_goes_when_nothing_is_left():
    """the last highlight removed: the book's note leaves Reader's Notes"""
    a = Device("A")
    hid = a.add(10, "seul")
    a.sync()
    check("the note is there", note() is not None, True)
    tick(); a.remove(hid); a.sync()
    check("the note is gone", note(), None)
    check("the drive remembers the removal", sidecar()["highlights"][0]["deleted"], True)


def without_a_notes_folder():
    """no Reader's Notes folder named: highlights still cross, and no note is written anywhere"""
    cfg = dict(CFG, notes_url="")
    a, b = Device("A", cfg), Device("B", cfg)
    a.add(10, "sans note"); a.sync(); b.sync()
    check("second device", b.live(), [("sans note", "")])
    check("no note", os.listdir(os.path.join(DRIVE, "Mes notes")), [])


def a_notes_login_of_its_own_and_a_wrong_one():
    """the notes folder refuses the login: highlights still reach the other device, the note comes once it is put right"""
    wrong = dict(CFG, notes_username="lecteur", notes_password="faux")
    a, b = Device("A", wrong), Device("B")
    a.add(10, "malgré tout")
    try:
        a.sync()
        raise AssertionError("the notes folder should have refused")
    except rb.WrongLogin:
        pass
    check("no note yet", note(), None)
    b.sync()
    check("the other device has it", b.live(), [("malgré tout", "")])
    a.cfg = dict(CFG, notes_username="lecteur", notes_password=CFG["password"])
    a.sync()
    check("the note, once the login is right", note(), "Zoé d'Arc + l'été: «essai»\n\n%s\n" % quoted("malgré tout"))


def a_wrong_library_password():
    """the library refuses the login: nothing is lost here, and it goes up once the password is right"""
    a = Device("A", dict(CFG, password="faux"))
    a.add(10, "en attente")
    try:
        a.sync()
        raise AssertionError("the library should have refused")
    except rb.WrongLogin:
        pass
    check("kept here", a.live(), [("en attente", "")])
    check("nothing on the drive", sidecar(), None)
    a.cfg = dict(CFG)
    a.sync()
    check("on the drive", [h["text"] for h in sidecar()["highlights"]], ["en attente"])


def a_file_that_is_not_ours():
    """something else lies where the highlights should be (not our format, not even JSON): ours are written, nothing breaks"""
    a = Device("A")
    for junk in ('{"format": "something-else", "highlights": [{"id": "x"}]}', "not json at all"):
        put("Livres", BOOK + rb.HIGHLIGHTS_SUFFIX, junk)
        tick(); a.add(10 + len(passed), "le nôtre")
        a.sync()
        check("our format on the drive", sidecar()["format"], rb.HIGHLIGHTS_FORMAT)


def three_devices():
    """three devices, each with a highlight of its own and one removal: all three end alike"""
    a, b, c = Device("A"), Device("B"), Device("C")
    ida = a.add(10, "de A"); b.add(20, "de B"); c.add(30, "de C", "et sa note")
    for d in (a, b, c, a, b):
        d.sync()
    tick(); c.remove(ida); c.sync()
    for d in (a, b, c):
        d.sync()
    end = [("de B", ""), ("de C", "et sa note")]
    check("all three", (a.live(), b.live(), c.live()), (end, end, end))


def a_book_not_from_the_library():
    """a book opened from a file, or fetched by an older version through a share link: it stays out of all this"""
    for source in (None, "4242"):
        d = Device("A")
        d.entry["source"] = source
        d.add(10, "local")
        check("no file next to it", (d.sync()[1], sidecar(), note()), (None, None, None))


def readers_notes_shows_it_read_only():
    """Reader's Notes (desktop) receives the book's note, follows its changes, lets it go, and never writes to it"""
    if rn is None:
        raise AssertionError("readers-notes-desktop is not next to this repository")
    a = Device("A")
    hid = a.add(10, "pour les notes", "un mot")
    a.sync()
    store = rn.Store(tempfile.mkdtemp(prefix="notes-bench-", dir=TMP))
    cfg = {"server": BASE, "folder": "Mes notes", "username": CFG["username"], "password": CFG["password"], "folders": False}
    mine = store.create("Une note à moi\nqui reste")
    rn.sync_run(store, cfg)
    books = [n for n in store.all() if store.is_book(n["id"])]
    check("one book note", [store.text(n["id"]) for n in books], [note()])
    check("folders stay unused", store.uses_folders(), False)
    check("my own note went up", drive_file("Mes notes", "Une note à moi.txt"), "Une note à moi\nqui reste")
    store.save(books[0]["id"], "tampered")            # refused: the note is not ours to change
    rn.sync_run(store, cfg)
    check("the drive's note is untouched", note().startswith("Zoé d'Arc"), True)
    tick(); a.edit(hid, comment="un autre mot"); a.sync()
    rn.sync_run(store, cfg)
    check("the change arrives", store.text(books[0]["id"]), note())
    tick(); a.remove(hid); a.sync()
    rn.sync_run(store, cfg)
    check("the note leaves", [n for n in store.all() if store.is_book(n["id"])], [])
    check("my own note is still there", store.text(mine), "Une note à moi\nqui reste")


CASES = [a_highlight_crosses, a_comment_crosses_back, a_removal_crosses_and_stays, both_offline_then_both_sync,
         the_same_comment_edited_twice, removed_here_edited_there, two_devices_at_the_same_moment,
         the_place_follows_the_reader, a_place_and_highlights_do_not_step_on_each_other,
         the_note_goes_when_nothing_is_left, without_a_notes_folder, a_notes_login_of_its_own_and_a_wrong_one,
         a_wrong_library_password, a_file_that_is_not_ours, three_devices, a_book_not_from_the_library,
         readers_notes_shows_it_read_only]


def main():
    if not shutil.which("rclone"):
        sys.exit("rclone is needed to serve the test drive")
    os.makedirs(DRIVE)
    failed = 0
    try:
        for fn in CASES:
            try:
                case(fn)
            except Exception as exc:
                failed += 1
                print("FAIL  %s\n   %s: %s" % (fn.__doc__.strip().split("\n")[0], type(exc).__name__, exc), flush=True)
                if server is None:
                    serve()
    finally:
        stop()
        shutil.rmtree(TMP, ignore_errors=True)
    print("%d of %d cases passed" % (len(CASES) - failed, len(CASES)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
