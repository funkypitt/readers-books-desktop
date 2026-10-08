"""Books made up for the tests and the screenshots: nothing here is anyone's file."""
import struct
import zipfile

from PyQt5 import QtCore, QtGui

LOREM = ("Il pleuvait sur la ville depuis le matin, une pluie fine et tenace qui noyait les toits "
         "et faisait briller les pavés. Dans la boutique, la lampe restait allumée ; on entendait "
         "le tic-tac de l'horloge et, parfois, le pas d'un passant pressé. ")


def picture(width, height, tone):
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    image.fill(QtGui.QColor(tone, tone, tone))
    painter = QtGui.QPainter(image)
    painter.setPen(QtGui.QPen(QtGui.QColor(255 - tone, 255 - tone, 255 - tone), 6))
    painter.drawEllipse(width // 4, height // 4, width // 2, height // 2)
    painter.end()
    buffer = QtCore.QBuffer()
    buffer.open(QtCore.QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(buffer.data())


def epub(path, title="Le Livre d'essai", chapters=6, magazine=False):
    manifest, spine, nav = [], [], []
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/img/one.png", picture(600, 400, 60))
        z.writestr("OEBPS/img/two.png", picture(300, 900, 200))
        sections = ["Monde", "Monde", "Culture", "Culture", "Sciences", "Sciences"]
        for i in range(1, chapters + 1):
            name = "text/ch%d.xhtml" % i
            body = ""
            if magazine:
                body += '<p class="category">%s</p><h1>Article numéro %d &amp; ses suites</h1><p class="author">Par Auteur %d</p>' % (sections[(i - 1) % 6], i, i)
                body += '<img src="../img/one.png"/><p class="lead">Un chapô qui résume l\'article en une phrase.</p>'
            else:
                body += "<h1>Chapitre %d — %s</h1>" % (i, "La pluie" if i % 2 else "Le beau temps")
            body += "".join("<p>%s</p>" % (LOREM * (2 + (k % 3))) for k in range(14 if not magazine else 5))
            if i == 2:
                body += '<p>Avant l\'image.</p><img src="../img/two.png"/><p class="caption">Une légende, en petit.</p>'
                body += "<p>Une ligne<br/>puis une autre, après un retour.</p>"
            z.writestr("OEBPS/" + name, "<html><head><title>x</title><style>p{}</style></head><body>%s</body></html>" % body)
            manifest.append('<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (i, name))
            spine.append('<itemref idref="c%d"/>' % i)
            if magazine:
                nav.append('<li><a href="%s"><span class="toc-cat">%s</span> <span class="toc-title">Article numéro %d &amp; ses suites</span> <span class="toc-author">Auteur %d</span></a></li>'
                           % (name, sections[(i - 1) % 6], i, i))
            else:
                nav.append('<li><a href="%s">Chapitre %d</a></li>' % (name, i))
        z.writestr("OEBPS/nav.xhtml", "<html><body><nav><ol>%s</ol></nav></body></html>" % "".join(nav))
        z.writestr("OEBPS/content.opf", '<package><metadata><dc:title>%s</dc:title></metadata><manifest>%s'
                   '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/></manifest><spine>%s</spine></package>'
                   % (title, "".join(manifest), "".join(spine)))
    return path


def mobi(path, title="Un Mobi", text=None):
    """An uncompressed PalmDoc/MOBI: header, record 0, one text record."""
    text = (text or "<h1>Premier</h1><p>%s</p><mbp:pagebreak/><h2>Second</h2><p>Fin — été.</p>" % LOREM).encode("utf-8")
    full = title.encode("utf-8")
    record0 = struct.pack(">HHIHHHH", 1, 0, len(text), 1, 4096, 0, 0)
    mobi_header = bytearray(232)
    mobi_header[0:4] = b"MOBI"
    struct.pack_into(">I", mobi_header, 4, 232)       # header length
    struct.pack_into(">I", mobi_header, 12, 65001)    # utf-8
    struct.pack_into(">I", mobi_header, 0x80 - 16, 0x40)
    exth = b"EXTH" + struct.pack(">II", 12 + 8 + len(full), 1) + struct.pack(">II", 503, 8 + len(full)) + full
    record0 += bytes(mobi_header) + exth
    header = bytearray(78)
    header[0:6] = b"oldnam"
    header[60:68] = b"BOOKMOBI"
    struct.pack_into(">H", header, 76, 2)
    first = 78 + 16 + 2
    table = struct.pack(">II", first, 0) + struct.pack(">II", first + len(record0), 2) + b"\x00\x00"
    with open(path, "wb") as fh:
        fh.write(bytes(header) + table + record0 + text)
    return path


def fb2(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0"?><FictionBook><description><title-info><book-title>Un FB2</book-title></title-info></description>'
                 "<body><section><title><p>Un</p></title><p>%s</p></section><section><title><p>Deux</p></title><p>Fin.</p></section></body>"
                 "<binary id='x'>AAAA</binary></FictionBook>" % LOREM)
    return path


def txt(path):
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("Premier paragraphe.\r\n\r\nSecond paragraphe,\nsur deux lignes.\n\n\nTroisième.")
    return path
