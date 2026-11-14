"""The macOS build's Info.plist completed after PyInstaller: the version, the oldest macOS the
bundle runs on, and the books the app opens from the Finder (Open With, the Dock icon), as an
alternative, never the default.
usage: python packaging/macos-info.py "dist/Readers Books.app" 1.20.2"""
import os
import plistlib
import re
import subprocess
import sys


def minimum_macos(app):
    """The highest `minos` of the bundle's Mach-O files, for the architecture of its executable:
    a Mac older than one of its libraries must be told by the Finder, not see the app vanish."""
    with open(app + "/Contents/Info.plist", "rb") as f:
        exe = app + "/Contents/MacOS/" + plistlib.load(f)["CFBundleExecutable"]
    arch = subprocess.run(["lipo", "-archs", exe], capture_output=True, text=True).stdout.split()[0]
    best, where = (10, 13), exe
    for root, _dirs, files in os.walk(app):
        for name in files:
            path = os.path.join(root, name)
            if os.path.islink(path):
                continue
            with open(path, "rb") as f:
                magic = f.read(4)
            if magic not in (b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xce\xfa\xed\xfe"):
                continue
            out = subprocess.run(["otool", "-arch", arch, "-l", path], capture_output=True, text=True).stdout
            # LC_BUILD_VERSION says "minos 14.0", the older LC_VERSION_MIN_MACOSX "version 10.13"
            found = re.findall(r"^\s*minos (\d+)\.(\d+)", out, re.M) or re.findall(
                r"LC_VERSION_MIN_MACOSX\n.*\n\s*version (\d+)\.(\d+)", out)
            for v in found:
                v = (int(v[0]), int(v[1]))
                if v > best:
                    best, where = v, path
    print("oldest macOS: %d.%d (%s, %s)" % (best + (os.path.relpath(where, app), arch)))
    return "%d.%d" % best


app, version = sys.argv[1], sys.argv[2]
path = app + "/Contents/Info.plist"
minimum = minimum_macos(app)
with open(path, "rb") as f:
    info = plistlib.load(f)
info["CFBundleShortVersionString"] = version
info["CFBundleVersion"] = version
info["LSMinimumSystemVersion"] = minimum
info["CFBundleDocumentTypes"] = [
    {"CFBundleTypeName": "EPUB book", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
     "LSItemContentTypes": ["org.idpf.epub-container"]},
    # MOBI, Kindle, FictionBook and plain text have no type of the system's own
    {"CFBundleTypeName": "E-book", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
     "CFBundleTypeExtensions": ["mobi", "prc", "azw", "azw3", "fb2"]},
    {"CFBundleTypeName": "Plain text", "CFBundleTypeRole": "Viewer", "LSHandlerRank": "Alternate",
     "CFBundleTypeExtensions": ["txt"]},
]
with open(path, "wb") as f:
    plistlib.dump(info, f)
print("Info.plist:", version, "macOS", minimum, len(info["CFBundleDocumentTypes"]), "document types")
