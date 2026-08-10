"""Testes do motor de mercado: camadas de outlier e blend Brick/web.

Casos de fronteira construidos a partir de padroes reais observados no CSV
de coleta (promocao em `observacoes`, poucos concorrentes, dispersao alta)
mais um teste de sanidade contra o banco ja carregado (Fase 1).
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path
from statistics import median

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine import mercado, parametros  # noqa: E402

HOJE = date(2026, 8, 2)
PARAMS = parametros.carregar()


def obs(preco, status="OK", dias_atras=0, observacoes=None, site="teste"):
    data = HOJE - timedelta(days=dias_atras)
    return mercado.Observacao(site=site, preco=preco, status=status, data_hora=data, observacoes=observacoes)


def test_camada_1_descarta_status_nao_ok_e_preco_ausente():
    lista = [obs(10.0, status="NAO_ENCONTRADO"), obs(None, status="OK"), obs(20.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert [o.preco for o in r.mantidas] == [20.0]
    assert len(r.descartadas) == 2


def test_camada_1_descarta_preco_promocional():
    lista = [obs(15.0, observacoes="Promoção: leve 2 pague 1"), obs(18.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert [o.preco for o in r.mantidas] == [18.0]
    assert r.descartadas[0].camada == "natureza"


def test_camada_1_mantem_preco_sem_palavras_promocionais():
    # Promoção sem "leve", "clube", "assinante" é retida como preço real
    lista = [obs(20.0, observacoes="Promoção: de R$ 25 por R$ 20"), obs(18.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    precos = sorted(o.preco for o in r.mantidas)
    assert precos == [18.0, 20.0]
    assert len(r.descartadas) == 0


def test_camada_2_descarta_preco_velho():
    lista = [obs(10.0, dias_atras=90), obs(11.0, dias_atras=5)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert [o.preco for o in r.mantidas] == [11.0]
    assert r.descartadas[0].camada == "frescor"


def test_camada_3_ancora_mata_promocao_pontual_mesmo_com_poucos_precos():
    # cenario real: 2 precos web, um deles e liquidacao a 40% do praticado na regiao
    lista = [obs(30.0), obs(12.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=29.0)  # ancora = Brick
    assert [o.preco for o in r.mantidas] == [30.0]
    assert r.descartadas[0].camada == "ancora"


def test_camada_3_nao_atua_sem_ancora():
    lista = [obs(30.0), obs(12.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=None)
    assert len(r.mantidas) == 2


def test_camada_4_mad_precisa_de_n_minimo():
    # 4 observacoes, uma bem discrepante: sem ancora, MAD so age com n>=5 (config atual)
    lista = [obs(10.0), obs(10.5), obs(11.0), obs(40.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert len(r.mantidas) == 4  # nao filtrou, n=4 < mad_n_min=5


def test_camada_4_mad_filtra_com_n_suficiente():
    lista = [obs(10.0), obs(10.2), obs(10.5), obs(10.8), obs(40.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    precos = sorted(o.preco for o in r.mantidas)
    assert 40.0 not in precos
    assert len(r.mantidas) == 4


def test_custo_abaixo_nao_e_removido_por_outlier():
    # regra da metodologia: preco abaixo do custo dispara revisao, nao e "outlier" a descartar.
    # a trava de custo e responsabilidade da Fase 3 (engine economico); aqui so confirmamos
    # que a camada de ancora do motor de mercado nao remove precos dentro da banda.
    lista = [obs(8.0), obs(8.5)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=8.2)
    assert len(r.mantidas) == 2


def test_peso_brick_sobe_quando_web_e_fraca():
    poucos = [obs(20.0)]
    r_pouco = mercado.calcular_mercado(poucos, PARAMS, HOJE, vum_brick=18.0, segmento_brick="RX")
    muitos = [obs(20.0), obs(19.5), obs(20.2), obs(19.8), obs(20.1)]
    r_muitos = mercado.calcular_mercado(muitos, PARAMS, HOJE, vum_brick=18.0, segmento_brick="RX")
    assert r_pouco.peso_brick > r_muitos.peso_brick


def test_sem_web_usa_brick_integralmente():
    r = mercado.calcular_mercado([], PARAMS, HOJE, vum_brick=25.0, segmento_brick="GEN")
    assert r.peso_brick == 1.0
    # O Brick sobe para a escala regional (dividido pela razao Brick/web).
    fator_bw = PARAMS["mercado"]["fator_fisico"]["GEN"]
    assert r.valor_referencia == pytest.approx(
        25.0 * (1 + PARAMS["mercado"]["brick"]["spread_etiqueta"]) / fator_bw)
    assert r.confianca == "MEDIA"


def test_sem_brick_usa_so_web():
    params_sem_canal = PARAMS
    lista = [obs(20.0), obs(21.0), obs(19.5)]
    r = mercado.calcular_mercado(lista, params_sem_canal, HOJE, vum_brick=None)
    assert r.peso_brick == 0.0
    # Sem fator: a mediana web e' a propria referencia (o premio de balcao so
    # entra com natureza_fiscal_item conhecida). Ate 2026-08-10 a web era
    # multiplicada por fator_fisico, empurrando o preco para a escala nacional.
    assert r.valor_referencia == median([20.0, 21.0, 19.5])


def test_camada_1_nao_descarta_mais_marketplace():
    # Decisao 2026-08-05: MARKETPLACE (vendedor terceiro) deixa de ser
    # descartado pela camada de natureza -- so status realmente invalido
    # (ex.: NAO_ENCONTRADO) ou preco ausente continuam sendo descartados.
    lista = [obs(18.0, status="MARKETPLACE"), obs(20.0, status="OK")]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert sorted(o.preco for o in r.mantidas) == [18.0, 20.0]
    assert len(r.descartadas) == 0


def test_mediana_ponderada_com_peso_igual_bate_com_mediana_padrao():
    # Sem nenhuma observacao MARKETPLACE, a versao ponderada deve devolver
    # exatamente statistics.median (inclusive para lista de tamanho par,
    # que faz media dos dois centrais).
    observacoes = [obs(10.0), obs(20.0), obs(30.0), obs(40.0)]
    assert mercado._mediana_ponderada(observacoes, PARAMS) == median([10.0, 20.0, 30.0, 40.0])


def test_mediana_ponderada_da_menos_peso_a_marketplace():
    # Um preco MARKETPLACE muito baixo (10.0) nao deve puxar a mediana com o
    # mesmo peso de um preco OK -- com peso 0.90 (config atual) ele ainda
    # pesa quase igual, mas a funcao deve pelo menos usar o peso configurado
    # em vez de ignorar por completo o status (o que a trava de regressao
    # abaixo prova comparando com o cenario de peso total igual).
    marketplace_baixo = [obs(10.0, status="MARKETPLACE"), obs(30.0), obs(31.0)]
    resultado = mercado._mediana_ponderada(marketplace_baixo, PARAMS)
    assert resultado == 30.0  # mediana simples tambem seria 30.0 aqui (3 obs, meio = 30.0)

    # Com peso reduzido de marketplace, testamos um caso onde o peso
    # realmente muda o resultado: dois precos "puxando para baixo" com um
    # deles marketplace (peso < 1) vs. dois precos OK "puxando para cima".
    params_peso_baixo = {**PARAMS, "mercado": {**PARAMS["mercado"], "marketplace": {"peso": 0.10}}}
    lista = [obs(10.0, status="MARKETPLACE"), obs(11.0, status="MARKETPLACE"), obs(30.0), obs(31.0)]
    resultado_peso_baixo = mercado._mediana_ponderada(lista, params_peso_baixo)
    resultado_peso_pleno = mercado._mediana_ponderada(lista, {**PARAMS, "mercado": {**PARAMS["mercado"], "marketplace": {"peso": 1.0}}})
    assert resultado_peso_baixo != resultado_peso_pleno


def test_calcular_mercado_inclui_marketplace_com_peso_reduzido():
    # Cenario de integracao: marketplace nao pode mais ser descartado pela
    # camada de natureza (antes sumia e n caia para 2); agora sobrevive e
    # entra na mediana ponderada, com o peso de config/parametros.toml.
    params_sem_canal = PARAMS
    com_marketplace = [obs(20.0, status="OK"), obs(21.0, status="OK"), obs(15.0, status="MARKETPLACE")]
    r = mercado.calcular_mercado(com_marketplace, params_sem_canal, HOJE, vum_brick=None)

    assert r.n == 3  # marketplace conta na contagem de observacoes validas (nao foi descartado)
    assert r.mediana == mercado._mediana_ponderada(
        [o for o in com_marketplace], params_sem_canal
    )

    # Com o peso de marketplace artificialmente alto (> soma dos pesos OK),
    # o preco de marketplace passa a dominar a mediana -- comprova que o
    # peso configurado realmente participa do calculo, nao e so "incluido
    # e ignorado".
    params_peso_alto = dict(params_sem_canal)
    params_peso_alto["mercado"] = dict(params_sem_canal["mercado"])
    params_peso_alto["mercado"]["marketplace"] = {"peso": 5.0}
    r_peso_alto = mercado.calcular_mercado(com_marketplace, params_peso_alto, HOJE, vum_brick=None)
    assert r_peso_alto.mediana == 15.0
    assert r_peso_alto.mediana != r.mediana


def test_divergencia_brick_web_e_sinalizada():
    # web muito acima do Brick (ex.: EAN com apresentacao trocada)
    lista = [obs(50.0), obs(52.0), obs(48.0)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=20.0, segmento_brick="GEN")
    assert r.divergencia_brick_web is True


def test_cluster_acima_brick_e_adotado_quando_concorrentes_convergem():
    # caso real BUPROVIL 600mg C/20 (2026-08-04): Brick 13,93, concorrentes
    # entre 22 e 24.
    #
    # MUDANCA 2026-08-10: este caso NAO cai mais no cluster, e isso e' a
    # correcao funcionando. A ancora agora sobe para a escala regional
    # (13,93 / 0,92 = 15,14) e o teto da banda vai a 24,23 -- os quatro precos
    # CABEM na banda, entao nao ha descarte a resgatar. O cluster era um
    # remendo para a ancora estar na escala errada (teto 22,29 descartava 3 dos
    # 4 concorrentes REAIS). Com a escala certa, o remendo fica ocioso aqui.
    lista = [obs(22.99), obs(23.99), obs(22.07), obs(23.99)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=13.93, segmento_brick="GEN")
    assert r.cluster_acima_brick is False
    assert r.filtro.descartadas == ()  # nenhum concorrente real e' mais jogado fora


def test_cluster_acima_brick_ainda_age_com_brick_muito_defasado():
    """O cluster continua existindo para Brick REALMENTE defasado: com brick 8,00
    (ancora 8,70, teto 13,91) os concorrentes em 22-24 seguem fora da banda e o
    cluster os resgata, em vez de colar no Brick puro."""
    lista = [obs(22.99), obs(23.99), obs(22.07), obs(23.99)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=8.00, segmento_brick="GEN")
    assert r.cluster_acima_brick is True
    assert r.valor_referencia > 13.93 * (1 + PARAMS["mercado"]["brick"]["spread_etiqueta"])


def test_cluster_acima_brick_nao_atua_se_concorrentes_dispersos():
    # concorrentes acima da banda mas sem convergencia (CV alto): fica como antes,
    # colado no Brick, porque nao ha evidencia solida de um preco de mercado real.
    lista = [obs(22.0), obs(60.0)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=13.93, segmento_brick="GEN")
    assert r.cluster_acima_brick is False


def test_cluster_acima_brick_nao_atua_com_menos_que_n_minimo():
    lista = [obs(22.99)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=13.93, segmento_brick="GEN")
    assert r.cluster_acima_brick is False


def test_sanidade_ratio_brick_web_no_banco_real():
    caminho_db = Path(__file__).parent.parent / "precificador.db"
    conn = sqlite3.connect(caminho_db)
    razoes = []
    for ean, vum in conn.execute("SELECT ean, vum FROM preco_brick"):
        precos = [
            preco for (preco,) in conn.execute(
                "SELECT preco FROM preco_concorrente WHERE ean = ? AND status = 'OK' AND preco IS NOT NULL",
                (ean,),
            )
        ]
        if len(precos) >= 3:
            razoes.append(vum / median(precos))
    conn.close()

    assert razoes, "esperava encontrar EANs com Brick e >=3 precos web no banco"
    mediana_razao = median(razoes)
    assert 0.80 <= mediana_razao <= 1.00, f"razao Brick/mediana_web fora da faixa esperada: {mediana_razao}"


# --- Testes novos: fator canal e mediana geografica (2026-08-08) ---





def test_mediana_geografica_ponderada():
    """Tres sites com pesos diferentes: media ponderada das medianas."""
    params = dict(PARAMS)
    params["mercado"] = dict(PARAMS["mercado"])
    params["mercado"]["peso_geografico"] = {
        "ativo": True, "raia": 4.0, "nissei": 1.0, "saojoao": 1.0,
    }
    # 3 observacoes da Raia (mediana = 22.0), 2 da Nissei (mediana = 15.0),
    # 1 do SaoJoao (mediana = 30.0)
    lista = [
        obs(20.0, site="raia"), obs(22.0, site="raia"), obs(25.0, site="raia"),
        obs(14.0, site="nissei"), obs(16.0, site="nissei"),
        obs(30.0, site="saojoao"),
    ]
    # media ponderada: (22.0*4 + 15.0*1 + 30.0*1) / 6 = 133/6 ≈ 22.17
    resultado = mercado._mediana_geografica(lista, params)
    assert resultado == pytest.approx((22.0 * 4 + 15.0 * 1 + 30.0 * 1) / 6)


def test_mediana_geografica_site_com_apelido():
    """farmasp e saopaulo agrupados como mesma loja antes da mediana."""
    params = dict(PARAMS)
    params["mercado"] = dict(PARAMS["mercado"])
    params["mercado"]["peso_geografico"] = {
        "ativo": True, "farmasp": 3.5, "nissei": 1.0, "raia": 1.0,
    }
    apelidos = {"saopaulo": "farmasp"}
    # farmasp (3 obs) + saopaulo (2 obs) = mesma loja: [20,22,24,21,23] mediana=22
    # nissei: [10] mediana=10
    # raia: [12] mediana=12
    lista = [
        obs(20.0, site="farmasp"), obs(22.0, site="farmasp"), obs(24.0, site="farmasp"),
        obs(21.0, site="saopaulo"), obs(23.0, site="saopaulo"),
        obs(10.0, site="nissei"),
        obs(12.0, site="raia"),
    ]
    # media: (22*3.5 + 10*1.0 + 12*1.0) / 5.5 = 99/5.5 = 18.0
    resultado = mercado._mediana_geografica(lista, params, apelidos)
    assert resultado == pytest.approx((22 * 3.5 + 10 * 1.0 + 12 * 1.0) / 5.5)


def test_mediana_geografica_inativa_cai_na_mediana_simples():
    """Com ativo=false, devolve mediana simples (comportamento antigo)."""
    params = dict(PARAMS)
    params["mercado"] = dict(PARAMS["mercado"])
    params["mercado"]["peso_geografico"] = {"ativo": False, "raia": 4.0, "nissei": 1.0}
    lista = [obs(10.0, site="raia"), obs(20.0, site="nissei"), obs(30.0, site="raia")]
    resultado = mercado._mediana_geografica(lista, params)
    assert resultado == median([10.0, 20.0, 30.0])  # mediana simples


def test_mediana_geografica_poucos_sites_cai_na_mediana_simples():
    """Com menos de 3 sites distintos, cai na mediana simples."""
    params = dict(PARAMS)
    params["mercado"] = dict(PARAMS["mercado"])
    params["mercado"]["peso_geografico"] = {"ativo": True, "raia": 4.0, "nissei": 1.0}
    # So 2 sites distintos: raia e nissei
    lista = [obs(10.0, site="raia"), obs(20.0, site="nissei"), obs(15.0, site="raia")]
    resultado = mercado._mediana_geografica(lista, params)
    assert resultado == median([10.0, 15.0, 20.0])  # mediana simples




# --- Ancora competitiva e premio de balcao (2026-08-10) ---

def test_ancora_competitiva_exclui_site_com_gap_online_balcao():
    """Nissei nao define o piso competitivo: o preco online dela diverge do
    balcao (teste presencial 2026-08-10) e a coleta so ve o site."""
    params = _params_ancora(excluir=["nissei"], gap=0.0)
    lista = [obs(18.0, site="nissei"), obs(25.0, site="drogaraia"), obs(26.0, site="farmasp")]
    menor, maior, motivo = mercado.ancora_competitiva_local(lista, params)
    assert menor == 25.0        # 18,00 da Nissei nao ancora o piso
    assert maior == 26.0
    assert "nissei" in motivo


def test_ancora_competitiva_nunca_fica_sem_ancora():
    """Se a exclusao esvaziar o conjunto, volta a usar todos -- ficar sem
    ancora seria pior que usar uma imperfeita."""
    params = _params_ancora(excluir=["nissei"], gap=0.0)
    lista = [obs(18.0, site="nissei")]
    menor, maior, motivo = mercado.ancora_competitiva_local(lista, params)
    assert menor == 18.0 and maior == 18.0
    assert motivo == ""


def test_ancora_competitiva_winsoriza_preco_isca():
    """Menor local 30% abaixo do 2o menor e' tratado como preco-isca."""
    params = _params_ancora(excluir=[], gap=0.15)
    lista = [obs(14.0, site="a"), obs(20.0, site="b"), obs(21.0, site="c")]
    menor, _, motivo = mercado.ancora_competitiva_local(lista, params)
    assert menor == 20.0
    assert "isca" in motivo


def test_ancora_competitiva_nao_winsoriza_gap_pequeno():
    """Gap dentro da tolerancia mantem o menor preco como ancora."""
    params = _params_ancora(excluir=[], gap=0.15)
    lista = [obs(19.0, site="a"), obs(20.0, site="b"), obs(21.0, site="c")]
    menor, _, motivo = mercado.ancora_competitiva_local(lista, params)
    assert menor == 19.0
    assert motivo == ""


def test_premio_balcao_aplicado_uma_vez_no_fim():
    """O premio de canal multiplica a referencia consolidada, nao as observacoes."""
    lista = [obs(20.0), obs(21.0), obs(19.5)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=None,
                                 natureza_fiscal_item="medicamento")
    premio = PARAMS["mercado"]["premio_balcao"]["medicamento"]
    assert r.valor_referencia == pytest.approx(median([20.0, 21.0, 19.5]) * premio)
    # A mediana bruta permanece na escala ONLINE observada
    assert r.mediana == pytest.approx(median([20.0, 21.0, 19.5]))


def _params_ancora(excluir, gap):
    params = dict(PARAMS)
    params["mercado"] = dict(PARAMS["mercado"])
    params["mercado"]["ancora_competitiva"] = {
        "ativo": True, "excluir_sites": excluir, "gap_maximo_pct": gap,
    }
    return params
