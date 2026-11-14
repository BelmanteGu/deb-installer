"""Reads a .deb without dpkg: the control fields and the file list. Pure Python, so it works on any distro.
Does not install anything and does not verify signatures (a plain .deb has none)."""
import io
import lzma
import gzip
import bz2
import subprocess
import tarfile
from dataclasses import dataclass, field


class DebError(Exception):
    pass


@dataclass
class DebInfo:
    path: str
    fields: dict = field(default_factory=dict)
    files: list = field(default_factory=list)  # (path, size) of regular files and links
    icon: bytes = b""  # the app's icon (PNG or SVG) if the package carries one

    @property
    def name(self): return self.fields.get("Package", "?")
    @property
    def version(self): return self.fields.get("Version", "?")
    @property
    def arch(self): return self.fields.get("Architecture", "?")
    @property
    def summary(self): return self.fields.get("Description", "").split("\n", 1)[0]
    @property
    def description(self):
        parts = self.fields.get("Description", "").split("\n")[1:]
        return "\n".join("" if p.strip() == "." else p.strip() for p in parts).strip()
    @property
    def installed_size_kb(self): return int(self.fields.get("Installed-Size", "0") or 0)
    @property
    def depends(self):
        raw = self.fields.get("Depends", "")
        return [d.strip() for d in raw.split(",") if d.strip()]


def _members(data):
    """Members of an ar archive: {name: bytes}."""
    if data[:8] != b"!<arch>\n":
        raise DebError("not a .deb (no ar header)")
    out, pos = {}, 8
    while pos + 60 <= len(data):
        hdr = data[pos:pos + 60]
        name = hdr[:16].decode("ascii", "replace").strip().rstrip("/")
        try:
            size = int(hdr[48:58])
        except ValueError:
            raise DebError("damaged ar header")
        out[name] = data[pos + 60:pos + 60 + size]
        pos += 60 + size + (size & 1)
    return out


def _decompress(name, blob):
    if name.endswith(".gz"): return gzip.decompress(blob)
    if name.endswith(".xz"): return lzma.decompress(blob)
    if name.endswith(".bz2"): return bz2.decompress(blob)
    if name.endswith(".zst"):
        try:
            from compression import zstd  # Python 3.14+
            return zstd.decompress(blob)
        except ImportError:
            r = subprocess.run(["zstd", "-dc"], input=blob, capture_output=True)
            if r.returncode: raise DebError("this package uses zstd and no zstd decoder is available")
            return r.stdout
    return blob


def _tar_of(members, prefix):
    for n, blob in members.items():
        if n.startswith(prefix):
            return tarfile.open(fileobj=io.BytesIO(_decompress(n, blob)))
    raise DebError(f"{prefix} missing: not a valid .deb")


def parse_control(text):
    fields, key = {}, None
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and key:
            fields[key] += "\n" + line
        elif ":" in line:
            key, _, val = line.partition(":")
            fields[key.strip()] = val.strip()
    return fields


def read_deb(path):
    try:
        with open(path, "rb") as f:
            members = _members(f.read())
        with _tar_of(members, "control.tar") as t:
            ctl = next((m for m in t.getmembers() if m.name.lstrip("./") == "control"), None)
            if not ctl: raise DebError("no control file")
            fields = parse_control(t.extractfile(ctl).read().decode("utf-8", "replace"))
        with _tar_of(members, "data.tar") as t:
            ms = t.getmembers()
            files = [(m.name.lstrip("."), m.size) for m in ms if m.isfile() or m.issym()]
            icon = _find_icon(t, ms, fields.get("Package", ""))
    except (OSError, tarfile.TarError, lzma.LZMAError, EOFError) as e:
        raise DebError(str(e))
    if "Package" not in fields: raise DebError("control has no Package field")
    return DebInfo(path, fields, sorted(files), icon)


def _find_icon(t, ms, pkg):
    """The best icon: the one the .desktop file names (else one named like the package), SVG first, else the largest PNG up to 512 px."""
    names = {pkg}
    for m in ms:
        p = m.name.lstrip(".")
        if p.startswith("/usr/share/applications/") and p.endswith(".desktop") and m.isfile():
            for line in t.extractfile(m).read().decode("utf-8", "replace").splitlines():
                if line.startswith("Icon="): names.add(line[5:].strip())
    best, best_score = None, 0
    for m in ms:
        p = m.name.lstrip(".")
        if not m.isfile() or not p.startswith(("/usr/share/icons/", "/usr/share/pixmaps/")): continue
        base, _, ext = p.rpartition("/")[2].rpartition(".")
        if base not in names or ext not in ("png", "svg"): continue
        size = next((int(d.split("x")[0]) for d in p.split("/") if "x" in d and d.split("x")[0].isdigit()), 64)
        score = 1000 if ext == "svg" else (size if size <= 512 else 0)
        if score > best_score: best, best_score = m, score
    return t.extractfile(best).read() if best else b""



def open_data_tar(path):
    """The package's data.tar as an open tarfile (the caller closes it)."""
    try:
        with open(path, "rb") as f: members = _members(f.read())
        return _tar_of(members, "data.tar")
    except (OSError, tarfile.TarError, lzma.LZMAError, EOFError) as e:
        raise DebError(str(e))


def maintainer_scripts(path):
    """Names of the maintainer scripts (preinst, postinst, prerm, postrm) the .deb carries."""
    try:
        with open(path, "rb") as f: members = _members(f.read())
        with _tar_of(members, "control.tar") as t:
            return [n for n in (m.name.lstrip("./") for m in t.getmembers() if m.isfile())
                    if n in ("preinst", "postinst", "prerm", "postrm")]
    except (OSError, tarfile.TarError, lzma.LZMAError, EOFError, DebError):
        return []
