#!/bin/bash
# Builds readers-books_<version>_all.deb next to this script. Needs dpkg-deb and fakeroot.
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; SRC="$HERE/.."
VERSION=$(grep -oE '^VERSION = "[^"]+"' "$SRC/readers_books.py" | cut -d'"' -f2)
ROOT="$HERE/deb-root"; rm -rf "$ROOT"
install -Dm755 "$SRC/readers_books.py" "$ROOT/usr/lib/readers-books/readers_books.py"
install -Dm755 "$SRC/paper2epub.py" "$ROOT/usr/lib/readers-books/paper2epub.py"
for f in "$HERE"/fonts/*; do install -Dm644 "$f" "$ROOT/usr/lib/readers-books/fonts/$(basename "$f")"; done
install -Dm755 /dev/stdin "$ROOT/usr/bin/readers-books" <<'SH'
#!/bin/sh
exec python3 /usr/lib/readers-books/readers_books.py "$@"
SH
install -Dm644 "$HERE/readers-books.desktop" "$ROOT/usr/share/applications/readers-books.desktop"
install -Dm644 "$HERE/readers-books.svg" "$ROOT/usr/share/icons/hicolor/scalable/apps/readers-books.svg"
install -Dm644 "$HERE/readers-books.png" "$ROOT/usr/lib/readers-books/readers-books.png"
install -Dm644 "$SRC/LICENSE" "$ROOT/usr/share/doc/readers-books/copyright"
mkdir -p "$ROOT/DEBIAN"
cat > "$ROOT/DEBIAN/control" <<CTRL
Package: readers-books
Version: $VERSION
Section: text
Priority: optional
Architecture: all
Depends: python3 (>= 3.8), python3-pyqt5, python3-requests
Recommends: python3-venv
Maintainer: funkypitt <pierregallaz@gmail.com>
Homepage: https://github.com/funkypitt/readers-books-desktop
Description: Black-and-white e-book reader: a shelf, and pages cut at whole lines
 A shelf as a plain list and books as pages of text, turned by a click or a
 key. EPUB, MOBI, FB2 and plain text; the place in each book is kept.
 Pictures in EPUBs are shown in the page, magazine issues open on their
 contents. An optional library lists the e-books kept on a drive (a public
 kDrive share link or any WebDAV address) and fetches a book when it is
 asked for. A paper in PDF becomes an EPUB, its figures, tables and
 equations as pictures, by a converter set up on first use (python3-venv;
 about 2 GB downloaded). The desktop twin of the Reader's Books Android app.
CTRL
fakeroot dpkg-deb --build "$ROOT" "$HERE/readers-books_${VERSION}_all.deb"
rm -rf "$ROOT"
echo "built $HERE/readers-books_${VERSION}_all.deb"
