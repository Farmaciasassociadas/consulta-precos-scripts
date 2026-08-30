"""Fase 4 v2: rodada de precificacao com regras incorporadas.

Melhorias:
- Detecta e corrige outliers de preco (embalagem confundida)
- Habilita controlados/fracionados com tier PROTECAO_MARGEM (nao bloqueia)
"""
from __future__ import annotations

import sqlite3
from dataclasses import replace
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


def _categoria_provisoria(grupo_pai_nf: str | None,
                          grupo_filho_nf: str | None = None,
                          classificacoes: set[str] | None = None) -> str | None:
    """Categoria da politica a partir dos grupos da NF.

    Tenta primeiro `PAI > FILHO` exatamente como esta em politica_categoria --
    a tabela ja tem 50 classificacoes nesse formato (ETICOS > RX, VAREJO >
    LEITES, SIMILAR > CONTROLADO...). So depois cai no de-para do PAI.

    Ate 12/08/2026 so o PAI era consultado, e por um de-para de 6 entradas que
    nao incluia ETICOS, LIBERADO nem VAREJO. Enquanto o relatorio de NF antigo
    trazia GENERICO/SIMILAR/REFERENCIA isso passava; o relatorio novo usa a
    taxonomia PAI=ETICOS/LIBERADO/VAREJO e 415 itens (299 com estoque) ficaram
    sem regra financeira -- inclusive 23 CONTROLADOS, que a politica manda
    mandar para REVISAO_HUMANA e que sem categoria nem chegavam la.
    """
    pai = (grupo_pai_nf or "").strip()
    filho = (grupo_filho_nf or "").strip()
    if classificacoes and pai and filho:
        exata = f"{pai} > {filho}"
        if exata in classificacoes:
            return exata
    if classificacoes and pai in classificacoes:
        return pai
    return DEPARA_PROVISORIO.get(pai)


def buscar_produtos(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    sql = """
    SELECT
        p.ean, p.descricao, p.grupo_pai_nf, p.grupo_filho_nf, p.marca_propria, p.marca_exclusiva_preco,
        c.custo_medio, c.n_compras, c.tem_icms_st,
        b.vum AS vum_brick, b.curva_abc, b.segmento,
        e.preco_venda_atual, e.estoque_atual,
        m.pmc,
        f.pmpf, f.multiplo AS pmpf_multiplo
    FROM produto p
    LEFT JOIN (
        SELECT ean, AVG(custo_unitario) AS custo_medio, COUNT(*) AS n_compras, MAX(tem_icms_st) AS tem_icms_st
        FROM custo_nf GROUP BY ean
    ) c ON c.ean = p.ean
    LEFT JOIN preco_brick b ON b.ean = p.ean
    LEFT JOIN estoque e ON e.ean = p.ean
    LEFT JOIN pmc_cmed_pr m ON m.ean = p.ean
    LEFT JOIN pmpf_pr f ON f.ean = p.ean
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
        "SELECT site, data_hora, status, preco, observacoes, COALESCE(estoque, '') "
        "FROM preco_concorrente WHERE ean = ?", (ean,)
    ).fetchall()
    return [
        mercado.Observacao(
            site=site, preco=preco, status=status,
            data_hora=mercado.parse_data_hora(data_hora), observacoes=observacoes,
            estoque=estoque,
        )
        for site, data_hora, status, preco, observacoes, estoque in linhas
    ]


def processar_rodada(conn: sqlite3.Connection, observacao_rodada: str | None = None,
                     ajuste_lucro_sem_vizinhanca: float = 0.0) -> int:
    """`ajuste_lucro_sem_vizinhanca` e o acrescimo de lucro-alvo da Fase 3
    (controle de margem do mix), aplicado SO em itens sem vizinhanca local --
    ver economico.ajuste_lucro_alvo_mix e rodar_com_controle_de_mix."""
    params = parametros.carregar()
    data_referencia = date.today()

    cur = conn.execute("INSERT INTO rodada (observacao) VALUES (?)", (observacao_rodada,))
    rodada_id = cur.lastrowid

    produtos = buscar_produtos(conn)
    classificacoes_com_politica = {
        r[0] for r in conn.execute("SELECT classificacao_exata FROM politica_categoria")}
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
        categoria = subcategoria[0] if subcategoria else _categoria_provisoria(
            row["grupo_pai_nf"], row["grupo_filho_nf"], classificacoes_com_politica)

        # Paridade com o motor do app (precificacao/ do ConsultaPrecosEAN): o
        # segmento auditado do Brick corrige o eixo (GENERICO/ETICOS/SIMILAR)
        # antes da politica financeira -- sem isso, generico cadastrado como
        # etico usa lucro-alvo de etico (10%) em vez de generico (15%).
        motivo_eixo = ""
        cfg_classificacao = params.get("classificacao", {})
        if cfg_classificacao.get("corrigir_eixo_por_brick", False) and categoria:
            permitidas = {r[0] for r in conn.execute(
                "SELECT classificacao_exata FROM politica_categoria")}
            permitidas |= {r[0] for r in conn.execute(
                "SELECT DISTINCT classificacao_exata FROM subcategoria_classificada")}
            categoria, motivo_eixo = economico.corrigir_eixo_por_brick(
                categoria, row["segmento"], permitidas)

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
            obs, params, data_referencia,
            # Paridade com o app: sem custo validado por NF nao ha base para
            # ancorar no Brick (auditoria nacional) -- o item sai so com a web.
            vum_brick=row["vum_brick"] if row["custo_medio"] is not None else None,
            segmento_brick=row["segmento"],
            natureza_fiscal_item=natureza,
            # Paridade com o app: sem o custo aqui a guarda `_brick_incoerente`
            # nunca dispara (ela exige as duas testemunhas, custo E web) -- ficou
            # morta nesta copia batch ate 12/08/2026, e por isso o LACTA BOMBOM
            # (custo 1,06, Brick 120,02 de display) saia a R$ 139,99 aqui mas nao
            # no app.
            custo=row["custo_medio"],
            pmpf=row["pmpf"],
            pmpf_multiplo=row["pmpf_multiplo"],
        )

        tier = economico.determinar_tier(
            papel_politica=politica[0] if politica else None,
            curva_abc=row["curva_abc"],
            n_concorrentes=resultado_mercado.n,
            cv=resultado_mercado.cv,
            tem_brick=row["vum_brick"] is not None,
            categoria=categoria,
        )

        # NOVIDADE: habilitar controlados/fracionados com PROTECAO_MARGEM
        if tier == "REVISAO_HUMANA":
            tier = "PROTECAO_MARGEM"

        # Paridade com o app: o ranking e o piso competitivo usam so os precos
        # da VIZINHANCA local quando ela e confiavel (mercado.selecionar_vizinhanca);
        # os sites remotos continuam valendo para n/cv/divergencia. menor/maior
        # local alimentam o piso competitivo e os status honestos.
        # Paridade com o app: a ancora do piso/teto competitivo usa
        # `observacoes_locais` (TODOS os locais que sobreviveram as camadas),
        # nao `observacoes_alvo` -- barra de evidencia mais baixa, porque um
        # unico preco local ja prova que existe loja ao lado vendendo por
        # aquilo. Ver mercado.selecionar_vizinhanca e [mercado.ancora_competitiva].
        precos_concorrentes = list(resultado_mercado.precos_alvo)
        menor_local = maior_local = None
        if resultado_mercado.observacoes_locais:
            menor_local, maior_local, _motivo = mercado.ancora_competitiva_local(
                list(resultado_mercado.observacoes_locais), params)

        # Fase 3: so quem NAO tem vizinhanca local visivel absorve o ajuste de
        # mix -- subir preco onde o cliente compara e' como se perde cliente.
        lucro_alvo = politica[1] if politica else None
        if lucro_alvo is not None and not resultado_mercado.alvo_so_local:
            lucro_alvo += ajuste_lucro_sem_vizinhanca
        # Fase 6: premio de risco de inventario da celula ABC-XYZ. Devolve 0,0
        # enquanto [xyz] estiver desligado (sem historico de venda).
        if lucro_alvo is not None:
            lucro_alvo += economico.premio_risco_xyz(row["curva_abc"], None, params)

        resultado = economico.aplicar_travas(
            custo=row["custo_medio"],
            natureza_fiscal_item=natureza,
            tier=tier,
            valor_referencia_mercado=resultado_mercado.valor_referencia,
            divergencia_brick_web=resultado_mercado.divergencia_brick_web,
            lucro_liquido_alvo_pct=lucro_alvo,
            teto_cmed=row["pmc"],
            preco_atual=preco_atual_final,
            params=params,
            precos_concorrentes=precos_concorrentes,
            curva_abc=row["curva_abc"],
            e_chamariz=e_chamariz,
            menor_concorrente_local=menor_local,
            maior_concorrente_local=maior_local,
            categoria=categoria,
        )
        status_gravado = resultado.status

        # Paridade com o app: sem regra financeira cadastrada (categoria sem
        # politica), tenta com a margem mediana das categorias como estimativa
        # em vez de bloquear o item sem preco.
        if resultado.preco_sugerido is None and resultado.status == "REVISAO_MANUAL_SEM_MARKUP":
            lucros = [r[0] for r in conn.execute(
                "SELECT lucro_liquido_alvo_pct FROM politica_categoria "
                "WHERE lucro_liquido_alvo_pct IS NOT NULL")]
            lucro_mediano_fallback = median(lucros) if lucros else 0.15
            retry = economico.aplicar_travas(
                custo=row["custo_medio"],
                natureza_fiscal_item=natureza,
                tier=tier,
                valor_referencia_mercado=resultado_mercado.valor_referencia,
                divergencia_brick_web=resultado_mercado.divergencia_brick_web,
                lucro_liquido_alvo_pct=lucro_mediano_fallback + (
                    0.0 if resultado_mercado.alvo_so_local else ajuste_lucro_sem_vizinhanca),
                teto_cmed=row["pmc"],
                preco_atual=preco_atual_final,
                params=params,
                precos_concorrentes=precos_concorrentes,
                curva_abc=row["curva_abc"],
                e_chamariz=e_chamariz,
                menor_concorrente_local=menor_local,
                maior_concorrente_local=maior_local,
                categoria=categoria,
            )
            if retry.preco_sugerido is not None:
                status_gravado = "REVISAO_MANUAL_SEM_MARKUP_MARGEM_ESTIMADA"
                resultado = economico.ResultadoPrecificacao(
                    status=status_gravado,
                    preco_sugerido=retry.preco_sugerido,
                    justificativa=(f"{retry.justificativa} Sem categoria cadastrada: "
                                   f"aplicada margem mediana de {lucro_mediano_fallback:.0%} "
                                   "como estimativa; revisar a classificacao."),
                    piso=retry.piso, alvo=retry.alvo, tier=retry.tier,
                    custo_estimado=retry.custo_estimado,
                )

        justificativa_final = resultado.justificativa
        if nota_outlier:
            justificativa_final = f"[OUTLIER CORRIGIDO] {nota_outlier} {resultado.justificativa}"
        if motivo_eixo:
            justificativa_final += f" Categoria: {motivo_eixo}."
        # Rastreabilidade (paridade com o app): quem definiu o alvo aparece na
        # justificativa -- vizinhanca local x todos os concorrentes.
        if resultado_mercado.alvo_so_local:
            justificativa_final += (
                f" Alvo definido pelos {resultado_mercado.n_local} concorrentes "
                f"da vizinhanca (de {resultado_mercado.n} coletados); os demais "
                f"validaram o preco.")
        elif resultado_mercado.n_local or resultado_mercado.n:
            justificativa_final += (
                f" Vizinhanca insuficiente ({resultado_mercado.n_local} de "
                f"{resultado_mercado.n}): alvo usou todos os concorrentes.")

        # Paridade com o app: guarda de sanidade sobre o preco final. Ver
        # mercado.excede_sanidade -- sugestao de 3x+ a mediana crua de todos os
        # concorrentes, sem PMC que a justifique, e' custo/embalagem errada, nao
        # preco. Descartada em vez de gravada, senao vira preco aplicado.
        sanidade = mercado.excede_sanidade(resultado.preco_sugerido, obs, row["pmc"])
        if sanidade:
            centro, n_lojas = sanidade
            justificativa_final = (
                f"SUGESTAO DESCARTADA: R$ {resultado.preco_sugerido:.2f} e' "
                f"{resultado.preco_sugerido / centro:.0f}x a mediana de {n_lojas} "
                f"concorrentes (R$ {centro:.2f}) e nao ha PMC que justifique. Quase "
                f"sempre custo cadastrado errado ou preco de caixa lancado como "
                f"unidade -- conferir o cadastro. {justificativa_final}"
            )
            resultado = replace(resultado, preco_sugerido=None)
            status_gravado = "REVISAO_MANUAL_SUGESTAO_IMPOSSIVEL"

        mediana_historico = mediana_sugerido_historico(conn, ean, rodada_id)
        if economico.preco_atual_e_outlier_historico(preco_atual_final, mediana_historico):
            justificativa_final = (
                f"[PRECO CADASTRO SUSPEITO] preco_atual (R$ {preco_atual_final:.2f}) destoa da "
                f"mediana historica de sugestoes (R$ {mediana_historico:.2f}); cadastro provavelmente "
                f"desatualizado, ignorado como referencia. {justificativa_final}"
            )

        linhas.append((
            rodada_id, ean, row["descricao"], categoria, natureza, tier, status_gravado,
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


def margem_bruta_do_mix(conn: sqlite3.Connection, rodada_id: int) -> float | None:
    """Margem bruta AGREGADA da rodada: soma dos lucros / soma dos precos.

    Agregada, nao mediana: e' a margem que a DRE enxerga. Sem historico de
    venda proprio nao ha peso de volume para aplicar -- cada item entra uma
    vez. Quando houver venda, trocar por soma ponderada pelas unidades.
    """
    linha = conn.execute(
        "SELECT SUM(preco_sugerido - custo), SUM(preco_sugerido) FROM recomendacao "
        "WHERE rodada_id = ? AND preco_sugerido IS NOT NULL AND custo IS NOT NULL",
        (rodada_id,)).fetchone()
    if not linha or not linha[1]:
        return None
    return linha[0] / linha[1]


def rodar_com_controle_de_mix(conn: sqlite3.Connection, observacao: str | None) -> int:
    """Fase 3: roda, mede a margem do mix e, se ficou abaixo da meta da DRE,
    roda de novo elevando o lucro-alvo SO nos itens sem vizinhanca local.

    Duas passadas, nao um laco: a segunda ja usa o ajuste calculado com a
    medicao da primeira, e iterar mais nao converge melhor -- so multiplica
    rodadas no banco. Se a meta continuar longe, o motivo aparece no aviso de
    `ajuste_lucro_alvo_mix` e a resposta nao esta no preco.
    """
    params = parametros.carregar()
    rodada_id = processar_rodada(conn, observacao)
    margem = margem_bruta_do_mix(conn, rodada_id)
    ajuste, motivo = economico.ajuste_lucro_alvo_mix(margem, params)
    if motivo:
        print("\n=== Controle de margem do mix ===")
        print(f"  {motivo}")
    if ajuste <= 0:
        return rodada_id

    conn.execute("DELETE FROM recomendacao WHERE rodada_id = ?", (rodada_id,))
    conn.execute("DELETE FROM rodada WHERE id = ?", (rodada_id,))
    conn.commit()
    rodada_id = processar_rodada(
        conn, f"{observacao} + ajuste de mix {ajuste:.1%}",
        ajuste_lucro_sem_vizinhanca=ajuste)
    nova = margem_bruta_do_mix(conn, rodada_id)
    if nova is not None and margem is not None:
        print(f"  margem do mix: {margem:.2%} -> {nova:.2%} "
              f"(meta {economico.margem_bruta_meta_mix(params):.2%})")
    return rodada_id


def main() -> None:
    conn = db.connect()
    db.criar_schema(conn)
    rodada_id = rodar_com_controle_de_mix(
        conn, "rodada_v2_com_outlier_fix_e_controlados_habilitados")
    resumo_rodada(conn, rodada_id)
    comparar_com_anterior(conn, rodada_id)
    conn.close()


if __name__ == "__main__":
    main()
