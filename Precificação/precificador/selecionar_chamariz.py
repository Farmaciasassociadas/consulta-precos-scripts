"""Recalcula a lista de itens chamariz/KVI e grava em `chamariz_vigente`.

100% automatico e reproduzivel (sem curadoria manual): usa o ranking de mais
vendidos do Brick por segmento (RX/GEN/SIM/NMED) cruzado com comparabilidade
(numero de concorrentes) e dispersao (CV) da ultima rodada. Ver
engine/chamariz.py para o racional de cada criterio.

Rodar depois de cada rodada de precificacao (rodada_v2.py), ou sozinho a
cada `chamariz.revisar_a_cada_dias` (config/parametros.toml).
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import db
from engine import parametros
from engine.chamariz import CandidatoChamariz, selecionar_chamariz


def _montar_candidatos(conn: sqlite3.Connection) -> list[CandidatoChamariz]:
    conn.row_factory = sqlite3.Row
    ultima_rodada = conn.execute("SELECT MAX(id) FROM rodada").fetchone()[0]

    sql = """
    SELECT
        b.ean, b.segmento, b.posicao_mais_vendidos,
        r.n_concorrentes, r.cv
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
        candidatos.append(CandidatoChamariz(
            ean=row["ean"],
            segmento=row["segmento"],
            posicao_mais_vendidos=posicao,
            n_concorrentes=row["n_concorrentes"] or 0,
            cv=row["cv"],
        ))
    return candidatos


def rodar(conn: sqlite3.Connection) -> int:
    params = parametros.carregar()
    cfg = params["chamariz"]
    candidatos = _montar_candidatos(conn)
    selecionados = selecionar_chamariz(
        candidatos,
        top_n_por_segmento=cfg["top_n_por_segmento"],
        n_concorrentes_minimo=cfg["n_concorrentes_minimo"],
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
