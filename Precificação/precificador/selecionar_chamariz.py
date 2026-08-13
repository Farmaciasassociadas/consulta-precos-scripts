"""Recalcula a lista de itens chamariz/KVI e grava em `chamariz_vigente`.

100% automatico e reproduzivel (sem curadoria manual): cruza o ranking de mais
vendidos do Brick com a MARGEM que sobra depois do desconto, a comparabilidade
(numero de concorrentes) e a dispersao (CV) da ultima rodada. Ver
engine/chamariz.py para o racional de cada criterio.

Desde 12/08/2026 a selecao e' Top N GLOBAL (7 itens), nao mais top 8 por
segmento (32 itens): imagem de preco se forma sobre poucos itens que o cliente
sabe de cor, e cota por segmento obrigava a rebaixar itens que ninguem procura
so para preencher a cota.

Rodar depois de cada rodada de precificacao (rodada_v2.py), ou sozinho a
cada `chamariz.revisar_a_cada_dias` (config/parametros.toml).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import db
from engine import parametros
from engine.chamariz import CandidatoChamariz, selecionar_chamariz


def _montar_candidatos(conn: sqlite3.Connection, desconto_pct: float = 0.0) -> list[CandidatoChamariz]:
    conn.row_factory = sqlite3.Row
    ultima_rodada = conn.execute("SELECT MAX(id) FROM rodada").fetchone()[0]

    # `custo` e `mercado_referencia` da ultima rodada dao a margem que SOBRA
    # depois do desconto de chamariz -- o criterio "lucrativo" pedido em
    # 12/08/2026. Sem custo, a margem fica None e o score usa o neutro 0,5.
    sql = """
    SELECT
        b.ean, b.segmento, b.posicao_mais_vendidos,
        r.n_concorrentes, r.cv, r.custo, r.mercado_referencia
    FROM preco_brick b
    LEFT JOIN recomendacao r ON r.ean = b.ean AND r.rodada_id = ?
    WHERE b.posicao_mais_vendidos IS NOT NULL AND b.segmento IS NOT NULL
    """
    candidatos = []
    for row in conn.execute(sql, (ultima_rodada,)).fetchall():
        try:
            posicao = int(str(row["posicao_mais_vendidos"]).rstrip("ºo").strip())
        except ValueError:
            continue
        margem = None
        custo, mercado = row["custo"], row["mercado_referencia"]
        if custo and mercado and mercado > 0:
            preco_chamariz = mercado * (1 - desconto_pct)
            if preco_chamariz > 0:
                margem = (preco_chamariz - custo) / preco_chamariz
        candidatos.append(CandidatoChamariz(
            ean=row["ean"],
            segmento=row["segmento"],
            posicao_mais_vendidos=posicao,
            n_concorrentes=row["n_concorrentes"] or 0,
            cv=row["cv"],
            margem_pos_desconto=margem,
        ))
    return candidatos


def rodar(conn: sqlite3.Connection) -> int:
    params = parametros.carregar()
    cfg = params["chamariz"]
    candidatos = _montar_candidatos(conn, cfg.get("desconto_maximo_pct", 0.0))
    selecionados = selecionar_chamariz(
        candidatos,
        top_n_global=cfg["top_n_global"],
        n_concorrentes_minimo=cfg["n_concorrentes_minimo"],
        pesos={
            "giro": cfg.get("peso_giro", 0.40),
            "margem": cfg.get("peso_margem", 0.30),
            "comparabilidade": cfg.get("peso_comparabilidade", 0.20),
            "dispersao": cfg.get("peso_dispersao", 0.10),
        },
    )

    revisar_ate = (date.today() + timedelta(days=cfg["revisar_a_cada_dias"])).isoformat()
    conn.execute("DELETE FROM chamariz_vigente")
    conn.executemany(
        "INSERT INTO chamariz_vigente (ean, segmento, score, revisar_ate) VALUES (?, ?, ?, ?)",
        [(s.ean, s.segmento, s.score, revisar_ate) for s in selecionados],
    )
    conn.commit()
    return len(selecionados)


if __name__ == "__main__":
    conn = db.connect()
    db.criar_schema(conn)
    n = rodar(conn)
    print(f"{n} itens selecionados como chamariz/KVI (ver tabela chamariz_vigente).")
    conn.close()
