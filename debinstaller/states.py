"""What each situation looks like to the user: the text and icon for "already installed", "update", "older version",
"wrong architecture", a failed install, an unreadable file... Pure functions, no GTK, so they are easy to test.
Does not decide how to install (backend.py) and does not draw anything (app.py)."""
import platform
from dataclasses import dataclass

DEB_ARCH = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf", "i686": "i386", "i386": "i386"}


def machine_arch():
    return DEB_ARCH.get(platform.machine(), platform.machine())


@dataclass
class State:
    kind: str            # ok | update | warning | done | error
    icon: str
    title: str
    text: str
    can_continue: bool = True
    next_label: str = "Continue"
    offer_close: bool = False


def overview_state(info, action, installed, reason, note="", arch=None):
    """The status card of the Overview page. `action` is install/upgrade/reinstall/downgrade, `installed` the current
    version or None, `reason` why this system cannot install (or None)."""
    arch = arch or machine_arch()
    extra = ("\n\n" + note) if note else ""
    if reason:
        return State("error", "dialog-error-symbolic", "This system cannot install .deb files", reason, False)
    if info.arch not in ("all", arch):
        return State("error", "dialog-error-symbolic", f"This package is for {info.arch}",
                     f"This computer is {arch}, so {info.name} cannot run here. Get the {arch} version of the package.", False)
    if action == "reinstall":
        return State("done", "object-select-symbolic", "Already installed",
                     f"Version {installed} of {info.name} is already on this computer. Reinstall only if something is broken." + extra,
                     True, "Reinstall anyway", True)
    if action == "upgrade":
        return State("update", "go-up-symbolic", "Update available",
                     f"Installed: {installed}. This package has {info.version}." + extra, True, "Continue")
    if action == "downgrade":
        return State("warning", "dialog-warning-symbolic", "Older version",
                     f"Installed: {installed}. This package has {info.version}, which is older: installing it replaces the newer one." + extra)
    return State("ok", "list-add-symbolic", "Ready to install", f"{info.name} is not installed on this computer." + extra)


FAILURES = [
    (("could not get lock", "unable to lock", "database is locked", "waiting for cache lock"),
     "Another installer is running", "Close the other package manager (Software, apt or pacman) and try again."),
    (("exists in filesystem", "conflicting files", "file conflicts", "trying to overwrite"),
     "Files conflict with another package", "A file from this package already belongs to another package or exists on disk. The log shows which one."),
    (("unmet dependencies", "unable to locate package", "but it is not installable", "could not satisfy", "target not found"),
     "Missing dependencies", "A library this package needs is not available. The log lists what is missing."),
    (("no space left",), "Not enough disk space", "Free some space and try again."),
    (("failed retrieving", "could not resolve", "temporary failure resolving", "failed to retrieve"),
     "Network problem", "A dependency could not be downloaded. Check your connection and try again."),
    (("not a debian format archive", "invalid or corrupted package", "corrupted package"),
     "The package is damaged", "The file is not a valid .deb. Download it again."),
]


def failure(code, log):
    """(title, text) for an install that ended with `code`; `log` is the output so far."""
    if code in (126, 127):
        return "Installation cancelled", "The password was not entered or was refused. Nothing was installed."
    low = log.lower()
    for needles, title, text in FAILURES:
        if any(n in low for n in needles): return title, text
    return "Installation failed", f"The installer stopped with code {code}. The log shows why."


def read_error(msg):
    """(title, text) for a file that could not be read; `msg` is the error text."""
    low = msg.lower()
    if "no ar header" in low or "not a .deb" in low:
        return "This is not a .deb file", "The file does not look like a Debian package. Check that the download finished."
    if "errno 2" in low or "no such file" in low:
        return "File not found", "The file was moved or deleted."
    if "errno 13" in low or "permission denied" in low:
        return "No permission to read the file", "Check the file's permissions."
    if "zstd" in low:
        return "Cannot unpack this package", "It uses zstd compression and no zstd decoder is installed. Install zstd and try again."
    return "The package looks damaged", f"It may be incomplete or corrupted. Detail: {msg}"
