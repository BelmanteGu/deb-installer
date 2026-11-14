"""Gives a .deb file its own icon in the file manager: the Deb Installer icon with the icon of the package inside it in the
corner. It writes a small PNG and sets the file's `metadata::custom-icon` (stored by GIO next to your settings, the .deb
itself is not touched). Does nothing when the package has no icon. Set DEB_INSTALLER_NO_FILE_ICON=1 to turn it off.
Why not a thumbnailer: file managers skip thumbnails for big files (Nautilus: over 50 MB), and big packages are common."""
import hashlib
import io
import os

try:
    import cairo
except ImportError:  # optional: without it .deb files just keep the generic .deb icon
    cairo = None
import gi
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gio, GLib  # noqa: E402

SIZE = 256
BADGE = 118  # the package icon's box, bottom right
BASE = ("icons/hicolor/256x256/apps/io.github.debinstaller.png",)


def _data_dirs():
    return [GLib.get_user_data_dir(), *GLib.get_system_data_dirs(), os.path.join(os.path.dirname(__file__), "..", "assets")]


def _base_png():
    for d in _data_dirs():
        for rel in (*BASE, "icon-256.png"):
            p = os.path.join(d, rel)
            if os.path.exists(p): return p
    return None


def _surface(data):
    """A cairo surface from PNG or SVG bytes (GDK decodes both)."""
    png = Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)).save_to_png_bytes().get_data()
    return cairo.ImageSurface.create_from_png(io.BytesIO(png))


def _rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    for cx, cy, a in ((x + w - r, y + r, -90), (x + w - r, y + h - r, 0), (x + r, y + h - r, 90), (x + r, y + r, 180)):
        cr.arc(cx, cy, r, a * 3.14159265 / 180, (a + 90) * 3.14159265 / 180)
    cr.close_path()


def compose(icon_bytes, out_path):
    """Writes the composite PNG; returns False if it could not."""
    base = _base_png()
    if not base or not icon_bytes: return False
    pkg = _surface(icon_bytes)
    s = cairo.ImageSurface(cairo.FORMAT_ARGB32, SIZE, SIZE)
    cr = cairo.Context(s)
    cr.set_source_surface(cairo.ImageSurface.create_from_png(base), 0, 0); cr.paint()
    x = y = SIZE - BADGE - 6
    _rounded(cr, x + 1, y + 4, BADGE, BADGE, 26); cr.set_source_rgba(0, 0, 0, .3); cr.fill()      # shadow
    _rounded(cr, x, y, BADGE, BADGE, 26); cr.set_source_rgb(1, 1, 1); cr.fill()                    # white tile
    pad = 9; side = BADGE - 2 * pad
    cr.save(); _rounded(cr, x + pad, y + pad, side, side, 18); cr.clip()
    cr.translate(x + pad, y + pad); cr.scale(side / pkg.get_width(), side / pkg.get_height())
    cr.set_source_surface(pkg, 0, 0); cr.paint(); cr.restore()
    s.write_to_png(out_path)
    return True


def apply(deb_path, info):
    """Sets the composite as the icon of `deb_path`. Returns the PNG path, or None."""
    if cairo is None or os.environ.get("DEB_INSTALLER_NO_FILE_ICON") or not info.icon: return None
    d = os.path.join(GLib.get_user_data_dir(), "deb-installer", "file-icons")
    os.makedirs(d, exist_ok=True)
    out = os.path.join(d, hashlib.sha1(info.icon + info.name.encode()).hexdigest()[:16] + ".png")
    try:
        if not os.path.exists(out) and not compose(info.icon, out): return None
        Gio.File.new_for_path(deb_path).set_attribute_string("metadata::custom-icon", Gio.File.new_for_path(out).get_uri(), 0, None)
        return out
    except (GLib.Error, OSError, cairo.Error):
        return None
