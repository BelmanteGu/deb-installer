"""The version and path rules of the .deb -> pacman conversion (no pacman needed)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from debinstaller import archconv

assert archconv.pkgver("5.11492.2") == "5.11492.2-1"
assert archconv.pkgver("1.2-3") == "1.2_3-1"          # hyphen is not allowed in a pacman version
assert archconv.pkgver("2:1.0~rc1-4") == "1.0_rc1_4-1"  # epoch dropped, tilde replaced
assert archconv._dest("./usr/bin/x") == "usr/bin/x"
assert archconv._dest("./lib/x86_64/y.so") == "usr/lib/x86_64/y.so"  # Arch keeps /lib as a symlink to /usr/lib
assert archconv._dest("./bin/tool") == "usr/bin/tool"
print("ok")
