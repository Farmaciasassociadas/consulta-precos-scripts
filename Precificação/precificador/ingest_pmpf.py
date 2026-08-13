"""Carrega o PMPF de medicamentos do Paraná (SEFAZ-PR) para a tabela `pmpf_pr`.

Fonte oficial, semestral e gratuita, por EAN:
    https://www.fazenda.pr.gov.br/Pagina/Pauta-de-Medicamentos

O arquivo vigente em 12/08/2026 é a NPF 07/2026 (`pmpf_pr_20260313.csv`,
11.023 medicamentos, vigência 01/04/2026 a 30/09/2026). Colunas:
    GTIN, Produto, Apresentacao, Multiplo, PMPF

`Multiplo` é indispensável: itens de caixa fechada ("AAS 100mg - 20 x 10
comprimidos", múltiplo 20) trazem o PMPF da CAIXA. Dividir por ele devolve a
apresentação que vai ao balcão -- sem isso os 382 itens de múltiplo > 1
entrariam 10 a 50 vezes acima da escala. Ver engine/mercado.normalizar_pmpf.

Uso:
    python ingest_pmpf.py [caminho/pmpf_pr.csv]

Rodar a cada semestre, quando a NPF nova sair (em torno de 01/04 e 01/10).
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

import db

PADRAO = Path(r"C:\Users\docze\ConsultaPrecosEAN\precificacao\dados\pmpf_pr.csv")
# O arquivo da SEFAZ vem em latin-1; utf-8 quebra nos acentos das descrições.
ENCODING = "latin-1"


def carregar(conn: sqlite3.Connection, caminho: Path) -> int:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pmpf_pr (
            ean TEXT PRIMARY KEY,
            descricao TEXT,
            apresentacao TEXT,
            multiplo REAL NOT NULL DEFAULT 1,
            pmpf REAL NOT NULL
        )""")
    linhas = []
    with open(caminho, encoding=ENCODING, newline="") as f:
        for row in csv.DictReader(f):
            ean = (row.get("GTIN") or "").strip()
            try:
                valor = float(row.get("PMPF") or 0)
                multiplo = float(row.get("Multiplo") or 1) or 1.0
            except ValueError:
                continue
            if not ean or valor <= 0:
                continue
            linhas.append((ean, (row.get("Produto") or "").strip(),
                           (row.get("Apresentacao") or "").strip(), multiplo, valor))
    conn.execute("DELETE FROM pmpf_pr")
    conn.executemany(
        "INSERT OR REPLACE INTO pmpf_pr (ean, descricao, apresentacao, multiplo, pmpf) "
        "VALUES (?, ?, ?, ?, ?)", linhas)
    conn.execute(
        "INSERT INTO carga_log (fonte, arquivo, linhas_carregadas) VALUES (?, ?, ?)",
        ("pmpf_pr", caminho.name, len(linhas)))
    conn.commit()
    return len(linhas)


def main() -> None:
    caminho = Path(sys.argv[1]) if len(sys.argv) > 1 else PADRAO
    if not caminho.exists():
        raise SystemExit(f"arquivo nao encontrado: {caminho}")
    conn = db.connect()
    n = carregar(conn, caminho)
    coberto = conn.execute(
        "SELECT COUNT(*) FROM produto p JOIN pmpf_pr m ON m.ean = p.ean").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM produto").fetchone()[0]
    print(f"{n} EANs de PMPF carregados de {caminho.name}.")
    print(f"cobertura do catalogo: {coberto}/{total} ({coberto / total:.1%})")
    conn.close()


if __name__ == "__main__":
    main()
