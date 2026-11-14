#!/usr/bin/env python3
"""Builds deb-installer_<version>_all.deb in pure Python (no dpkg needed, so it runs on any distro and in CI).
It packs the app, a launcher, the menu entry, the icons and the license. It does not sign anything.

usage: python3 tools/build_deb.py [output folder]      (default: dist/)
"""
import gzip
import io
import lzma
import os
import sys
import tarfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from debinstaller import __version__  # noqa: E402

NAME = "deb-installer"
MTIME = int(os.environ.get("SOURCE_DATE_EPOCH", time.time()))
CONTROL = """Package: {name}
Version: {version}
Architecture: all
Maintainer: BelmanteGu <noreply@github.com>
Installed-Size: {size}
Depends: python3 (>= 3.9), python3-gi, python3-gi-cairo, gir1.2-gtk-4.0 (>= 4.10), gir1.2-adw-1 (>= 1.4), apt, pkexec | policykit-1
Recommends: zstd
Section: utils
Priority: optional
Homepage: https://github.com/BelmanteGu/deb-installer
Description: Graphical installer for .deb packages
 Open or drop a .deb file, see its icon, version, size, dependencies and files,
 and install, upgrade, reinstall or downgrade it in a step-by-step wizard.
 Dependencies are resolved by apt and the password is asked by polkit.
"""
LAUNCHER = """#!/bin/sh
PYTHONPATH=/usr/lib/deb-installer exec python3 -m debinstaller "$@"
"""


def collect():
    """{path inside the package: (bytes, mode)}"""
    files = {}
    def add(dest, src_or_bytes, mode=0o644):
        data = src_or_bytes if isinstance(src_or_bytes, bytes) else open(os.path.join(ROOT, src_or_bytes), "rb").read()
        files[dest] = (data, mode)
    for f in sorted(os.listdir(os.path.join(ROOT, "debinstaller"))):
        if f.endswith(".py"): add(f"usr/lib/{NAME}/debinstaller/{f}", f"debinstaller/{f}")
    add("usr/bin/deb-installer", LAUNCHER.encode(), 0o755)
    desktop = open(os.path.join(ROOT, "data/debinstaller.desktop")).read()
    add("usr/share/applications/io.github.debinstaller.desktop", desktop.encode())
    add("usr/share/icons/hicolor/scalable/apps/io.github.debinstaller.svg", "data/icons/hicolor/scalable/apps/io.github.debinstaller.svg")
    add("usr/share/icons/hicolor/scalable/mimetypes/io.github.debinstaller.deb-file.svg", "data/icons/hicolor/scalable/mimetypes/io.github.debinstaller.deb-file.svg")
    add("usr/share/mime/packages/io.github.debinstaller.xml", "data/mime/io.github.debinstaller.xml")
    add("usr/share/icons/hicolor/256x256/apps/io.github.debinstaller.png", "assets/icon-256.png")
    add(f"usr/share/doc/{NAME}/copyright", "LICENSE")
    add(f"usr/share/doc/{NAME}/README.md", "README.md")
    return files


def tar_bytes(entries, compress):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.GNU_FORMAT) as t:
        seen = set()
        for path in sorted(entries):
            parts = path.split("/")
            for k in range(1, len(parts)):  # directories first
                d = "./" + "/".join(parts[:k])
                if d not in seen and "/".join(parts[:k]) != "":
                    seen.add(d); i = tarfile.TarInfo(d + "/"); i.type = tarfile.DIRTYPE; i.mode = 0o755; i.mtime = MTIME
                    i.uname = i.gname = "root"; t.addfile(i)
            data, mode = entries[path]
            i = tarfile.TarInfo("./" + path); i.size = len(data); i.mode = mode; i.mtime = MTIME; i.uname = i.gname = "root"
            t.addfile(i, io.BytesIO(data))
    return compress(buf.getvalue())


def ar(members):
    out = b"!<arch>\n"
    for name, data in members:
        out += f"{name:<16}{MTIME:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n".encode() + data + (b"\n" if len(data) & 1 else b"")
    return out


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "dist")
    os.makedirs(outdir, exist_ok=True)
    files = collect()
    size = sum(len(d) for d, _ in files.values()) // 1024 + 1
    control = CONTROL.format(name=NAME, version=__version__, size=size).encode()
    ctl_tar = tar_bytes({"control": (control, 0o644)}, lambda b: gzip.compress(b, mtime=0))
    data_tar = tar_bytes(files, lambda b: lzma.compress(b, preset=6))
    deb = ar([("debian-binary", b"2.0\n"), ("control.tar.gz", ctl_tar), ("data.tar.xz", data_tar)])
    path = os.path.join(outdir, f"{NAME}_{__version__}_all.deb")
    with open(path, "wb") as f: f.write(deb)
    print(path, f"{len(deb) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
