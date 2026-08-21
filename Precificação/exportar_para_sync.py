"""Exporta do .db o que NAO da para reconstruir, para um CSV que sincroniza.

Por que existe: o precificador.db tem 53 MB e e' quase todo derivado --
ingest.py reconstroi preco_brick, pmc_cmed_pr, recomendacao e companhia a
partir das fontes. Sincronizar o binario entre os 3 PCs pelo git nao funciona
(o git nao reconcilia binario: um PC sobrescreve o outro) e ainda joga custo e
margem para dentro do repositorio.

O que realmente precisa viajar e' pequeno: a classificacao feita a mao e o
cadastro de produto vindo das notas. Vai para o repo PRIVADO do app, que os 3
PCs ja sincronizam.

Uso: python exportar_para_sync.py [--destino <pasta>]
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "precificador"))
from caminhos import CONSULTA_PRECOS  # noqa: E402

DB = Path(__file__).parent / "precificador" / "precificador.db"
DESTINO_PADRAO = CONSULTA_PRECOS / "precificacao" / "dados"

TABELAS = {
    "sync_subcategoria_classificada.csv":
        "SELECT ean, classificacao_exata, fonte FROM subcategoria_classificada ORDER BY ean",
    "sync_produto.csv":
        "SELECT ean, descricao, grupo_pai_nf, grupo_filho_nf FROM produto ORDER BY ean",
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destino", type=Path, default=DESTINO_PADRAO)
    args = ap.parse_args()
    args.destino.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(DB)
    for nome, sql in TABELAS.items():
        cursor = conn.execute(sql)
        colunas = [d[0] for d in cursor.description]
        linhas = cursor.fetchall()
        caminho = args.destino / nome
        with caminho.open("w", encoding="utf-8", newline="") as fh:
            escritor = csv.writer(fh)
            escritor.writerow(colunas)
            escritor.writerows(linhas)
        print(f"{caminho}  {len(linhas)} linhas  {caminho.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
