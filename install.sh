#!/bin/sh
# Installs Deb Installer for the current user (no root): the app in ~/.local/share/deb-installer, a launcher in
# ~/.local/bin, the menu entry and the icon. Remove it with ./install.sh --uninstall. Does not touch system files.
set -e
P="${PREFIX:-$HOME/.local}"
APP="$P/share/deb-installer"
if [ "$1" = "--uninstall" ]; then
  rm -rf "$APP" "$P/bin/deb-installer" "$P/share/applications/io.github.debinstaller.desktop" \
         "$P/share/icons/hicolor/scalable/apps/io.github.debinstaller.svg" \
         "$P/share/icons/hicolor/scalable/mimetypes/application-vnd.debian.binary-package.svg" \
         "$P/share/icons/hicolor/scalable/mimetypes/application-x-deb.svg"
  command -v update-desktop-database >/dev/null && update-desktop-database "$P/share/applications" 2>/dev/null || true
  echo "Deb Installer removed."; exit 0
fi
here="$(dirname "$(readlink -f "$0")")"
rm -rf "$APP"; mkdir -p "$APP" "$P/bin" "$P/share/applications" "$P/share/icons/hicolor/scalable/apps" "$P/share/icons/hicolor/scalable/mimetypes"
cp -r "$here/debinstaller" "$APP/"; find "$APP" -name __pycache__ -prune -exec rm -rf {} +
cat > "$P/bin/deb-installer" <<LAUNCH
#!/bin/sh
cd "$APP" && exec python3 -m debinstaller "\$@"
LAUNCH
chmod +x "$P/bin/deb-installer"
cp "$here/data/icons/hicolor/scalable/apps/io.github.debinstaller.svg" "$P/share/icons/hicolor/scalable/apps/"
# .deb files get the app icon with a small .deb badge (the file manager picks it up from the icon theme)
cp "$here"/data/icons/hicolor/scalable/mimetypes/*.svg "$P/share/icons/hicolor/scalable/mimetypes/"
sed "s|^Exec=.*|Exec=$P/bin/deb-installer %f|" "$here/data/debinstaller.desktop" > "$P/share/applications/io.github.debinstaller.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$P/share/applications" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$P/share/icons/hicolor" 2>/dev/null || true
echo "Installed. Run: deb-installer   (or find 'Deb Installer' in your app menu)"
