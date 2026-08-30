"""Testes do motor economico: fiscal, piso, tier, alvo, travas, grade."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import economico, parametros  # noqa: E402

PARAMS = parametros.carregar()


def test_natureza_fiscal_medicamento_com_st():
    assert economico.natureza_fiscal("SIMILAR > RX-SIMILAR", tem_icms_st=True) == "medicamento"


def test_natureza_fiscal_medicamento_sem_st_vira_perfumaria_higiene():
    # categoria de medicamento sem evidencia de ST na NF: so o monofasico se aplica
    assert economico.natureza_fiscal("GENERICO > O.T.C/MIP", tem_icms_st=False) == "perfumaria_higiene"


def test_natureza_fiscal_perfumaria():
    assert economico.natureza_fiscal("PERFUMARIA > HIGIENE BUCAL", tem_icms_st=False) == "perfumaria_higiene"


def test_natureza_fiscal_varejo_padrao():
    assert economico.natureza_fiscal("VAREJO > LEITES", tem_icms_st=False) == "padrao"


def test_divisor_piso_desconta_toda_a_estrutura():
    """Composicao, nao constante: `despesas_fixas_pct` e parametro de negocio e
    mudou em 12/08/2026 (17,5% -> 23,33%, calibrado com R$ 35 mil reais de
    estrutura sobre R$ 150 mil/mes). Pinar o resultado aqui transformava uma
    decisao financeira em quebra de teste."""
    prem = PARAMS["premissas"]
    for natureza in ("medicamento", "perfumaria_higiene", "padrao"):
        esperado = (1 - prem["cartao_pct"] - prem["despesas_fixas_pct"]
                    - economico.despesas_de_comercializacao(PARAMS)
                    - economico.aliquota_simples_efetiva(PARAMS, natureza))
        assert economico.divisor_piso(PARAMS, natureza) == pytest.approx(esperado)
    # O divisor do ALVO rateia MAIS que o do piso: a despesa fixa entra so nele.
    for natureza in ("medicamento", "perfumaria_higiene", "padrao"):
        assert economico.divisor_piso(PARAMS, natureza) < economico.divisor_piso_contribuicao(
            PARAMS, natureza)


def test_despesas_de_comercializacao_soma_pbm_so_quando_pedido():
    base = economico.despesas_de_comercializacao(PARAMS)
    com_pbm = economico.despesas_de_comercializacao(PARAMS, tem_pbm=True)
    assert com_pbm == pytest.approx(base + PARAMS["premissas"].get("pbm_taxa_pct", 0.0))


def test_piso_e_maior_para_natureza_padrao_que_medicamento():
    # Com margem_bruta_minima_pct (0.25), ambos ficam iguais a custo/0.75.
    # Para testar a diferenca por natureza, desabilitamos a margem minima.
    params_sem_margem = dict(PARAMS)
    params_sem_margem["premissas"] = dict(PARAMS["premissas"])
    params_sem_margem["premissas"]["margem_bruta_minima_pct"] = 0.0
    params_sem_margem["premissas"]["margem_bruta_minima_por_natureza"] = {}
    custo = 10.0
    assert economico.piso(custo, params_sem_margem, "padrao") > economico.piso(custo, params_sem_margem, "medicamento")


def test_piso_usa_contribuicao_minima_em_item_barato():
    # item de R$0,50 de custo: piso por divisor seria ~0,68, mas a contribuicao
    # minima de R$0,60 (config) deve prevalecer.
    resultado = economico.piso(0.50, PARAMS, "padrao")
    assert resultado == 0.50 + PARAMS["premissas"]["contribuicao_minima_reais"]


def test_determinar_tier_revisao_humana_tem_prioridade():
    assert economico.determinar_tier("REVISAO_HUMANA", "A", 10, 0.05, True) == "REVISAO_HUMANA"


def test_determinar_tier_imagem_por_curva_a():
    assert economico.determinar_tier("PADRAO", "A", 1, None, True) == "PRECO_IMAGEM"


def test_determinar_tier_protecao_sem_mercado():
    assert economico.determinar_tier("PADRAO", "B", 0, None, False) == "PROTECAO_MARGEM"


def test_determinar_tier_curva_c_com_mercado_medido_nao_e_protecao():
    """Mudanca 2026-08-10: Curva C so forca PROTECAO_MARGEM quando o mercado e'
    de fato pouco medido. Com 8 concorrentes e CV 5% ha evidencia de sobra --
    tratar como 'sem mercado' rebaixava 66% do catalogo e apertava a trava de
    variacao (0,30 vs 0,50) sem motivo comercial."""
    assert economico.determinar_tier("PADRAO", "C", 8, 0.05, True) == "PRECO_IMAGEM"


def test_determinar_tier_curva_c_sem_mercado_continua_protecao():
    """O gate continua valendo onde ele existe para valer: Curva C com mercado
    ralo (< 3 concorrentes) segue protegendo margem."""
    assert economico.determinar_tier("PADRAO", "C", 2, None, True) == "PROTECAO_MARGEM"


def test_calcular_alvo_imagem_usa_99_da_mediana_fisica():
    alvo = economico.calcular_alvo("PRECO_IMAGEM", valor_referencia_mercado=20.0, alvo_econ=15.0)
    assert alvo == 20.0 * 0.99


def test_calcular_alvo_ranking_2o_lugar_com_concorrentes_suficientes():
    # decisao 2026-08-05: nao perseguir o menor preco -- ficar no 2o lugar
    # (config PADRAO=2), escolhendo o maior preco que ainda garanta a posicao.
    precos = [10.0, 12.0, 15.0, 20.0]  # 4 concorrentes, ordenado
    alvo = economico.calcular_alvo(
        "PADRAO", valor_referencia_mercado=14.0, alvo_econ=8.0,
        precos_concorrentes=precos, params=PARAMS,
    )
    # 2o lugar = media entre o 1o (10.0) e o 2o (12.0) concorrente
    assert alvo == pytest.approx((10.0 + 12.0) / 2)


def test_calcular_alvo_ranking_cai_para_regra_antiga_com_poucos_concorrentes():
    # com menos de n_min_observacoes (3), nao ha base estatistica para ranking:
    # mantem a regra antiga (mediana_fisica * 0.99).
    alvo = economico.calcular_alvo(
        "PADRAO", valor_referencia_mercado=20.0, alvo_econ=15.0,
        precos_concorrentes=[18.0, 19.0], params=PARAMS,
    )
    assert alvo == 20.0 * 0.99


def test_calcular_alvo_imagem_sem_precos_concorrentes_mantem_regra_antiga():
    # compatibilidade: chamada sem precos_concorrentes (parametro opcional)
    # continua igual a antes.
    alvo = economico.calcular_alvo("PRECO_IMAGEM", valor_referencia_mercado=20.0, alvo_econ=15.0)
    assert alvo == 20.0 * 0.99


# ── formadores de preco (uso continuo / anticoncepcional) -- decisao 2026-08-30 ──

@pytest.mark.parametrize("categoria", [
    "ETICOS > USO CONTINUO",
    "GENERICO > USO CONTINUO",
    "SIMILAR > USO CONTINUO",
    "ETICOS > ANTICONCEPCIONAL",
    "GENERICO > ANTICONCEPCIONAL",
    "SIMILAR > ANTICONCEPCIONAL",
])
def test_e_formador_opiniao_reconhece_as_subcategorias_da_politica(categoria):
    assert economico.e_formador_opiniao(categoria) is True


@pytest.mark.parametrize("categoria", [None, "", "ETICOS > RX", "ETICOS > CONTROLADO", "PERFUMARIA > FRALDAS"])
def test_e_formador_opiniao_nao_marca_o_resto_do_catalogo(categoria):
    assert economico.e_formador_opiniao(categoria) is False


def test_determinar_tier_formador_opiniao_ignora_protecao_por_mercado_fraco():
    # Curva C com 2 concorrentes e sem Brick: hoje isso e' e_protecao
    # incondicional (ver test_determinar_tier_curva_c_sem_mercado_continua_protecao).
    # Para USO CONTINUO/ANTICONCEPCIONAL (papel PRECO_IMAGEM na politica), a
    # politica de categoria tem que vencer o heuristico de mercado fraco.
    assert economico.determinar_tier(
        "PRECO_IMAGEM", "C", 2, None, False, categoria="ETICOS > USO CONTINUO",
    ) == "PRECO_IMAGEM"


def test_determinar_tier_formador_opiniao_nao_afeta_categoria_comum():
    # Mesmo cenario de mercado fraco, mas categoria fora da lista: continua
    # caindo em PROTECAO_MARGEM -- a excecao e' so para as categorias certas.
    assert economico.determinar_tier(
        "PRECO_IMAGEM", "C", 2, None, False, categoria="ETICOS > RX",
    ) == "PROTECAO_MARGEM"


def test_determinar_tier_formador_opiniao_exige_papel_preco_imagem():
    # A excecao nao dispara so pela categoria: se a politica cadastrada para
    # a categoria nao for PRECO_IMAGEM, o heuristico de mercado continua valendo.
    assert economico.determinar_tier(
        "PADRAO", "C", 2, None, False, categoria="ETICOS > USO CONTINUO",
    ) == "PROTECAO_MARGEM"


def test_alvo_por_ranking_formador_opiniao_mira_o_rank_1():
    precos = [10.0, 12.0, 15.0, 20.0]
    alvo = economico.alvo_por_ranking(
        "PRECO_IMAGEM", precos, PARAMS, curva_abc="C", categoria="GENERICO > ANTICONCEPCIONAL",
    )
    # rank 1 = 99% do menor concorrente, mesmo com curva C (que normalmente
    # miraria o 3o lugar) e tier PRECO_IMAGEM (que miraria o 2o).
    assert alvo == pytest.approx(10.0 * 0.99)


def test_alvo_por_ranking_curva_c_comum_continua_no_3o_lugar():
    precos = [10.0, 12.0, 15.0, 20.0]
    alvo = economico.alvo_por_ranking("PRECO_IMAGEM", precos, PARAMS, curva_abc="C")
    abaixo, no_alvo = precos[1], precos[2]  # rank 3 = media entre 2o e 3o
    assert alvo == pytest.approx((abaixo + no_alvo) / 2)


def test_calcular_alvo_formador_opiniao_garante_piso_por_fora():
    # calcular_alvo devolve o ALVO (rank 1); quem garante que o preco final
    # nunca fica abaixo do piso e' aplicar_travas/arredondar_grade, nao esta
    # funcao -- aqui so' confirmamos que o alvo de fato mira o mais barato.
    precos = [10.0, 12.0, 15.0]
    alvo = economico.calcular_alvo(
        "PRECO_IMAGEM", valor_referencia_mercado=14.0, alvo_econ=8.0,
        precos_concorrentes=precos, params=PARAMS, curva_abc="C",
        categoria="SIMILAR > USO CONTINUO",
    )
    assert alvo == pytest.approx(10.0 * 0.99)


def test_travas_sem_custo_estima_custo_pela_fracao_com_shrinkage_da_natureza():
    # Ate 30/08/2026 este teste pinava 0.60 (constante global unica). Desde o
    # item 6 (shrinkage bayesiano por natureza), "padrao" tem seu proprio
    # pct_shrunk no TOML -- pinar aqui reintroduziria a mesma fragilidade que
    # `test_divisor_piso_desconta_toda_a_estrutura` ja evita para despesas_fixas_pct.
    r = economico.aplicar_travas(
        custo=None, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=20.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_SEM_CUSTO_BASE_MERCADO"
    assert r.custo_estimado is not None
    pct_esperado = economico.pct_custo_estimado("padrao", PARAMS)
    assert r.custo_estimado == pytest.approx(r.preco_sugerido * pct_esperado)


def test_calcular_alvo_protecao_margem_limitada_por_mercado():
    # alvo economico bem alto, mas mercado existe: protecao fica limitada a mercado*1.15
    alvo = economico.calcular_alvo("PROTECAO_MARGEM", valor_referencia_mercado=10.0, alvo_econ=50.0)
    assert alvo == 10.0 * 1.15


def test_calcular_alvo_protecao_margem_sem_mercado_usa_alvo_economico():
    alvo = economico.calcular_alvo("PROTECAO_MARGEM", valor_referencia_mercado=None, alvo_econ=50.0)
    assert alvo == 50.0


def test_arredondar_grade_respeita_piso_e_teto():
    r = economico.arredondar_grade(alvo=25.30, piso_valor=24.00, teto=26.00, terminacoes=[0.49, 0.79, 0.90, 0.95, 0.99])
    assert r.preco is not None
    assert 24.00 <= r.preco <= 26.00


def test_arredondar_grade_nao_ultrapassa_teto_baixo():
    # bug do script antigo: grid_price nao recebia teto e podia estourar o PMC
    r = economico.arredondar_grade(alvo=30.0, piso_valor=20.0, teto=20.50, terminacoes=[0.49, 0.79, 0.90, 0.95, 0.99])
    assert r.preco is not None
    assert r.preco <= 20.50


def test_arredondar_grade_impossivel_quando_piso_maior_que_teto():
    r = economico.arredondar_grade(alvo=30.0, piso_valor=25.0, teto=20.0, terminacoes=[0.49, 0.79, 0.90, 0.95, 0.99])
    assert r.preco is None


def test_travas_sem_custo_com_mercado_sugere_preco_por_mercado():
    r = economico.aplicar_travas(
        custo=None, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=20.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_SEM_CUSTO_BASE_MERCADO"
    assert r.preco_sugerido is not None
    assert r.preco_sugerido <= 20.0


def test_travas_sem_custo_e_sem_mercado_nao_ha_base():
    r = economico.aplicar_travas(
        custo=None, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=None,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "REVISAO_MANUAL_SEM_CUSTO_E_SEM_MERCADO"
    assert r.preco_sugerido is None


def test_travas_divergencia_brick_web_sinaliza_mas_ainda_sugere_preco():
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=20.0,
        divergencia_brick_web=True, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "DIVERGENCIA_BRICK_WEB"
    assert r.preco_sugerido is not None


def test_travas_mercado_abaixo_do_custo_sugere_preco_no_piso():
    r = economico.aplicar_travas(
        custo=15.0, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=12.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    # MUDANCA 12/08/2026: custo 15 contra mercado 12 e' 1,25x -- compra ruim, nao
    # erro de embalagem (esse e' >= 3x). Precifica no piso minimo e segue.
    assert r.status == "OK_MARGEM_MINIMA_MERCADO"
    assert r.preco_sugerido is not None
    assert r.preco_sugerido >= r.piso - 1e-9


def test_travas_piso_acima_do_teto_cmed():
    # Piso novo (despesa fixa fora do piso, so variavel + cartao + Simples):
    # custo 50 em medicamento -> 50/0.9347 ~= 53.49. Com teto CMED abaixo do
    # piso, o status sinaliza e o preco fica limitado ao teto.
    r = economico.aplicar_travas(
        custo=50.0, natureza_fiscal_item="medicamento", tier="PADRAO", valor_referencia_mercado=60.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=50.0, preco_atual=None, params=PARAMS,
    )
    # MUDANCA 12/08/2026: o teto CMED e' lei, nao ha decisao humana a tomar --
    # o preco E' o teto, descido para a maior terminacao da grade que cabe nele.
    assert r.status == "OK_TETO_CMED"
    assert r.preco_sugerido is not None and r.preco_sugerido <= 50.0


def test_travas_preco_atual_nao_disponivel_nao_trava_mais():
    # preco_atual (cadastro) e reconhecidamente nao confiavel: mesmo distante
    # do preco sugerido, nao deve mais travar a sugestao.
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=15.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=2.0, params=PARAMS,
    )
    assert r.status != "REVISAO_MANUAL_VARIACAO_ALTA"
    assert r.status == "OK"
    assert r.preco_sugerido is not None


def test_travas_divergencia_mercado_forte_sinaliza_mas_ainda_sugere_preco():
    # Com o piso novo (despesa fixa fora do piso), o mesmo cenario de antes
    # (lucro-alvo alto em PROTECAO_MARGEM) fica dentro dos 30% e sai OK -- o
    # piso nao domina mais o alvo. O status FORTE continua existindo para
    # quando a variacao realmente passa do limite: testamos com a trava de
    # PROTECAO_MARGEM reduzida a 5% (grade 11.99 vs mercado 10.50 = 14%).
    params_trava_apertada = dict(PARAMS)
    params_trava_apertada["trava"] = dict(PARAMS["trava"])
    params_trava_apertada["trava"]["variacao_maxima_mercado_por_tier"] = dict(
        PARAMS["trava"]["variacao_maxima_mercado_por_tier"])
    params_trava_apertada["trava"]["variacao_maxima_mercado_por_tier"]["PROTECAO_MARGEM"] = 0.05
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PROTECAO_MARGEM", valor_referencia_mercado=10.5,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.50, teto_cmed=None, preco_atual=None,
        params=params_trava_apertada,
    )
    assert r.status == "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE"
    assert r.preco_sugerido is not None


def test_travas_piso_acima_do_mercado_sugere_preco_no_piso():
    # mercado muito abaixo do alvo economico (margem-alvo alta) mas ainda acima do custo:
    # antes bloqueava; agora sugere o preco no piso, com margem reduzida.
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=10.5,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.20, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_MARGEM_REDUZIDA"
    assert r.preco_sugerido is not None
    assert r.preco_sugerido >= r.piso - 1e-9


def test_travas_ok_de_ponta_a_ponta():
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=15.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=15.30, params=PARAMS,
    )
    assert r.status == "OK"
    assert r.preco_sugerido is not None
    assert r.piso is not None and r.preco_sugerido >= r.piso - 1e-9


# --- Testes novos: margem bruta minima no piso (2026-08-08) ---

def test_piso_respeita_margem_bruta_minima():
    """Custo 35.35, margem minima 25% -> piso >= 47.13."""
    params_com_margem = dict(PARAMS)
    params_com_margem["premissas"] = dict(PARAMS["premissas"])
    params_com_margem["premissas"]["margem_bruta_minima_pct"] = 0.25
    params_com_margem["premissas"]["margem_bruta_minima_por_natureza"] = {}
    resultado = economico.piso(35.35, params_com_margem, "medicamento")
    assert resultado == pytest.approx(35.35 / (1 - 0.25))  # 47.13


def test_piso_margem_zero_nao_altera():
    """Com margem_bruta_minima_pct = 0, comportamento identico ao sem margem."""
    params_sem_margem = dict(PARAMS)
    params_sem_margem["premissas"] = dict(PARAMS["premissas"])
    params_sem_margem["premissas"]["margem_bruta_minima_pct"] = 0.0
    params_sem_margem["premissas"]["margem_bruta_minima_por_natureza"] = {}
    # Deve cair no comportamento antigo: max(piso_simples, piso_contribuicao)
    resultado = economico.piso(10.0, params_sem_margem, "padrao")
    piso_simples = 10.0 / economico.divisor_piso_contribuicao(params_sem_margem, "padrao")
    piso_contrib = 10.0 + params_sem_margem["premissas"]["contribuicao_minima_reais"]
    assert resultado == max(piso_simples, piso_contrib)


def test_piso_prevalece_maior_dos_tres():
    """Com margem minima alta, o piso_margem deve prevalecer sobre os outros."""
    params_margem_alta = dict(PARAMS)
    params_margem_alta["premissas"] = dict(PARAMS["premissas"])
    params_margem_alta["premissas"]["margem_bruta_minima_pct"] = 0.90
    params_margem_alta["premissas"]["margem_bruta_minima_por_natureza"] = {}
    # piso_margem = 10 / 0.10 = 100, muito maior que piso_simples e piso_contribuicao
    resultado = economico.piso(10.0, params_margem_alta, "medicamento")
    assert resultado == pytest.approx(10.0 / 0.10)  # 100.0


def test_piso_margem_bruta_invalida_ignorada():
    """Margem >= 1 ou <= 0 nao deve ser aplicada (evita divisao por zero ou negativa)."""
    for valor_invalido in (1.0, 0.0, -0.1):
        params = dict(PARAMS)
        params["premissas"] = dict(PARAMS["premissas"])
        params["premissas"]["margem_bruta_minima_pct"] = valor_invalido
        params["premissas"]["margem_bruta_minima_por_natureza"] = {}
        resultado = economico.piso(10.0, params, "padrao")
        # Com margem invalida, cai no max(piso_simples, piso_contribuicao)
        piso_simples = 10.0 / economico.divisor_piso_contribuicao(params, "padrao")
        piso_contrib = 10.0 + params["premissas"]["contribuicao_minima_reais"]
        assert resultado == max(piso_simples, piso_contrib), f"falhou para margem={valor_invalido}"


# --- Grade psicologica por limiar de digito da esquerda (ESTUDO_PRICING_2026) ---

def test_fronteira_digito_esquerda_por_faixa():
    assert economico.fronteira_digito_esquerda(19.49) == 20.0    # abaixo de 20: passo 1
    assert economico.fronteira_digito_esquerda(19.99) == 20.0
    assert economico.fronteira_digito_esquerda(46.20) == 50.0    # 20-100: passo 5
    assert economico.fronteira_digito_esquerda(112.00) == 120.0  # acima: passo 10


def test_grade_limiar_sobe_ate_a_fronteira_sem_cruza_la():
    # alvo 19,30: a regra antiga escolhe 19,49 (a mais proxima). A nova sobe ate
    # 19,79 -- o maximo que cabe na tolerancia de 3% (19,88) sem cruzar o 20,00.
    r = economico.arredondar_grade(
        alvo=19.30, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS)
    assert r.preco == pytest.approx(19.79)

    # alvo 19,60: a tolerancia (20,19) ja alcanca o 19,99, mas a fronteira do
    # digito da esquerda corta ali -- nunca em 20,49.
    r = economico.arredondar_grade(
        alvo=19.60, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS)
    assert r.preco == pytest.approx(19.99)


def test_grade_limiar_respeita_tolerancia_sobre_o_alvo():
    # alvo 19,00 -> base 18,99, e a fronteira do digito da esquerda e' 19,00:
    # nao ha para onde subir sem virar "dezenove". Fica em 18,99.
    r = economico.arredondar_grade(
        alvo=19.00, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS)
    assert r.preco == pytest.approx(18.99)

    # alvo 46,00 (faixa de passo 5): sobe ate 46,99, nunca ate 47,49 -- a
    # tolerancia de 3% (47,38) permitiria, a fronteira nao.
    r = economico.arredondar_grade(
        alvo=46.00, piso_valor=40.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS)
    assert 46.00 <= r.preco < 47.00


def test_grade_limiar_nao_ultrapassa_concorrente_local():
    # Ha concorrente local a 19,60: subir para 19,99 nos tornaria mais caros
    # que ele. A regra para em 19,49.
    r = economico.arredondar_grade(
        alvo=19.30, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS,
        precos_locais=[17.00, 19.60, 22.00])
    assert r.preco == pytest.approx(19.49)


def test_grade_limiar_nao_sobe_quando_ja_somos_o_mais_caro():
    r = economico.arredondar_grade(
        alvo=19.30, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"], params=PARAMS,
        precos_locais=[15.00, 16.00, 17.00])
    assert r.preco == pytest.approx(19.49)


def test_grade_sem_params_mantem_comportamento_antigo():
    r = economico.arredondar_grade(
        alvo=19.30, piso_valor=15.0, teto=None,
        terminacoes=PARAMS["grade"]["terminacoes"])
    assert r.preco == pytest.approx(19.49)


# --- Teto competitivo ---

def test_teto_competitivo_limita_preco_acima_de_toda_a_praca():
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="perfumaria_higiene", tier="PROTECAO_MARGEM",
        valor_referencia_mercado=20.0, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.20, teto_cmed=None, preco_atual=None, params=PARAMS,
        precos_concorrentes=[16.0, 17.0, 18.0], curva_abc="B",
        menor_concorrente_local=16.0, maior_concorrente_local=18.0,
    )
    assert r.preco_sugerido is not None
    assert r.preco_sugerido <= 18.0


def test_teto_competitivo_cede_para_o_piso():
    # Custo alto: o piso nao cabe abaixo do maior local. O preco fica acima da
    # praca de proposito e o status honesto sinaliza -- nao vende no prejuizo.
    r = economico.aplicar_travas(
        custo=20.0, natureza_fiscal_item="perfumaria_higiene", tier="PROTECAO_MARGEM",
        valor_referencia_mercado=24.0, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.20, teto_cmed=None, preco_atual=None, params=PARAMS,
        precos_concorrentes=[22.0, 24.0, 25.0], curva_abc="B",
        menor_concorrente_local=22.0, maior_concorrente_local=25.0,
    )
    # MUDANCA 12/08/2026: antes de devolver um preco que nao vende, o motor
    # tenta o PISO MINIMO (sem a margem-alvo da DRE). Aqui ele cabe embaixo do
    # maior local (25,00), entao o item volta para dentro do mercado com margem
    # baixa em vez de ficar acima da praca inteira.
    assert r.status == "OK_MARGEM_MINIMA_MERCADO"
    assert r.preco_sugerido <= 25.0


def test_teto_competitivo_nao_se_aplica_a_chamariz():
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="perfumaria_higiene", tier="PROTECAO_MARGEM",
        valor_referencia_mercado=20.0, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.20, teto_cmed=None, preco_atual=None, params=PARAMS,
        precos_concorrentes=[16.0, 17.0, 18.0], curva_abc="B", e_chamariz=True,
        menor_concorrente_local=16.0, maior_concorrente_local=18.0,
    )
    # chamariz busca o MENOR concorrente, entao nem chega perto do teto
    assert r.preco_sugerido is not None and r.preco_sugerido <= 16.0


def test_piso_competitivo_vira_piso_duro_da_grade():
    """Ate 12/08/2026 a grade arredondava para BAIXO do menor concorrente local
    depois de o piso competitivo ter subido o alvo -- e justo por cima da
    fronteira de digito esquerdo (7,21 -> 6,99), onde mais custa."""
    grade = economico.arredondar_grade(
        7.21, 7.21, None, PARAMS["grade"]["terminacoes"], PARAMS, [7.21, 9.90])
    assert grade.preco is not None and grade.preco >= 7.21


def test_piso_duro_cede_para_o_teto_cmed():
    """Piso competitivo e' politica; teto CMED e' lei. Quando o menor
    concorrente local esta acima do PMC, o item nao pode ficar sem preco."""
    grade = economico.arredondar_grade(
        10.0, 10.0, 9.0, PARAMS["grade"]["terminacoes"], PARAMS, None)
    # com piso 10 e teto 9 nao existe grade: quem chama tem de ceder o piso
    assert grade.preco is None
    grade_ok = economico.arredondar_grade(
        10.0, 8.0, 9.0, PARAMS["grade"]["terminacoes"], PARAMS, None)
    assert grade_ok.preco is not None and grade_ok.preco <= 9.0


def test_piso_minimo_e_menor_que_o_piso_cheio():
    """O piso minimo tira a margem-alvo da DRE e deixa so o que e' restricao de
    verdade: imposto, despesa variavel e a contribuicao em reais."""
    for natureza in ("medicamento", "perfumaria_higiene", "padrao"):
        assert economico.piso_minimo(20.0, PARAMS, natureza) < economico.piso(20.0, PARAMS, natureza)
        assert economico.piso_minimo(20.0, PARAMS, natureza) > 20.0


def test_teto_cmed_nao_bloqueia_mais_e_desce_para_a_grade():
    """Teto CMED e' lei -- nao existe decisao humana. O preco e' o teto, na maior
    terminacao da grade que cabe nele."""
    r = economico.aplicar_travas(
        custo=50.0, natureza_fiscal_item="medicamento", tier="PADRAO",
        valor_referencia_mercado=60.0, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.10, teto_cmed=50.0, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_TETO_CMED"
    assert r.preco_sugerido is not None and r.preco_sugerido <= 50.0
    assert not r.status.startswith("REVISAO_MANUAL")


def test_divergencia_forte_absolvida_quando_a_referencia_e_que_esta_furada():
    """TRIDENT MENTA C/5 (12/08/2026): custo R$ 1,81, um 'concorrente' a R$ 51,40
    (preco de display) levou a referencia a R$ 28,81. A sugestao de R$ 4,99
    estava CERTA e era ela que caia na fila de revisao."""
    r = economico.aplicar_travas(
        custo=1.81, natureza_fiscal_item="padrao", tier="PROTECAO_MARGEM",
        valor_referencia_mercado=28.81, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
        precos_concorrentes=[4.55], curva_abc="B",
    )
    assert r.status != "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE"
    assert r.preco_sugerido is not None and r.preco_sugerido < 10.0


def test_divergencia_forte_continua_agindo_com_referencia_plausivel():
    """A absolvicao exige que a REFERENCIA seja implausivel. Referencia a 1,05x o
    custo faz todo sentido -- quem esta fora e' a sugestao, e a trava age."""
    params = dict(PARAMS)
    params["trava"] = dict(PARAMS["trava"])
    params["trava"]["variacao_maxima_mercado_por_tier"] = dict(
        PARAMS["trava"]["variacao_maxima_mercado_por_tier"])
    params["trava"]["variacao_maxima_mercado_por_tier"]["PROTECAO_MARGEM"] = 0.05
    r = economico.aplicar_travas(
        custo=10.0, natureza_fiscal_item="padrao", tier="PROTECAO_MARGEM",
        valor_referencia_mercado=10.5, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.50, teto_cmed=None, preco_atual=None, params=params,
    )
    assert r.status == "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE"


def test_custo_muito_acima_do_mercado_e_erro_de_embalagem():
    """SAB PROTEX C/12: custo 39,89 (NF em pack) contra mercado 3,99. 10x nao e'
    compra ruim, e' fator_venda faltando."""
    r = economico.aplicar_travas(
        custo=39.89, natureza_fiscal_item="perfumaria_higiene", tier="PADRAO",
        valor_referencia_mercado=3.99, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM"


# ── pct_custo_estimado: shrinkage bayesiano (item 6, plano 2026-08-30) ──

def test_pct_custo_estimado_usa_valor_por_natureza_quando_existe():
    params = {"custo_estimado": {
        "pct_do_preco_mercado": 0.60,
        "por_natureza": {"medicamento": {"n": 452, "pct_shrunk": 0.5532}},
    }}
    assert economico.pct_custo_estimado("medicamento", params) == 0.5532


def test_pct_custo_estimado_cai_no_global_para_natureza_desconhecida():
    params = {"custo_estimado": {
        "pct_do_preco_mercado": 0.60,
        "por_natureza": {"medicamento": {"n": 452, "pct_shrunk": 0.5532}},
    }}
    assert economico.pct_custo_estimado("padrao", params) == 0.60
    assert economico.pct_custo_estimado(None, params) == 0.60


def test_pct_custo_estimado_cai_no_global_sem_tabela_por_natureza():
    params = {"custo_estimado": {"pct_do_preco_mercado": 0.60}}
    assert economico.pct_custo_estimado("medicamento", params) == 0.60


def test_pct_custo_estimado_usa_default_060_sem_secao_custo_estimado():
    assert economico.pct_custo_estimado("medicamento", {}) == 0.60


def test_pct_custo_estimado_com_os_parametros_reais_fica_entre_50_e_70_por_cento():
    # guarda de sanidade: o shrinkage nao pode devolver algo fora da faixa
    # plausivel de markup (medido em 30/08/2026: 0.5532 a 0.6632).
    for natureza in ("medicamento", "perfumaria_higiene", "padrao"):
        pct = economico.pct_custo_estimado(natureza, PARAMS)
        assert 0.40 <= pct <= 0.80


def test_custo_pouco_acima_do_mercado_e_compra_ruim_e_nao_bloqueia():
    """RISQUE ESM: custo 8,99 contra mercado 7,55. 1,2x nao tem erro de dado
    nenhum -- e' compra ruim, e o motor tem de precificar e seguir."""
    r = economico.aplicar_travas(
        custo=8.99, natureza_fiscal_item="perfumaria_higiene", tier="PADRAO",
        valor_referencia_mercado=7.55, divergencia_brick_web=False,
        lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_MARGEM_MINIMA_MERCADO"
    assert r.preco_sugerido is not None and r.preco_sugerido > 8.99
