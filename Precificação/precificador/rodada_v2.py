"""Fase 4 v2: rodada de precificacao com regras incorporadas.

Melhorias:
- Detecta e corrige outliers de preco (embalagem confundida)
- Habilita controlados/fracionados com tier PROTECAO_MARGEM (nao bloqueia)
"""
from __future__ import annotations

import sqlite3
from datetime import date
from statistics import median

import db
from engine import economico, mercado, parametros

DEPARA_PROVISORIO = {
    "GENÉRICO": "GENERICO",
    "GENERICO": "GENERICO",
    "SIMILAR": "SIMILAR",
    "REFERÊNCIA": "ETICOS",
    "REFERENCIA": "ETICOS",
    "PERFUMARIA": "PERFUMARIA",
}


def _categoria_provisoria(grupo_pai_nf: str | None) -> str | None:
    return DEPARA_PROVISORIO.get((grupo_pai_nf or "").strip())


def buscar_produtos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    sql = """
    SELECT
        p.ean, p.descricao, p.grupo_pai_nf, p.marca_propria, p.marca_exclusiva_preco,
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


def preco_anterior_estoque(conn: sqlite3.Connection, ean: str) -> float | None:
    r = conn.execute("SELECT preco_venda_atual FROM estoque WHERE ean = ?", (ean,)).fetchone()
    return r[0] if r and r[0] else None


def mediana_sugerido_historico(conn: sqlite3.Connection, ean: str, rodada_atual_id: int) -> float | None:
    valores = [
        r[0] for r in conn.execute(
            "SELECT preco_sugerido FROM recomendacao WHERE ean = ? AND rodada_id != ? "
            "AND preco_sugerido IS NOT NULL",
            (ean, rodada_atual_id),
        )
    ]
    return median(valores) if valores else None


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
    try:
        chamariz_eans = {r[0] for r in conn.execute("SELECT ean FROM chamariz_vigente")}
    except sqlite3.OperationalError:
        chamariz_eans = set()  # schema antigo (rodar db.criar_schema para criar a tabela)
    linhas = []
    for row in produtos:
        ean = row["ean"]
        descricao = row["descricao"]
        e_chamariz = ean in chamariz_eans

        if row["marca_exclusiva_preco"] is not None:
            linhas.append((
                rodada_id, ean, descricao, None, None, None, "MARCA_EXCLUSIVA_MANUAL",
                row["custo_medio"], row["n_compras"], None,
                None, None, None, row["vum_brick"],
                None, None, row["pmc"], row["preco_venda_atual"],
                row["marca_exclusiva_preco"],
                "Marca Exclusiva Associados: preco de venda fixado manualmente pelo usuario "
                "(planilha Marca Exclusiva Associados TRATADO.xlsx, coluna Preco Venda), "
                "fora da precificacao automatica -- alimentado manualmente pelo usuario.",
            ))
            continue

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

        # NOVIDADE: corrigir outlier de preco_venda_atual
        preco_anterior = preco_anterior_estoque(conn, ean)
        preco_atual_corrigido, nota_outlier = economico.corrigir_preco_atual(
            venda_unit=row["preco_venda_atual"],
            preco_anterior=preco_anterior,
            custo_final=row["custo_medio"],
            pmc_val=row["pmc"],
            vum_brick=row["vum_brick"],
        )
        preco_atual_final = preco_atual_corrigido

        # Categoria/natureza fiscal calculadas ANTES do mercado: o motor de
        # mercado precisa da natureza para aplicar o premio de balcao correto
        # quando nao ha segmento Brick (ver engine/mercado._fator_fisico).
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

        obs = observacoes_do_ean(conn, ean)
        resultado_mercado = mercado.calcular_mercado(
            obs, params, data_referencia, vum_brick=row["vum_brick"], segmento_brick=row["segmento"],
            natureza_fiscal_item=natureza,
        )

        tier = economico.determinar_tier(
            papel_politica=politica[0] if politica else None,
            curva_abc=row["curva_abc"],
            n_concorrentes=resultado_mercado.n,
            cv=resultado_mercado.cv,
            tem_brick=row["vum_brick"] is not None,
        )

        # NOVIDADE: habilitar controlados/fracionados com PROTECAO_MARGEM
        if tier == "REVISAO_HUMANA":
            tier = "PROTECAO_MARGEM"

        # Um preco por site (o mais recente sobrevivente ao filtro de outliers),
        # para o motor de ranking decidir a posicao competitiva (2o/3o lugar)
        # em vez de sempre perseguir o menor preco.
        precos_por_site: dict[str, float] = {}
        for o in resultado_mercado.filtro.mantidas:
            if o.preco is not None:
                precos_por_site[o.site] = o.preco
        precos_concorrentes = list(precos_por_site.values())

        resultado = economico.aplicar_travas(
            custo=row["custo_medio"],
            natureza_fiscal_item=natureza,
            tier=tier,
            valor_referencia_mercado=resultado_mercado.valor_referencia,
            divergencia_brick_web=resultado_mercado.divergencia_brick_web,
            lucro_liquido_alvo_pct=politica[1] if politica else None,
            teto_cmed=row["pmc"],
            preco_atual=preco_atual_final,
            params=params,
            precos_concorrentes=precos_concorrentes,
            curva_abc=row["curva_abc"],
            e_chamariz=e_chamariz,
        )

        justificativa_final = resultado.justificativa
        if nota_outlier:
            justificativa_final = f"[OUTLIER CORRIGIDO] {nota_outlier} {resultado.justificativa}"

        mediana_historico = mediana_sugerido_historico(conn, ean, rodada_id)
        if economico.preco_atual_e_outlier_historico(preco_atual_final, mediana_historico):
            justificativa_final = (
                f"[PRECO CADASTRO SUSPEITO] preco_atual (R$ {preco_atual_final:.2f}) destoa da "
                f"mediana historica de sugestoes (R$ {mediana_historico:.2f}); cadastro provavelmente "
                f"desatualizado, ignorado como referencia. {justificativa_final}"
            )

        linhas.append((
            rodada_id, ean, row["descricao"], categoria, natureza, tier, resultado.status,
            row["custo_medio"], row["n_compras"], resultado_mercado.valor_referencia,
            resultado_mercado.n, resultado_mercado.cv, resultado_mercado.peso_brick, row["vum_brick"],
            resultado.piso, resultado.alvo, row["pmc"], preco_atual_final,
            resultado.preco_sugerido, justificativa_final,
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
    rodada_id = processar_rodada(conn, "rodada_v2_com_outlier_fix_e_controlados_habilitados")
    resumo_rodada(conn, rodada_id)
    comparar_com_anterior(conn, rodada_id)
    conn.close()


if __name__ == "__main__":
    main()
