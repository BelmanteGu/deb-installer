"""Talks to the system. Two kinds are supported: Debian-based (apt-get through pkexec: apt resolves the dependencies)
and Arch-based (the .deb is converted by archconv.py and installed with pacman -U through pkexec). The password prompt is
polkit's, this program never sees it. Does not parse .deb files (debinfo.py)."""
import os
import shutil
import subprocess
import tempfile

from . import archconv


def system():
    """'apt', 'pacman' or None."""
    if shutil.which("apt-get") and shutil.which("pkexec"): return "apt"
    if shutil.which("pacman") and shutil.which("pkexec"): return "pacman"
    return None


def supported():
    """None if this system can install, else the reason."""
    if system(): return None
    return "This system has neither apt-get nor pacman (or no pkexec): it cannot install .deb packages."


def note():
    """A line to show before installing, when this system needs a conversion."""
    if system() == "pacman":
        return ("This is an Arch-based system: the package is converted to a pacman package. Its Debian dependencies are not "
                "checked and its install scripts are not run. Remove it later with: sudo pacman -R <name>")
    return ""


def installed_version(name):
    """The installed version of `name`, or None."""
    if system() == "pacman":
        r = subprocess.run(["pacman", "-Q", name], capture_output=True, text=True)
        return r.stdout.split()[1] if r.returncode == 0 else None
    if not shutil.which("dpkg-query"): return None
    r = subprocess.run(["dpkg-query", "-W", "-f=${Status}|${Version}", name], capture_output=True, text=True)
    if r.returncode or "installed" not in r.stdout.split("|")[0].split() or "not-installed" in r.stdout: return None
    return r.stdout.split("|")[1]


def compare(a, b):
    """-1, 0, 1 as the system orders the versions a and b."""
    if system() == "pacman":
        return int(subprocess.run(["vercmp", a, b], capture_output=True, text=True).stdout.strip() or 0)
    for op, res in (("lt", -1), ("eq", 0)):
        if subprocess.run(["dpkg", "--compare-versions", a, op, b]).returncode == 0: return res
    return 1


def action_for(info):
    """('install'|'upgrade'|'reinstall'|'downgrade', installed version or None)."""
    cur = installed_version(info.name)
    if cur is None: return "install", None
    new = archconv.pkgver(info.version) if system() == "pacman" else info.version
    c = compare(new, cur)
    return ("upgrade" if c > 0 else "downgrade" if c < 0 else "reinstall"), cur


def _run(cmd, on_line, env=None):
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    for line in p.stdout: on_line(line.rstrip())
    return p.wait()


def install(info, on_line):
    """Installs the package; calls on_line for each output line; returns the exit code."""
    env = dict(os.environ, LC_ALL="C.UTF-8")
    if system() == "pacman":
        with tempfile.TemporaryDirectory(prefix="debinstaller-") as tmp:
            on_line("Converting the .deb to a pacman package…")
            pkg, skipped = archconv.convert(info, tmp)
            if skipped: on_line("Not run on this system: " + ", ".join(skipped))
            os.chmod(tmp, 0o755); os.chmod(pkg, 0o644)  # pkexec runs pacman as root, which must be able to read it
            return _run(["pkexec", "pacman", "-U", "--noconfirm", pkg], on_line, env)
    cmd = ["pkexec", "env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "install", "-y", "--allow-downgrades",
           os.path.abspath(info.path)]
    return _run(cmd, on_line, env)
