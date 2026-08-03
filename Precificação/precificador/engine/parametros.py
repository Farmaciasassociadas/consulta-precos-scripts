"""Carregamento dos parametros financeiros/fiscais/de mercado (config/parametros.toml).

Mantido separado do resto do motor para que outliers.py, brick.py e mercado.py
permanecam funcoes puras: recebem os parametros como argumento, nunca leem o
arquivo sozinhos.
"""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

PADRAO = Path(__file__).parent.parent / "config" / "parametros.toml"


def carregar(caminho: Path = PADRAO) -> dict[str, Any]:
    with open(caminho, "rb") as f:
        return tomllib.load(f)
