"""The texts for each situation (no GTK needed)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from types import SimpleNamespace as NS
from debinstaller import states as S

pkg = NS(name="claude-desktop", version="2.0", arch="amd64")
st = S.overview_state(pkg, "install", None, None, arch="x86_64" and "amd64"); assert st.kind == "ok" and st.can_continue
st = S.overview_state(pkg, "reinstall", "2.0-1", None, arch="amd64"); assert st.title == "Already installed" and st.next_label == "Reinstall anyway" and st.offer_close
st = S.overview_state(pkg, "upgrade", "1.0", None, arch="amd64"); assert st.kind == "update" and "1.0" in st.text
st = S.overview_state(pkg, "downgrade", "3.0", None, arch="amd64"); assert st.kind == "warning"
st = S.overview_state(pkg, "install", None, None, arch="arm64"); assert st.kind == "error" and not st.can_continue and "amd64" in st.title
st = S.overview_state(NS(name="x", version="1", arch="all"), "install", None, None, arch="arm64"); assert st.kind == "ok"
st = S.overview_state(pkg, "install", None, "no apt", arch="amd64"); assert not st.can_continue
assert S.failure(126, "")[0] == "Installation cancelled"
assert S.failure(1, "error: failed to commit transaction (conflicting files)")[0] == "Files conflict with another package"
assert S.failure(100, "E: Unable to locate package foo")[0] == "Missing dependencies"
assert S.failure(1, "Could not get lock /var/lib/dpkg/lock")[0] == "Another installer is running"
assert S.failure(3, "boom")[0] == "Installation failed"
assert S.read_error("not a .deb (no ar header)")[0] == "This is not a .deb file"
assert S.read_error("[Errno 2] No such file")[0] == "File not found"
assert S.read_error("EOF")[0] == "The package looks damaged"
print("ok")
