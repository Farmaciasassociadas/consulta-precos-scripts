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


def test_divisor_piso_bate_com_tabela_do_plano():
    # PLANO_SISTEMA_PRECIFICACAO.md Parte 2.2
    assert economico.divisor_piso(PARAMS, "medicamento") == pytest.approx(0.7698, abs=0.0005)
    assert economico.divisor_piso(PARAMS, "perfumaria_higiene") == pytest.approx(0.7495, abs=0.0005)
    assert economico.divisor_piso(PARAMS, "padrao") == pytest.approx(0.7402, abs=0.0005)


def test_piso_e_maior_para_natureza_padrao_que_medicamento():
    custo = 10.0
    assert economico.piso(custo, PARAMS, "padrao") > economico.piso(custo, PARAMS, "medicamento")


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


def test_determinar_tier_protecao_curva_c_mesmo_com_boa_concorrencia():
    assert economico.determinar_tier("PADRAO", "C", 8, 0.05, True) == "PROTECAO_MARGEM"


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


def test_travas_sem_custo_estima_custo_a_60pct_do_preco_de_mercado():
    r = economico.aplicar_travas(
        custo=None, natureza_fiscal_item="padrao", tier="PADRAO", valor_referencia_mercado=20.0,
        divergencia_brick_web=False, lucro_liquido_alvo_pct=0.10, teto_cmed=None, preco_atual=None, params=PARAMS,
    )
    assert r.status == "OK_SEM_CUSTO_BASE_MERCADO"
    assert r.custo_estimado is not None
    assert r.custo_estimado == pytest.approx(r.preco_sugerido * 0.60)


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
    assert r.status == "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM"
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
    assert r.status == "REVISAO_MANUAL_PISO_ACIMA_DO_TETO"
    assert r.preco_sugerido == 50.0


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
