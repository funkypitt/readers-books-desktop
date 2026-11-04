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
                body += '<img src=\"../img/one.png\"/><p class="lead">Un chapô qui résume l\'article en une phrase.</p>'
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


LAYOUT_CSS = """
@charset "utf-8";
@media amzn-kf8 { p { color: red } }
body { margin: 0 5%; font-family: Georgia, serif; color: #333; background: #fed }
p { margin: 0; text-indent: 1.5em; text-align: justify }
p.noindent, h1 + p { text-indent: 0 }
h1 { font-size: 2.2em; text-align: center; margin: 1em 0 0.8em; page-break-before: always }
h2 { font-size: 1.4em; margin: 1.2em 0 0.4em }
h3 { font-size: 1.15em; font-style: italic; font-weight: normal; margin: 1em 0 0.3em }
h4 { font-size: 1em; text-transform: uppercase; margin: 0.8em 0 0.2em }
.centre { text-align: center; text-indent: 0 }
.droite { text-align: right; text-indent: 0 }
.spaced { text-indent: 0; margin: 0.7em 0 }
p.first::first-letter { font-size: 3em; float: left }
blockquote { margin: 0.8em 2em; font-style: italic }
blockquote p { text-indent: 0 }
.epigraph { margin-left: 30%; font-size: 0.9em; text-indent: 0; text-align: right }
.poem { margin: 0.8em 0 0.8em 2em }
.poem p { text-indent: -1em; margin-left: 1em; text-align: left }
.sc { font-variant: small-caps }
.caption, figcaption { font-size: 0.8em; text-align: center; text-indent: 0 }
pre { margin: 0.6em 1em; font-size: 0.9em }
.u { text-decoration: underline } .barre { text-decoration: line-through }
ol.roman { list-style-type: upper-roman }
.note { font-size: 0.75em; vertical-align: super }
.saut { page-break-before: always }
table { border-collapse: collapse; margin: 0.6em 0 } td, th { border: 1px solid #000; padding: 4px; font-family: Arial }
.pc { color: red; position: absolute; float: right; columns: 2; font-size: 30px }
"""


def layout_epub(path, title="Mise en page"):
    """A book that exercises what the reader takes from a style sheet: headings, alignment,
    indents, quotations, verse, lists, tables, small capitals, notes, rules, pictures and
    captions, drop caps, page breaks, code. Made up for the tests and the screenshots."""
    chapters = [
        ("Titres et alignements",
         "<h1>Titres et alignements</h1>"
         "<p class='first'>Le premier paragraphe ouvre le chapitre par une grande initiale posée sur deux lignes ; " + LOREM + "</p>"
         "<p>" + LOREM + "</p><p>" + LOREM + "</p>"
         "<h2>Un sous-titre de niveau deux</h2><p class='noindent'>" + LOREM + "</p>"
         "<h3>Un intertitre en italique</h3><p>" + LOREM + "</p>"
         "<h4>Un titre en capitales</h4><p>" + LOREM + "</p>"
         "<p class='centre'>Une ligne centrée<br/>et une seconde, centrée aussi</p>"
         "<p class='droite'>Une signature à droite</p>"
         "<p class='spaced'>Un paragraphe espacé, sans retrait, comme dans un livre de cuisine. " + LOREM + "</p>"
         "<p class='spaced'>Un autre paragraphe espacé, " + LOREM + "</p>"
         "<p class='pc' style='color:blue'>Des couleurs, des colonnes et des tailles en pixels qui ne changent rien.</p>"),
        ("Citations et vers",
         "<h1>Citations et vers</h1>"
         "<p class='epigraph'>Le silence est une longue phrase.<br/>— Un auteur</p>"
         "<p>Avant la citation, " + LOREM + "</p>"
         "<blockquote><p>Une citation en retrait des deux côtés, en italique, qui dure assez longtemps pour aller sur plusieurs lignes. " + LOREM + "</p></blockquote>"
         "<p>Après la citation, la suite du texte reprend.</p>"
         "<div class='poem'><p>Le vent se lève, il faut tenter de vivre,</p><p>L’air immense ouvre et referme mon livre,</p>"
         "<p>La vague en poudre ose jaillir des rocs, et ce vers est assez long pour revenir à la ligne sous lui-même.</p></div>"
         "<p>La lecture de <span class='sc'>Paul Valéry</span> en petites capitales, une note<sup>1</sup>, une autre<span class='note'>2</span>, "
         "H<sub>2</sub>O, un mot <span class='u'>souligné</span> et un <span class='barre'>barré</span>, du <code>code()</code> au fil du texte.</p>"
         "<hr/><p class='noindent'>Après un filet. " + LOREM + "</p>"
         "<pre>ligne un\n  ligne deux, en retrait\nligne trois</pre>"
         "<p>Un texte écrit sur\nplusieurs lignes de la source\nse lit d’un seul tenant.</p>"),
        ("Listes et tableau",
         "<h1>Listes et tableau</h1>"
         "<ul><li>Un premier point</li><li>Un deuxième point, assez long pour aller à la ligne et montrer où le texte revient sous la puce.</li>"
         "<li>Un point avec une liste dedans<ul><li>un sous-point</li><li>un autre sous-point</li></ul></li></ul>"
         "<ol><li>Premier</li><li>Deuxième</li><li>Troisième</li></ol>"
         "<ol class='roman' start='4'><li>Quatre en chiffres romains</li><li>Cinq</li></ol>"
         "<table><thead><tr><th>Ville</th><th>Habitants</th><th>Remarque</th></tr></thead><tbody>"
         "<tr><td>Lausanne</td><td>140 000</td><td>Au bord du lac, en pente, avec un métro qui monte depuis le port.</td></tr>"
         "<tr><td>Genève</td><td>200 000</td><td>Le jet d’eau.</td></tr>"
         "<tr><td>Fribourg</td><td>38 000</td><td><p>Deux langues,</p><p>une ville.</p></td></tr>"
         "</tbody></table>"
         "<p class='noindent'>Le texte reprend après le tableau.</p>"),
        ("Images",
         "<h1>Images</h1><p>Une petite image garde sa taille :</p>"
         "<figure><img src=\"../img/small.png\" alt=\"\"/><figcaption>Une petite image, centrée, avec sa légende.</figcaption></figure>"
         "<p>Une grande image prend toute la largeur :</p>"
         "<div class='figure'><img src=\"../img/one.png\"/><p class='caption'>La grande image et sa légende.</p></div>"
         "<p class='saut'>Ce paragraphe commence une nouvelle page, comme le demande sa feuille de style. " + LOREM + "</p>"
         "<p>" + LOREM + "</p>"),
    ]
    manifest, spine, nav = [], [], []
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("META-INF/container.xml", '<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>')
        z.writestr("OEBPS/img/one.png", picture(900, 600, 60))
        z.writestr("OEBPS/img/small.png", picture(160, 100, 200))
        z.writestr("OEBPS/css/book.css", LAYOUT_CSS)
        for i, (name, body) in enumerate(chapters, 1):
            href = "text/ch%d.xhtml" % i
            z.writestr("OEBPS/" + href, '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml"><head><title>%s</title>'
                       '<link rel="stylesheet" type="text/css" href="../css/book.css"/></head><body>%s</body></html>' % (name, body))
            manifest.append('<item id="c%d" href="%s" media-type="application/xhtml+xml"/>' % (i, href))
            spine.append('<itemref idref="c%d"/>' % i)
            nav.append('<li><a href="%s">%s</a></li>' % (href, name))
        z.writestr("OEBPS/nav.xhtml", "<html><body><nav><ol>%s</ol></nav></body></html>" % "".join(nav))
        z.writestr("OEBPS/content.opf", '<package><metadata><dc:title>%s</dc:title></metadata><manifest>%s'
                   '<item id="nav" href="nav.xhtml" properties="nav" media-type="application/xhtml+xml"/>'
                   '<item id="css" href="css/book.css" media-type="text/css"/></manifest><spine>%s</spine></package>'
                   % (title, "".join(manifest), "".join(spine)))
    return path
