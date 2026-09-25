"""Caminhos externos configuraveis do precificador batch."""
from __future__ import annotations

import os
from pathlib import Path


def caminho(nome: str, padrao: Path | str) -> Path:
    return Path(os.environ.get(nome, str(padrao))).expanduser()


CONSULTA_PRECOS = caminho("CONSULTA_PRECOS_DIR", Path.home() / "ConsultaPrecosEAN")
ESTOQUE_XLSX = caminho(
    "PRECIFICACAO_ESTOQUE_XLSX",
    r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA\estoque.xlsx",
)
# Planilhas de entrada do ingest.py (Brick, estoque, PMC, subcategoria). Moram
# no Drive, nao no git: C:\Claude empurra para repo PUBLICO, e o Drive ja'
# sincroniza entre os PCs -- e' o que deixa o outro PC reconstruir o .db.
INSUMOS = caminho(
    "PRECIFICACAO_INSUMOS_DIR",
    r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA\Claude\Insumos-Precificacao",
)
SUBCATEGORIA_XLSX = caminho("PRECIFICACAO_SUBCATEGORIA_XLSX", INSUMOS / "Pedro 2.xlsx")
MARCA_EXCLUSIVA_XLSX = caminho(
    "PRECIFICACAO_MARCA_EXCLUSIVA_XLSX",
    Path(r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA")
    / "PRECIFICA\u00c7\u00c3O" / "Marca Exclusiva Associados TRATADO.xlsx",
)
