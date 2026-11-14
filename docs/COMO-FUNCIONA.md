# Como funciona

## Visão geral

```
 .deb ──► debinfo.py ──► janela (app.py) ──► backend.py ──┬─► apt-get install   (Debian, Ubuntu, Mint)
          lê o pacote     assistente de 5      escolhe o    └─► archconv.py ► pacman -U   (Arch, CachyOS, Manjaro)
          sem dpkg        etapas               sistema
```

| Arquivo | O que faz | O que não faz |
|---|---|---|
| `debinstaller/debinfo.py` | Lê o `.deb` em Python puro: campos do `control`, lista de arquivos e ícone. Entende `.gz`, `.xz`, `.bz2` e `.zst`. | Não instala nada e não verifica assinatura (um `.deb` solto não tem). |
| `debinstaller/archconv.py` | Converte o `.deb` num pacote do pacman (`.pkg.tar.zst`), mantendo arquivos e permissões. | Não converte dependências (os nomes mudam entre distros) e não roda `postinst`/`prerm`. |
| `debinstaller/backend.py` | Detecta o sistema, compara versões e roda a instalação por `pkexec`. | Nunca vê a senha: o polkit pede. |
| `debinstaller/states.py` | Os textos e ícones de cada situação (já instalado, atualização, versão antiga, arquitetura errada, falhas, arquivo inválido). Sem GTK, então tem teste. | Não desenha nada nem instala. |
| `debinstaller/app.py` | A janela: barra lateral de etapas, páginas e botões. | Não lê `.deb` nem roda apt/pacman. |
| `tools/build_deb.py` | Monta o `.deb` do próprio app em Python puro, sem `dpkg`. | Não assina o pacote. |

## As etapas

1. **Select**: escolha ou arraste um `.deb`. A leitura roda numa thread, com um spinner e um ✓ ao terminar
   (pacotes grandes levam alguns segundos).
2. **Overview**: ícone, nome, versão, resumo e se é instalação nova, atualização, reinstalação ou downgrade.
3. **Details**: versão, arquitetura, tamanho, mantenedor, dependências e a lista de arquivos.
4. **Install**: progresso e o log ao vivo. Se a senha for cancelada ou falhar, dá para tentar de novo.
5. **Done**: confirmação.

## O ícone

O leitor procura o `Icon=` do arquivo `.desktop` do pacote (ou um ícone com o nome do pacote) em
`/usr/share/icons` e `/usr/share/pixmaps`, prefere SVG e, se não houver, o maior PNG até 512 px.

## Instalar em Arch (a conversão)

Arch não tem `apt` nem `dpkg`. O app lê o `data.tar` do `.deb`, escreve um `.PKGINFO` (nome, versão, arquitetura,
tamanho), troca `lib/`, `bin/` e `sbin/` por `usr/lib/`, `usr/bin/`, `usr/sbin/` (no Arch são links para `/usr`) e
comprime com `zstd`. Depois roda `pkexec pacman -U` nesse pacote. Resultado: o programa fica registrado no pacman e sai
com `sudo pacman -R <nome>`.

Limites: as dependências do Debian não são verificadas (se o programa não abrir, falta alguma biblioteca: instale com
`pacman -S`) e os scripts de instalação do `.deb` não rodam (o log lista os que foram ignorados).

## Segurança

- A elevação de privilégio é só `pkexec` (polkit) sobre `apt-get install` ou `pacman -U`; o app roda como seu usuário.
- Instalar um `.deb` executa o que o pacote trouxer: instale só de quem você confia.

## O ícone dos arquivos `.deb`

Todo `.deb` no gerenciador de arquivos mostra o ícone do app com um selo `.deb` no canto. Não basta pôr o ícone no tema
`hicolor` com o nome do tipo (`application-vnd.debian.binary-package`): o GTK procura **tema por tema**, e um tema como o
Adwaita já tem o ícone genérico `package-x-generic`, que ganha antes de o GTK olhar o `hicolor`. Por isso o app instala
`data/mime/io.github.debinstaller.xml`, que dá ao tipo `.deb` um nome de ícone que nenhum tema define
(`io.github.debinstaller.deb-file`), e o ícone com esse nome no `hicolor`. O gerenciador de arquivos pode precisar ser
reiniciado (`nautilus -q`) para ler o tipo novo.

### O ícone do pacote no selo

Quando você abre um `.deb` no app, `debinstaller/fileicon.py` monta uma imagem (o ícone do Deb Installer com o ícone do
pacote pequeno no canto) e a grava em `~/.local/share/deb-installer/file-icons/`. Depois define o atributo
`metadata::custom-icon` daquele arquivo (o GIO guarda isso junto das suas configurações; o `.deb` não é tocado) e o
Nautilus passa a mostrar essa imagem. Não usei um *thumbnailer* porque os gerenciadores de arquivos não geram miniatura de
arquivos grandes (o Nautilus pula tudo acima de 50 MB) e pacotes grandes são comuns. Para desligar:
`DEB_INSTALLER_NO_FILE_ICON=1`. Sem o `python3-cairo` o recurso fica desligado e o `.deb` mantém o ícone padrão.

## As situações

`states.py` decide o que mostrar:

| Situação | Onde aparece | Botão principal |
|---|---|---|
| Não instalado | card da etapa Overview | Continue |
| **Já instalado** (mesma versão) | card verde | *Reinstall anyway* e *Close* |
| Atualização | card azul | Continue |
| Versão mais antiga | card amarelo | Continue |
| Arquitetura errada | card vermelho | bloqueado |
| Sem apt nem pacman | card vermelho | bloqueado |
| Arquivo inválido ou danificado | página de erro | *Choose another file…* |
| Senha cancelada, dependências, conflito, lock, disco cheio, rede, pacote corrompido | etapa Install, com o log | *Try again*, *Back*, *Copy log* |
| Sucesso | etapa Done | *Install another*, *Close* |

As falhas são reconhecidas pelo código de saída (126 e 127 são senha cancelada ou recusada pelo polkit) e por trechos
do log do apt e do pacman. O que não é reconhecido cai em "Installation failed" com o código e o log completo.
