"""Classifica por nome/marca os itens LIBERADO que sobraram sem categoria
(nem marca propria, nem cobertos por Pedro 2.xlsx). Regras por palavra-chave
sobre a descricao, baseadas em reconhecimento de marca (Nestle, Garoto,
Coca-Cola, Halls, Bepantol, Hipoglos, Salonpas, G-Tech etc. sao marcas
nacionais bem conhecidas -- nao pesquisado online por serem inequivocas).

Resultado gravado em subcategoria_classificada com fonte propria, para nao
se confundir com a planilha fornecida pelo usuario.
"""
from __future__ import annotations

import re
import sqlite3

import db

REGRAS: list[tuple[str, str]] = [
    (
        r"COCA[- ]?COLA|COCA ZERO|SPRITE|FANTA|SCHW\b|SCHWEPPES|DEL VALLE|POWER ?ADE|"
        r"MONSTER ENERGY|GAROTO|GEROTO|CHOCOLATE|CHOCOSTICK|CHOKITO|BATON|BOMBONS?|"
        r"PRESTIGIO|GALAK|CRUNCH|KIT ?KAT|TALENTO|SUFLER|LOLLO|ALPINO|CLASSIC CHOCOLATE|"
        r"CHARGE|HALLS|TRID\b|TRID\.|TRIDENT",
        "VAREJO > BEBIDAS E BOMBONIERE",
    ),
    (
        r"APTAMIL|APTANUTRI|\bNAN\b|NAN\d|NESLAC|NESTOGENO|NESTONUTRI|NINHO|FORTINI|NUTREN",
        "VAREJO > LEITES NUTRICAO",
    ),
    (
        r"MILMUNE|VITAMINA|LACDAY|COMPLEXO B|EXIMIA PROBIAC|CLORETO DE MAGNESIO",
        "VAREJO > VITAMINAS",
    ),
    (
        r"G\.?TECH|DELLAMED|BIOLAND|TERMOMETRO|NEBULIZADOR|OXIMETRO|^APARELHO|ESPACADOR",
        "VAREJO > ORTOPEDICOS",
    ),
]
CATEGORIA_PADRAO = "ETICOS > O.T.C/MIP"  # OTC farmaceutico de marca, sem palavra-chave de outra categoria
FONTE = "classificacao_por_nome_claude"


def classificar(descricao: str) -> str:
    texto = (descricao or "").upper()
    for padrao, categoria in REGRAS:
        if re.search(padrao, texto):
            return categoria
    return CATEGORIA_PADRAO


def buscar_liberado_sem_categoria(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    sql = """
    SELECT p.ean, p.descricao
    FROM produto p
    WHERE p.grupo_pai_nf = 'LIBERADO'
      AND p.marca_propria = 0
      AND p.ean NOT IN (SELECT ean FROM subcategoria_classificada)
    """
    return conn.execute(sql).fetchall()


def main() -> None:
    conn = db.connect()
    db.criar_schema(conn)
    itens = buscar_liberado_sem_categoria(conn)

    linhas = [(ean, classificar(descricao), FONTE) for ean, descricao in itens]
    conn.executemany(
        "INSERT OR REPLACE INTO subcategoria_classificada (ean, classificacao_exata, fonte) VALUES (?, ?, ?)",
        linhas,
    )
    conn.commit()

    contagem: dict[str, int] = {}
    for _, categoria, _ in linhas:
        contagem[categoria] = contagem.get(categoria, 0) + 1
    print(f"Classificados: {len(linhas)}")
    for categoria, n in sorted(contagem.items(), key=lambda x: -x[1]):
        print(f"  {categoria:35s} {n:4d}")
    conn.close()


if __name__ == "__main__":
    main()
