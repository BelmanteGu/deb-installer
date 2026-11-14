"""The window: a horizontal wizard (steps on the left, the page on the right, Back / Continue below), like a macOS installer.
Steps: Select, Overview, Details, Install, Done. Does not read .deb files (debinfo.py) and does not run apt (backend.py)."""
import os
import sys
import threading

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from . import backend, debinfo, states  # noqa: E402

STEPS = ["Select", "Overview", "Details", "Install", "Done"]
LABEL = {"install": "Install", "upgrade": "Upgrade", "reinstall": "Reinstall", "downgrade": "Downgrade"}
DOING = {"install": "Installing", "upgrade": "Upgrading", "reinstall": "Reinstalling", "downgrade": "Downgrading"}
CSS = b"""
.steps { background: alpha(@window_fg_color, 0.05); padding: 24px 12px; min-width: 190px; }
.step { padding: 7px 12px; border-radius: 8px; color: alpha(@window_fg_color, 0.55); }
.step.current { color: @window_fg_color; font-weight: bold; background: alpha(@accent_bg_color, 0.22); }
.step.done { color: @window_fg_color; }
.state-ok image { color: @accent_color; } .state-update image { color: @accent_color; }
.state-done image { color: @success_color; } .state-warning image { color: @warning_color; }
.state-error image { color: @error_color; } .error-page image { color: @error_color; } .done-page image { color: @success_color; }
"""


def human(kb):
    return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb} KB"


def page(*children, spacing=12):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=spacing, margin_top=24, margin_bottom=8,
                  margin_start=28, margin_end=28)
    for c in children: box.append(c)
    return box


def label(text="", css=None, **kw):
    lb = Gtk.Label(label=text, xalign=0, wrap=True, **kw)
    if css: lb.add_css_class(css)
    return lb


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Deb Installer", default_width=820, default_height=520)
        prov = Gtk.CssProvider(); prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.info, self.step, self.running, self.failed, self._file_rows = None, 0, False, False, []
        self.loading = False
        self.state, self.log_lines, self.alt_action = None, [], None
        self.action = "install"
        self.toasts = Adw.ToastOverlay()
        view = Adw.ToolbarView(); view.add_top_bar(Adw.HeaderBar())
        row = Gtk.Box(); row.append(self.build_sidebar())
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.stack = Gtk.Stack(vexpand=True, transition_type=Gtk.StackTransitionType.CROSSFADE)
        for n, p in zip(STEPS, (self.p_select(), self.p_overview(), self.p_details(), self.p_install(), self.p_done())):
            self.stack.add_named(p, n)
        self.stack.add_named(self.p_loading(), "Loading")
        self.stack.add_named(self.p_error(), "Error")
        right.append(self.stack); right.append(self.build_nav()); row.append(right)
        view.set_content(row); self.toasts.set_child(view); self.set_content(self.toasts)
        drop = Gtk.DropTarget.new(Gio.File, Gdk.DragAction.COPY)
        drop.connect("drop", self.on_drop)
        self.add_controller(drop)
        self.goto(0)

    def on_drop(self, target, f, x, y):
        self.open_path(f.get_path())
        return True

    # --- chrome
    def build_sidebar(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4); box.add_css_class("steps")
        self.step_labels = []
        for n in STEPS:
            lb = Gtk.Label(label=n, xalign=0); lb.add_css_class("step"); box.append(lb); self.step_labels.append(lb)
        return box

    def build_nav(self):
        bar = Gtk.Box(spacing=8, margin_top=8, margin_bottom=16, margin_start=28, margin_end=28)
        self.back = Gtk.Button(label="Back"); self.back.connect("clicked", lambda *_: self.on_back())
        self.next = Gtk.Button(label="Continue", halign=Gtk.Align.END, hexpand=True)
        self.next.add_css_class("suggested-action"); self.next.connect("clicked", lambda *_: self.on_next())
        self.alt = Gtk.Button(label="Close", halign=Gtk.Align.END, visible=False)   # secondary action of the page
        self.alt.connect("clicked", lambda *_: self.on_alt())
        bar.append(self.back); bar.append(self.alt); bar.append(self.next)
        return bar

    def goto(self, i):
        self.step = i
        self.stack.set_visible_child_name(STEPS[i])
        for k, lb in enumerate(self.step_labels):
            for c in ("current", "done"): lb.remove_css_class(c)
            if k == i: lb.add_css_class("current")
            elif k < i: lb.add_css_class("done")
            lb.set_label(("✓  " if k < i else "") + STEPS[k])
        st = self.state
        self.back.set_visible(i in (1, 2) or (i == 3 and self.failed))
        self.next.set_visible(not (i == 0 or (i == 3 and not self.failed)))
        self.next.set_sensitive(not (i in (1, 2) and st and not st.can_continue))
        self.next.set_label({0: "Continue", 1: st.next_label if st else "Continue", 2: LABEL[self.action],
                             3: "Try again", 4: "Install another"}[i])
        self.alt_action = {1: "close", 3: "copy", 4: "close"}.get(i) if (i != 1 or (st and st.offer_close)) else None
        self.alt.set_visible(self.alt_action is not None and not (i == 3 and not self.failed))
        self.alt.set_label({"close": "Close", "copy": "Copy log"}.get(self.alt_action, ""))

    def on_alt(self):
        if self.alt_action == "close": self.close()
        elif self.alt_action == "copy":
            self.get_clipboard().set("\n".join(self.log_lines))
            self.toasts.add_toast(Adw.Toast(title="Log copied"))

    def on_back(self):
        self.goto(0 if self.step == 1 else 2 if self.step == 3 else self.step - 1)

    def on_next(self):
        if self.step == 4: self.reset()
        elif self.step == 1: self.goto(2)
        else: self.run_install()

    def reset(self):
        """Back to the first page for another package."""
        self.info, self.state, self.failed = None, None, False
        self.goto(0)

    # --- pages
    def p_select(self):
        pg = Adw.StatusPage(icon_name="package-x-generic-symbolic", title="Install a .deb package",
                            description="Drop a file anywhere on this window, or choose one.", vexpand=True)
        btn = Gtk.Button(label="Choose a file…", halign=Gtk.Align.CENTER)
        btn.add_css_class("suggested-action"); btn.add_css_class("pill"); btn.connect("clicked", self.choose)
        pg.set_child(btn)
        return pg

    def p_overview(self):
        self.icon = Gtk.Image(pixel_size=96, halign=Gtk.Align.START, icon_name="package-x-generic")
        self.title = label(css="title-1"); self.summary = label(css="title-4")
        self.meta = label(css="dim-label")
        self.card = Adw.PreferencesGroup()
        self.card_row = Adw.ActionRow(); self.card_row.set_title_lines(0); self.card_row.set_subtitle_lines(0)
        self.card_icon = Gtk.Image(pixel_size=32); self.card_row.add_prefix(self.card_icon); self.card.add(self.card_row)
        self.desc = Gtk.Label(xalign=0, yalign=0, wrap=True)
        sc = Gtk.ScrolledWindow(child=self.desc, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        head = Gtk.Box(spacing=18)
        head.append(self.icon)
        txt = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4, valign=Gtk.Align.CENTER)
        for w in (self.title, self.summary, self.meta): txt.append(w)
        head.append(txt)
        return page(head, self.card, sc)

    def p_details(self):
        self.group = Adw.PreferencesGroup(); self.rows = {}
        for key, name in (("version", "Version"), ("arch", "Architecture"), ("size", "Installed size"),
                          ("maint", "Maintainer"), ("deps", "Depends")):
            r = Adw.ActionRow(title=name, subtitle_selectable=True); r.add_css_class("property")
            self.group.add(r); self.rows[key] = r
        self.files_row = Adw.ExpanderRow(title="Files"); self.group.add(self.files_row)
        sc = Gtk.ScrolledWindow(child=self.group, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        return page(label("Details", "title-2"), sc)

    def p_install(self):
        self.progress = Gtk.ProgressBar(); self.result = label()
        self.log = Gtk.TextView(editable=False, monospace=True, cursor_visible=False, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        sc = Gtk.ScrolledWindow(child=self.log, vexpand=True); sc.add_css_class("card")
        self.install_title = label("Installing…", "title-2")
        return page(self.install_title, self.progress, self.result, sc)

    def p_loading(self):
        """Shown while a .deb is read: a spinner, then a check mark so you can see it worked."""
        self.spinner = Gtk.Spinner(spinning=True, width_request=64, height_request=64, halign=Gtk.Align.CENTER)
        self.check = Gtk.Image(icon_name="object-select-symbolic", pixel_size=64, halign=Gtk.Align.CENTER, visible=False)
        self.check.add_css_class("success")
        self.loading_page = Adw.StatusPage(title="Reading the package…", vexpand=True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, halign=Gtk.Align.CENTER)
        box.append(self.spinner); box.append(self.check)
        self.loading_page.set_child(box)
        return self.loading_page

    def p_error(self):
        self.error_page = Adw.StatusPage(icon_name="dialog-error-symbolic", title="Error", vexpand=True)
        self.error_page.add_css_class("error-page")
        btn = Gtk.Button(label="Choose another file…", halign=Gtk.Align.CENTER)
        btn.add_css_class("suggested-action"); btn.add_css_class("pill"); btn.connect("clicked", self.choose)
        self.error_page.set_child(btn)
        return self.error_page

    def show_error(self, title, text):
        self.loading = False
        self.error_page.set_title(title); self.error_page.set_description(GLib.markup_escape_text(text))
        self.stack.set_visible_child_name("Error"); self.back.set_visible(False); self.next.set_visible(False)
        self.alt.set_visible(False)

    def p_done(self):
        self.done_page = Adw.StatusPage(icon_name="object-select-symbolic", title="Done", vexpand=True)
        self.done_page.add_css_class("done-page")
        return self.done_page

    # --- actions
    def choose(self, *_):
        dlg = Gtk.FileDialog(title="Open a .deb")
        flt = Gtk.FileFilter(name="Debian packages"); flt.add_pattern("*.deb")
        store = Gio.ListStore.new(Gtk.FileFilter); store.append(flt); dlg.set_filters(store)
        dlg.open(self, None, self._chosen)

    def _chosen(self, dlg, res):
        try: f = dlg.open_finish(res)
        except GLib.Error: return
        self.open_path(f.get_path())

    def open_path(self, path):
        """Reads the .deb on a thread (big packages take seconds) with a spinner, then shows the overview."""
        if self.running or getattr(self, "loading", False): return
        self.loading = True
        self.spinner.set_visible(True); self.spinner.start(); self.check.set_visible(False)
        self.loading_page.set_title("Reading the package…")
        self.loading_page.set_description(GLib.markup_escape_text(os.path.basename(path)))
        self.stack.set_visible_child_name("Loading"); self.back.set_visible(False); self.next.set_visible(False)
        def work():
            try: info, err = debinfo.read_deb(path), None
            except debinfo.DebError as e: info, err = None, str(e)
            GLib.idle_add(self.loaded, info, err, priority=GLib.PRIORITY_DEFAULT)
        threading.Thread(target=work, daemon=True).start()

    def loaded(self, info, err):
        if err:
            self.spinner.stop(); self.info = None; self.state = None
            self.show_error(*states.read_error(err)); return
        self.info = info
        self.spinner.stop(); self.spinner.set_visible(False); self.check.set_visible(True)
        self.loading_page.set_title("Package loaded")
        self.loading_page.set_description(f"{info.name} {info.version}")
        GLib.timeout_add(700, self.show_info)

    def show_info(self):
        self.loading = False
        self.fill()
        return False

    def fill(self):
        i = self.info
        self.failed = False
        self.title.set_text(i.name); self.summary.set_text(i.summary)
        self.meta.set_text(f"Version {i.version} · {i.arch} · {human(i.installed_size_kb)} installed")
        self.desc.set_text(i.description or "No description.")
        self.set_icon(i.icon)
        vals = {"version": i.version, "arch": i.arch, "size": human(i.installed_size_kb),
                "maint": i.fields.get("Maintainer", "-"), "deps": "\n".join(i.depends) or "none"}
        for k, v in vals.items(): self.rows[k].set_subtitle(GLib.markup_escape_text(v))
        self.rows["deps"].set_subtitle_lines(0)
        for r in self._file_rows: self.files_row.remove(r)
        self._file_rows = []
        for p, size in i.files[:300]:
            r = Adw.ActionRow(title=GLib.markup_escape_text(p), subtitle=f"{size} bytes"); r.set_title_lines(1)
            self.files_row.add_row(r); self._file_rows.append(r)
        self.files_row.set_subtitle(f"{len(i.files)} files" + (" (first 300 shown)" if len(i.files) > 300 else ""))
        self.log.get_buffer().set_text("")
        reason = backend.supported()
        self.action, cur = ("install", None) if reason else backend.action_for(i)
        st = self.state = states.overview_state(i, self.action, cur, reason, backend.note())
        self.card_row.set_title(st.title); self.card_row.set_subtitle(GLib.markup_escape_text(st.text))
        self.card_icon.set_from_icon_name(st.icon)
        for c in ("ok", "update", "warning", "done", "error"): self.card_row.remove_css_class(f"state-{c}")
        self.card_row.add_css_class(f"state-{st.kind}")
        self.goto(1)

    def set_icon(self, data):
        try:
            if not data: raise ValueError
            self.icon.set_from_paintable(Gdk.Texture.new_from_bytes(GLib.Bytes.new(data)))
        except (GLib.Error, ValueError):
            self.icon.set_from_icon_name("package-x-generic")

    def run_install(self):
        self.running, self.failed = True, False
        self.log.get_buffer().set_text(""); self.log_lines = []; self.result.set_text("Waiting for your password…")
        self.install_title.set_text(f"{DOING[self.action]} {self.info.name}…"); self.progress.set_visible(True)
        self.goto(3)
        self.pulse = GLib.timeout_add(120, lambda: self.progress.pulse() or True)
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self):
        buf = self.log.get_buffer()
        def line(t):
            def add():
                self.log_lines.append(t)
                buf.insert(buf.get_end_iter(), t + "\n"); self.log.scroll_to_mark(buf.get_insert(), 0, False, 0, 0)
                self.result.set_text("Working…")
            GLib.idle_add(add, priority=GLib.PRIORITY_DEFAULT)
        try: code = backend.install(self.info, line)
        except OSError as e: line(str(e)); code = 1
        GLib.idle_add(self.finished, code, priority=GLib.PRIORITY_DEFAULT)

    def finished(self, code):
        GLib.source_remove(self.pulse); self.running = False
        if code == 0:
            word = {"install": "installed", "upgrade": "updated", "reinstall": "reinstalled", "downgrade": "downgraded"}[self.action]
            self.done_page.set_title(f"{self.info.name} {self.info.version}")
            self.done_page.set_description(f"Successfully {word}.")
            self.goto(4)
        else:
            self.failed = True
            title, text = states.failure(code, "\n".join(self.log_lines))
            self.progress.set_visible(False)
            self.install_title.set_text(title); self.result.set_text(text)
            self.goto(3)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id="io.github.debinstaller", flags=Gio.ApplicationFlags.HANDLES_OPEN)
        self.win = None

    def window(self):
        if not self.win: self.win = Window(self)
        return self.win

    def do_activate(self): self.window().present()

    def do_open(self, files, n, hint):
        w = self.window(); w.present(); w.open_path(files[0].get_path())


def main():
    # The app icon lives in data/icons (when installed, the system icon theme has it instead).
    Gtk.init()
    Gtk.IconTheme.get_for_display(Gdk.Display.get_default()).add_search_path(
        os.path.join(os.path.dirname(__file__), "..", "data", "icons"))
    Gtk.Window.set_default_icon_name("io.github.debinstaller")
    return App().run(sys.argv)
