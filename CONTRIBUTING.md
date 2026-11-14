# Contribuindo

Contribuições são bem-vindas: bug, ideia ou pull request.

1. Faça um fork e crie uma branch.
2. Rode os testes: `python3 tests/test_debinfo.py && python3 tests/test_archconv.py`.
3. Se mudou a interface, atualize os prints em `docs/media/` (veja [docs/DESENVOLVIMENTO.md](docs/DESENVOLVIMENTO.md)).
4. Abra o pull request dizendo **o que mudou, por que, e em qual sistema você testou** (Debian, Ubuntu, Arch...).

Regras do projeto: cada arquivo começa com um comentário que diz o que ele faz e o que não faz; nada de dependência
fora do GTK4/libadwaita e da biblioteca padrão do Python; o app nunca lê a senha do usuário (quem pede é o polkit).
