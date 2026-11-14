#!/usr/bin/env python3
"""Draws one screenshot per situation of the wizard into docs/media/ (already installed, update, older version, wrong
architecture, unreadable file, cancelled, missing dependencies, done...). The system's answers are SIMULATED (what apt/pacman
would say), the screens are the real ones. usage: python3 tools/state_shots.py <some .deb> <output folder>"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gi
gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1")
from gi.repository import GLib, Gtk, Graphene
from debinstaller import app as A, backend

DEB, OUT = os.path.abspath(sys.argv[1]), sys.argv[2]
app = A.App(); app.set_application_id("io.github.debinstaller.stateshots")
real_action, real_support, real_install = backend.action_for, backend.supported, backend.install
real_read = A.debinfo.read_deb

def as_amd64(path):  # the same package, declared as amd64, to show the wrong-architecture screen
    i = real_read(path); i.fields["Architecture"] = "amd64"; return i

def snap(w, name):
    W, H = w.get_width(), w.get_height(); s = Gtk.Snapshot(); Gtk.WidgetPaintable.new(w).snapshot(s, W, H)
    w.get_native().get_renderer().render_texture(s.to_node(), Graphene.Rect().init(0, 0, W, H)).save_to_png(f"{OUT}/{name}.png")

def fake_install(code, lines):
    def f(info, on_line):
        for l in lines: on_line(l)
        return code
    return f

CASES = [  # (file name, setup, what to do after the package loads)
    ("estado-pronto", lambda: None, None),
    ("estado-ja-instalado", lambda: setattr(backend, "action_for", lambda i: ("reinstall", i.version + "-1")), None),
    ("estado-atualizacao", lambda: setattr(backend, "action_for", lambda i: ("upgrade", "0.0.9-1")), None),
    ("estado-versao-antiga", lambda: setattr(backend, "action_for", lambda i: ("downgrade", "9.9.9-1")), None),
    ("estado-arquitetura", lambda: (setattr(A.states, "machine_arch", lambda: "arm64"), setattr(A.debinfo, "read_deb", as_amd64)), None),
    ("estado-sem-suporte", lambda: setattr(backend, "supported", lambda: "This system has neither apt-get nor pacman (or no pkexec): it cannot install .deb packages."), None),
    ("falha-cancelado", lambda: setattr(backend, "install", fake_install(126, ["Error executing command as another user: Not authorized"])), "install"),
    ("falha-dependencias", lambda: setattr(backend, "install", fake_install(100, ["Reading package lists...", "E: Unable to locate package libfoo1", "E: Unmet dependencies."])), "install"),
    ("falha-conflito", lambda: setattr(backend, "install", fake_install(1, ["error: failed to commit transaction (conflicting files)", "deb-installer: /usr/bin/deb-installer exists in filesystem"])), "install"),
    ("concluido", lambda: setattr(backend, "install", fake_install(0, ["Converting the .deb to a pacman package…", "installing deb-installer (0.1.0-1)..."])), "install"),
    ("erro-arquivo", lambda: None, "bad"),
]

def reset_backend():
    backend.action_for, backend.supported, backend.install = real_action, real_support, real_install
    A.states.machine_arch = lambda: "amd64"; A.debinfo.read_deb = real_read

def run(w, i=0):
    if i >= len(CASES): app.quit(); return False
    name, setup, then = CASES[i]
    reset_backend(); setup(); w.reset()
    bad = os.path.join(OUT, "..", "..", "README.md")  # a real file that is not a .deb
    w.open_path(os.path.abspath(bad) if then == "bad" else DEB)
    def after_load():
        if then == "install": w.goto(2); GLib.timeout_add(300, lambda: (w.run_install(), False)[1]); delay = 1500
        else: delay = 100
        GLib.timeout_add(delay, lambda: (snap(w, name), GLib.timeout_add(150, lambda: (run(w, i + 1), False)[1]), False)[2])
        return False
    GLib.timeout_add(2200, after_load)
    return False

def go(*_):
    w = app.window(); w.set_default_size(820, 520); w.stack.set_transition_type(Gtk.StackTransitionType.NONE); w.present()
    GLib.timeout_add(1000, lambda: (run(w), False)[1])
app.connect("activate", go); app.run([])
