"""Builds a tiny .deb in memory (no dpkg needed) and checks that debinfo reads it."""
import gzip, io, lzma, os, sys, tarfile, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from debinstaller import debinfo

def tar(files):
    b = io.BytesIO()
    with tarfile.open(fileobj=b, mode="w") as t:
        for n, d in files.items():
            i = tarfile.TarInfo(n); i.size = len(d); t.addfile(i, io.BytesIO(d))
    return b.getvalue()

def ar(members):
    out = b"!<arch>\n"
    for n, d in members.items():
        out += f"{n:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(d):<10}`\n".encode() + d + (b"\n" if len(d) & 1 else b"")
    return out

ctl = b"Package: hello\nVersion: 1.2-3\nArchitecture: amd64\nInstalled-Size: 2048\nDepends: libc6, bash\nDescription: Says hello\n A longer text.\n .\n Second paragraph.\n"
deb = ar({"debian-binary": b"2.0\n", "control.tar.gz": gzip.compress(tar({"./control": ctl})),
          "data.tar.xz": lzma.compress(tar({"./usr/bin/hello": b"#!/bin/sh\n", "./usr/share/doc/hello": b"x"}))})
with tempfile.NamedTemporaryFile(suffix=".deb", delete=False) as f: f.write(deb)
i = debinfo.read_deb(f.name)
assert (i.name, i.version, i.arch, i.summary) == ("hello", "1.2-3", "amd64", "Says hello"), i
assert i.depends == ["libc6", "bash"] and i.installed_size_kb == 2048
assert i.description == "A longer text.\n\nSecond paragraph.", repr(i.description)
assert [p for p, _ in i.files] == ["/usr/bin/hello", "/usr/share/doc/hello"], i.files
try: debinfo.read_deb(__file__); raise SystemExit("should fail")
except debinfo.DebError: pass
print("ok")
