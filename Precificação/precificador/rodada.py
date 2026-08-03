"""Fase 4: orquestra uma rodada de precificacao sobre o banco real.

Junta engine.mercado + engine.economico com os dados carregados na Fase 1 e
grava uma linha de recomendacao por EAN em `recomendacao`, presa a uma
`rodada`. Ao final, compara com a rodada anterior (se existir).

De-para de categoria: PROVISORIO, so no nivel macro (ver DEPARA_PROVISORIO
abaixo) -- o de-para oficial por subgrupo ainda nao existe (pendencia 5.4 do
PLANO_SISTEMA_PRECIFICACAO.md). Enquanto isso, itens ficam limitados a
tier/alvo de nivel macro, e LIBERADO (sem correspondencia segura) vai para
REVISAO_MANUAL_SEM_MARKUP em vez de receber um chute.
"""
from __future__ import annotations

import sqlite3
from datetime import date

import db
from engine import economico, mercado, parametros

DEPARA_PROVISORIO = {
    "GENÉRICO": "GENERICO",
    "GENERICO": "GENERICO",
    "SIMILAR": "SIMILAR",
    "REFERÊNCIA": "ETICOS",
    "REFERENCIA": "ETICOS",
    "PERFUMARIA": "PERFUMARIA",
    # "LIBERADO": sem categoria macro segura na taxonomia nova -- deixado de fora.
}


def _categoria_provisoria(grupo_pai_nf: str | None) -> str | None:
    return DEPARA_PROVISORIO.get((grupo_pai_nf or "").strip())


def buscar_produtos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    sql = """
    SELECT
        p.ean, p.descricao, p.grupo_pai_nf, p.marca_propria,
        c.custo_medio, c.n_compras, c.tem_icms_st,
        b.vum AS vum_brick, b.curva_abc, b.segmento,
        e.preco_venda_atual, e.estoque_atual,
        m.pmc
    FROM produto p
    LEFT JOIN (
        SELECT ean, AVG(custo_unitario) AS custo_medio, COUNT(*) AS n_compras, MAX(tem_icms_st) AS tem_icms_st
        FROM custo_nf GROUP BY ean
    ) c ON c.ean = p.ean
    LEFT JOIN preco_brick b ON b.ean = p.ean
    LEFT JOIN estoque e ON e.ean = p.ean
    LEFT JOIN pmc_cmed_pr m ON m.ean = p.ean
    """
    return conn.execute(sql).fetchall()


def observacoes_do_ean(conn: sqlite3.Connection, ean: str) -> list[mercado.Observacao]:
    linhas = conn.execute(
        "SELECT site, data_hora, status, preco, observacoes FROM preco_concorrente WHERE ean = ?", (ean,)
    ).fetchall()
    return [
        mercado.Observacao(
            site=site, preco=preco, status=status,
            data_hora=mercado.parse_data_hora(data_hora), observacoes=observacoes,
        )
        for site, data_hora, status, preco, observacoes in linhas
    ]


def processar_rodada(conn: sqlite3.Connection, observacao_rodada: str | None = None) -> int:
    params = parametros.carregar()
    data_referencia = date.today()

    cur = conn.execute("INSERT INTO rodada (observacao) VALUES (?)", (observacao_rodada,))
    rodada_id = cur.lastrowid

    produtos = buscar_produtos(conn)
    linhas = []
    for row in produtos:
        ean = row["ean"]
        descricao = row["descricao"]

        if row["marca_propria"]:
            descricao_marcada = f"{descricao} *" if descricao else descricao
            linhas.append((
                rodada_id, ean, descricao_marcada, None, None, None, "MARCA_PROPRIA_MANUAL",
                row["custo_medio"], row["n_compras"], None,
                None, None, None, row["vum_brick"],
                None, None, row["pmc"], row["preco_venda_atual"],
                None, "Marca propria: preco definido manualmente pelo usuario, fora da precificacao automatica.",
            ))
            continue

        obs = observacoes_do_ean(conn, ean)
        resultado_mercado = mercado.calcular_mercado(
            obs, params, data_referencia, vum_brick=row["vum_brick"], segmento_brick=row["segmento"],
        )

        subcategoria = conn.execute(
            "SELECT classificacao_exata FROM subcategoria_classificada WHERE ean = ?", (ean,)
        ).fetchone()
        categoria = subcategoria[0] if subcategoria else _categoria_provisoria(row["grupo_pai_nf"])
        politica = None
        if categoria:
            politica = conn.execute(
                "SELECT papel, lucro_liquido_alvo_pct FROM politica_categoria WHERE classificacao_exata = ?",
                (categoria,),
            ).fetchone()

        tem_icms_st = bool(row["tem_icms_st"])
        natureza = economico.natureza_fiscal(categoria, tem_icms_st)
        tier = economico.determinar_tier(
            papel_politica=politica[0] if politica else None,
            curva_abc=row["curva_abc"],
            n_concorrentes=resultado_mercado.n,
            cv=resultado_mercado.cv,
            tem_brick=row["vum_brick"] is not None,
        )

        resultado = economico.aplicar_travas(
            custo=row["custo_medio"],
            natureza_fiscal_item=natureza,
            tier=tier,
            valor_referencia_mercado=resultado_mercado.valor_referencia,
            divergencia_brick_web=resultado_mercado.divergencia_brick_web,
            lucro_liquido_alvo_pct=politica[1] if politica else None,
            teto_cmed=row["pmc"],
            preco_atual=row["preco_venda_atual"],
            params=params,
        )

        linhas.append((
            rodada_id, ean, row["descricao"], categoria, natureza, tier, resultado.status,
            row["custo_medio"], row["n_compras"], resultado_mercado.valor_referencia,
            resultado_mercado.n, resultado_mercado.cv, resultado_mercado.peso_brick, row["vum_brick"],
            resultado.piso, resultado.alvo, row["pmc"], row["preco_venda_atual"],
            resultado.preco_sugerido, resultado.justificativa,
        ))

    conn.executemany(
        """INSERT INTO recomendacao (
            rodada_id, ean, descricao, categoria_provisoria, natureza_fiscal, tier, status,
            custo, n_compras_nf, mercado_referencia, n_concorrentes, cv, peso_brick, vum_brick,
            piso, alvo, teto_cmed, preco_atual, preco_sugerido, justificativa
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        linhas,
    )
    conn.commit()
    return rodada_id


def resumo_rodada(conn: sqlite3.Connection, rodada_id: int) -> None:
    print(f"\n=== Rodada {rodada_id}: resumo por status ===")
    for status, n in conn.execute(
        "SELECT status, COUNT(*) FROM recomendacao WHERE rodada_id = ? GROUP BY status ORDER BY 2 DESC", (rodada_id,)
    ):
        print(f"  {status:38s} {n:5d}")

    print(f"\n=== Rodada {rodada_id}: resumo por tier (itens OK) ===")
    for tier, n in conn.execute(
        "SELECT tier, COUNT(*) FROM recomendacao WHERE rodada_id = ? AND status = 'OK' GROUP BY tier ORDER BY 2 DESC",
        (rodada_id,),
    ):
        print(f"  {tier:20s} {n:5d}")

    abaixo_piso_hoje = conn.execute(
        "SELECT COUNT(*) FROM recomendacao WHERE rodada_id = ? AND piso IS NOT NULL "
        "AND preco_atual IS NOT NULL AND preco_atual > 0 AND preco_atual < piso",
        (rodada_id,),
    ).fetchone()[0]
    print(f"\nItens com preco praticado HOJE abaixo do piso calculado: {abaixo_piso_hoje}")


def comparar_com_anterior(conn: sqlite3.Connection, rodada_atual: int) -> None:
    anterior = conn.execute(
        "SELECT id FROM rodada WHERE id < ? ORDER BY id DESC LIMIT 1", (rodada_atual,)
    ).fetchone()
    if not anterior:
        print("\n(sem rodada anterior para comparar)")
        return
    rodada_anterior = anterior[0]
    print(f"\n=== Diff: rodada {rodada_anterior} -> rodada {rodada_atual} ===")
    diffs = conn.execute(
        """
        SELECT a.ean, a.status, b.status, a.preco_sugerido, b.preco_sugerido, a.tier, b.tier
        FROM recomendacao a JOIN recomendacao b ON a.ean = b.ean
        WHERE a.rodada_id = ? AND b.rodada_id = ?
        """,
        (rodada_anterior, rodada_atual),
    ).fetchall()
    mudou_status = sum(1 for r in diffs if r[1] != r[2])
    mudou_tier = sum(1 for r in diffs if r[5] != r[6])
    # Conta tanto "preco diferente" quanto "passou a ter/deixou de ter preco",
    # nao so a diferenca numerica entre dois precos ja existentes.
    mudou_preco = sum(
        1 for r in diffs
        if (r[3] is None) != (r[4] is None)
        or (r[3] is not None and r[4] is not None and abs(r[3] - r[4]) > 0.005)
    )
    ganharam_preco = sum(1 for r in diffs if r[3] is None and r[4] is not None)
    perderam_preco = sum(1 for r in diffs if r[3] is not None and r[4] is None)
    print(f"  EANs comparados: {len(diffs)}")
    print(f"  Mudaram de status: {mudou_status}")
    print(f"  Mudaram de tier: {mudou_tier}")
    print(f"  Mudaram de preco sugerido (inclui ganhou/perdeu preco): {mudou_preco}")
    print(f"    dos quais passaram a ter preco: {ganharam_preco}")
    print(f"    dos quais deixaram de ter preco: {perderam_preco}")


def main() -> None:
    conn = db.connect()
    db.criar_schema(conn)
    rodada_id = processar_rodada(conn)
    resumo_rodada(conn, rodada_id)
    comparar_com_anterior(conn, rodada_id)
    conn.close()


if __name__ == "__main__":
    main()
