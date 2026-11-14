# Desenvolvimento

## Rodar do código

```
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1     # Arch: pacman -S python-gobject gtk4 libadwaita
./deb-installer [arquivo.deb]
```

## Testes

```
python3 tests/test_debinfo.py     # monta um .deb em memória e lê
python3 tests/test_archconv.py    # regras de versão e caminho da conversão para pacman
```

## Gerar o .deb do app

```
python3 tools/build_deb.py        # cria dist/deb-installer_<versão>_all.deb
```

A versão vem de `debinstaller/__init__.py`.

## Os prints

Os prints de `docs/media/` são capturas da própria janela (o GTK grava o widget em PNG), usando o `.deb` do app como
exemplo. Para refazê-los, abra o app com um `.deb` e use a captura de tela do seu sistema, ou renderize o widget com
`Gtk.WidgetPaintable` + `Gsk.Renderer.render_texture`.

## Publicar uma versão

1. Suba a versão em `debinstaller/__init__.py`.
2. `git tag vX.Y.Z && git push --tags`: o workflow `Release` gera o `.deb` e anexa à release.
