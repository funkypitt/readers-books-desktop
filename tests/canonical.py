"""The text of every chapter, as highlights count it, against a snapshot taken with an earlier
version: a highlight is a place in that text, on this computer, on the phone and on the drive, so
a change of presentation must leave it byte for byte as it was.

    python3 tests/canonical.py write SNAPSHOT BOOKS...   # with the version that sets the reference
    python3 tests/canonical.py check SNAPSHOT BOOKS...   # with the version being tested
    python3 tests/canonical.py looks OUT BOOKS...        # how each paragraph is set, one line each:
                                                         # the phone's CanonicalTest writes the same

BOOKS are files or folders (searched below for .epub .mobi .azw3 .fb2). The snapshot is one line
per chapter: file name, chapter, length, SHA-256 of the chapter's text (UTF-8). The phone has the
same check (CanonicalTest) and reads the same snapshot.
"""
import hashlib
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location("rb", os.path.join(HERE, "readers_books.py"))
rb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rb)

EXTENSIONS = (".epub", ".mobi", ".azw3", ".fb2")


def books(paths):
    for path in paths:
        if os.path.isdir(path):
            for root, _dirs, files in os.walk(path):
                for name in sorted(files):
                    if name.lower().endswith(EXTENSIONS):
                        yield os.path.join(root, name)
        else:
            yield path


def lines(path):
    name = os.path.basename(path)
    try:
        book = rb.parse_book(path, rb.detect(path, name), name)
    except Exception as e:      # a book neither version reads is the same for both
        return ["%s\t-\t-\t%s" % (name, type(e).__name__)]
    out = []
    for i, chapter in enumerate(book.chapters):
        text = rb.chapter_text(chapter)
        out.append("%s\t%d\t%d\t%s" % (name, i, rb.u16(text), hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()))
    return out


def _f2(x):
    return "-" if x != x else "%.2f" % x


def describe(look):
    if look is None:
        return "none"
    return "|".join(str(x) for x in (
        look.align, _f2(look.indent), _f2(look.left), _f2(look.right), _f2(look.above), int(look.page_break), int(look.rule),
        _f2(look.size), look.flags, look.level, look.marker, look.number, look.drop_cap,
        ",".join(map(str, look.soft)) if look.soft else "-",
        ",".join(",".join(map(str, c)) for c in look.cells) if look.cells else "-", look.table, _f2(look.width), look.pixels))


def looks(out, paths):
    with open(out, "w", encoding="utf-8") as fh:
        for path in sorted(books(paths), key=os.path.basename):
            name = os.path.basename(path)
            try:
                book = rb.parse_book(path, rb.detect(path, name), name)
            except Exception:
                continue
            for c, chapter in enumerate(book.chapters):
                k = 0
                for b in chapter.blocks:
                    if isinstance(b, rb.ImageBlock):
                        fh.write("%s\t%d\t%d\tI %s\n" % (name, c, k, describe(b.look)))
                        k += 1
                    else:
                        for p in b.paragraphs:
                            runs = ",".join("%d,%d,%d" % r for r in p.styles) if p.styles else "-"
                            fh.write("%s\t%d\t%d\tP %s %s %s\n" % (name, c, k, p.kind, describe(p.look), runs))
                            k += 1


def main():
    mode, snapshot, paths = sys.argv[1], sys.argv[2], sys.argv[3:]
    if mode == "looks":
        looks(snapshot, paths)
        return 0
    found = []
    for path in books(paths):
        found.extend(lines(path))
    found.sort()
    if mode == "write":
        with open(snapshot, "w", encoding="utf-8") as fh:
            fh.write("\n".join(found) + "\n")
        print("%d chapters written" % len(found))
        return 0
    with open(snapshot, encoding="utf-8") as fh:
        wanted = [line for line in fh.read().split("\n") if line]
    names = {line.split("\t")[0] for line in found}
    wanted = [line for line in wanted if line.split("\t")[0] in names]
    missing = sorted(set(wanted) - set(found))
    extra = sorted(set(found) - set(wanted))
    print("%d books, %d chapters checked, %d differ" % (len(names), len(found), len(missing) + len(extra)))
    for line in (missing + extra)[:20]:
        print(("  was  " if line in missing else "  now  ") + line)
    return 1 if missing or extra else 0


if __name__ == "__main__":
    sys.exit(main())
