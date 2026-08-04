#!/bin/bash
# Hook automático: após cada Edit em repo_temp/*.py, auto-commit se houver mudanças
# Desabilitado por padrão — ativar com: export ECC_AUTO_COMMIT=1

# Sair silencioso se o hook não está habilitado
[[ "$ECC_AUTO_COMMIT" != "1" ]] && exit 0

# Sair se não estamos em repo_temp
[[ ! -d "repo_temp/.git" ]] && exit 0
cd repo_temp || exit 0

# Rodar o auto-commit (silencioso)
python auto_commit.py 2>&1 | head -3

exit 0  # Nunca quebrar o fluxo do Claude Code
