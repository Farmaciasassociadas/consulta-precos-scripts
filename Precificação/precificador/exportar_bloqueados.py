"""Exporta so os itens que estao BLOQUEADOS de verdade: os que precisam de uma
decisao humana item a item porque o motor nao tem como decidir sozinho.

Nao entram aqui as filas de conferencia (DIVERGENCIA_BRICK_WEB,
PISO_ACIMA_DO_MERCADO), que ja saem com preco sugerido, nem as lacunas de
cadastro (SEM_CUSTO_E_SEM_MERCADO, marca propria/exclusiva), que se resolvem
em lote na entrada de NF/coleta e nao no olho.

Filtra por estoque > 0: item que nao esta na loja nao e decisao de hoje.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook

import db
from exportar_excel import CABECALHO, _formatar, _linha

STATUS_BLOQUEADOS = (
    "CUSTO_ACIMA_DO_MERCADO",
    "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM",
    "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE",
    "REVISAO_MANUAL_PISO_ACIMA_DO_TETO",
)

# O que fazer com cada um -- a coluna que faltava para a planilha virar tarefa.
ACAO = {
    "CUSTO_ACIMA_DO_MERCADO": (
        "Custo de NF acima do que o mercado cobra. Conferir se a NF esta em "
        "embalagem diferente da venda (usar fator_venda em embalagens_produtos.csv) "
        "ou se foi compra ruim -- neste caso, decidir entre vender no prejuizo "
        "para girar ou devolver/encalhar."
    ),
    "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM": (
        "Custo ou embalagem inconsistente. Conferir a NF: quantidade unitaria x "
        "quantidade de venda. Corrigir em embalagens_produtos.csv, nunca digitar "
        "custo na mao."
    ),
    "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE": (
        "Os concorrentes discordam demais entre si para formar referencia. "
        "Conferir se os precos coletados sao do mesmo produto/apresentacao."
    ),
    "REVISAO_MANUAL_PISO_ACIMA_DO_TETO": (
        "O piso pelo custo passa do teto CMED: nao da para vender no minimo de "
        "margem sem estourar o preco maximo legal. Revisar o custo antes."
    ),
}

COLUNAS_EXTRA = ["Estoque", "Valor em estoque (venda)", "O que fazer"]


def exportar(conn: sqlite3.Connection, rodada_id: int) -> Path:
    conn.row_factory = sqlite3.Row
    marcadores = ",".join("?" * len(STATUS_BLOQUEADOS))
    linhas = conn.execute(
        f"""
        SELECT r.*, e.estoque_atual, e.valor_total_venda
        FROM recomendacao r
        LEFT JOIN estoque e ON e.ean = r.ean
        WHERE r.rodada_id = ?
          AND r.status IN ({marcadores})
          AND COALESCE(e.estoque_atual, 0) > 0
        ORDER BY COALESCE(e.valor_total_venda, 0) DESC
        """,
        (rodada_id, *STATUS_BLOQUEADOS),
    ).fetchall()

    wb = Workbook()
    aba = wb.active
    aba.title = "Decisao Humana"
    aba.append(CABECALHO + COLUNAS_EXTRA)
    for r in linhas:
        aba.append(
            _linha(r)
            + [r["estoque_atual"], r["valor_total_venda"], ACAO.get(r["status"], "")]
        )
    _formatar(aba)

    saida = Path(__file__).parent.parent / f"decisao_humana_rodada_{rodada_id}.xlsx"
    wb.save(saida)
    return saida


def main() -> None:
    conn = db.connect()
    rodada_id = conn.execute("SELECT MAX(id) FROM rodada").fetchone()[0]
    caminho = exportar(conn, rodada_id)
    total = conn.execute(
        f"""SELECT COUNT(*) FROM recomendacao r LEFT JOIN estoque e ON e.ean = r.ean
            WHERE r.rodada_id = ? AND r.status IN ({",".join("?" * len(STATUS_BLOQUEADOS))})
              AND COALESCE(e.estoque_atual, 0) > 0""",
        (rodada_id, *STATUS_BLOQUEADOS),
    ).fetchone()[0]
    print(f"rodada {rodada_id}: {total} itens bloqueados com estoque -> {caminho}")


if __name__ == "__main__":
    main()
