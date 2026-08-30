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
    # 4 observacoes, uma bem discrepante: o MAD nao age (n=4 < mad_n_min=5).
    #
    # ATE 2026-08-10 este teste afirmava que as 4 sobreviviam -- documentando
    # como esperado justamente o vao que deixava 315 EANs sem protecao alguma.
    # Agora a camada 4b (razao) cobre esse intervalo, entao o 40,00 cai. O que
    # este teste garante e' o ESCOPO do MAD: quem descartou nao foi ele.
    lista = [obs(10.0), obs(10.5), obs(11.0), obs(40.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert all(d.camada != "mad" for d in r.descartadas)
    assert [d.camada for d in r.descartadas] == ["razao"]


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


def test_pmpf_desempata_e_desliga_a_bandeira_de_divergencia():
    # Mesmo caso do teste acima, agora com a terceira testemunha. O PMPF em 50
    # confirma a web: o desacordo esta explicado (o Brick e' que esta fora) e as
    # camadas 3-4 ja usam o PMPF como ancora -- nao ha o que conferir na mao.
    lista = [obs(50.0), obs(52.0), obs(48.0)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=20.0,
                                 segmento_brick="GEN", pmpf=50.0)
    assert r.divergencia_brick_web is False


def test_pmpf_longe_dos_dois_mantem_a_bandeira():
    # Terceira testemunha que discorda dos DOIS lados nao explica nada: a
    # bandeira continua de pe, que e' exatamente a fila que sobra para o humano.
    lista = [obs(50.0), obs(52.0), obs(48.0)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=20.0,
                                 segmento_brick="GEN", pmpf=120.0)
    assert r.divergencia_brick_web is True


def test_brick_de_caixa_descartado_com_uma_unica_web_coerente_com_o_custo():
    # LACTA BOMBOM OURO BRANCO (12/08/2026): custo 1,06, UMA web a 2,99, Brick
    # 120,02 (preco do display). Com n_min_web=2 a guarda nao disparava e o
    # sugerido saia a R$ 139,99. O custo e' o segundo testemunho.
    r = mercado.calcular_mercado([obs(2.99)], PARAMS, HOJE, vum_brick=120.02,
                                 segmento_brick="NMED", custo=1.06)
    assert r.mediana is not None and r.mediana < 10.0


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
    # O PISO volta a usar todos; o TETO nao sai com uma loja so -- o maximo de
    # uma amostra pequena subestima o maximo real e viraria trava dura.
    assert menor == 18.0 and maior is None
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


# --- Camada 4b: rede de seguranca para n pequeno sem ancora (2026-08-10) ---

def test_camada_4b_descarta_outlier_grosseiro_sem_ancora():
    """Caso real medido: [7.49, 9.29, 24.60] sem Brick. O 24,60 e' 3,0x a
    mediana dos demais e entrava inteiro na mediana que define o alvo."""
    lista = [obs(7.49), obs(9.29), obs(24.60)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=None)
    assert sorted(o.preco for o in r.mantidas) == [7.49, 9.29]
    assert [d.camada for d in r.descartadas] == ["razao"]


def test_camada_4b_nao_age_quando_ha_ancora():
    """Com Brick, a camada 3 ja protege -- 4b nao deve rodar em cima dela."""
    lista = [obs(7.49), obs(9.29), obs(24.60)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=9.0)
    assert all(d.camada != "razao" for d in r.descartadas)


def test_camada_4b_nao_age_com_n_grande():
    """A partir de mad_n_min a camada 4 (MAD) assume; 4b sai de cena."""
    lista = [obs(10.0), obs(10.5), obs(11.0), obs(10.2), obs(30.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=None)
    assert all(d.camada != "razao" for d in r.descartadas)


def test_camada_4b_preserva_dispersao_comercial_legitima():
    """Spread de 1,6x entre farmacias e' diferenca de preco real, nao erro."""
    lista = [obs(10.0), obs(13.0), obs(16.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=None)
    assert len(r.mantidas) == 3
    assert r.descartadas == ()


def test_camada_4b_nunca_esvazia_o_conjunto():
    """Se todo mundo diverge de todo mundo, nao ha maioria em que confiar --
    devolve tudo em vez de zerar a referencia de mercado."""
    lista = [obs(1.0), obs(100.0)]
    mantidas, descartadas = mercado._camada_4b_razao(lista, 2, 4, 2.5)
    assert len(mantidas) == 2
    assert descartadas == []


def test_camada_4b_pega_outlier_para_baixo():
    """A protecao vale nos dois sentidos (1/razao_max)."""
    lista = [obs(2.0), obs(20.0), obs(22.0)]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE, ancora=None)
    assert sorted(o.preco for o in r.mantidas) == [20.0, 22.0]


# --- PMPF-PR como terceira ancora (Fase 2) ---

def test_normalizar_pmpf_divide_pelo_multiplo():
    # "AAS 100mg - 20 x 10 comprimidos", multiplo 20, PMPF 51,80 = caixa
    assert mercado.normalizar_pmpf(51.80, 20) == pytest.approx(2.59)
    assert mercado.normalizar_pmpf(26.38, 1) == pytest.approx(26.38)
    assert mercado.normalizar_pmpf(26.38, None) == pytest.approx(26.38)
    assert mercado.normalizar_pmpf(None, 20) is None
    assert mercado.normalizar_pmpf(0, 20) is None


def test_pmpf_entra_na_referencia_e_nao_leva_premio_de_balcao():
    """O PMPF ja e preco de balcao (NFC-e ao consumidor): aplicar o premio
    sobre ele converteria balcao em balcao de novo."""
    amostra = [obs(20.0, site="farmasp"), obs(20.0, site="saojoao"), obs(20.0, site="drogaraia")]
    sem = mercado.calcular_mercado(amostra, PARAMS, HOJE, natureza_fiscal_item="medicamento")
    com = mercado.calcular_mercado(amostra, PARAMS, HOJE, natureza_fiscal_item="medicamento",
                                   pmpf=20.0, pmpf_multiplo=1)
    premio = PARAMS["mercado"]["premio_balcao"]["medicamento"]
    peso = PARAMS["mercado"]["pmpf"]["com_vizinhanca_local"]
    assert sem.valor_referencia == pytest.approx(20.0 * premio)
    # so a parcela nao-PMPF leva o premio
    assert com.valor_referencia == pytest.approx(peso * 20.0 + (1 - peso) * 20.0 * premio)
    assert com.pmpf == pytest.approx(20.0)
    assert com.peso_pmpf == pytest.approx(peso)


def test_pmpf_sem_web_vira_quase_toda_a_referencia():
    r = mercado.calcular_mercado([], PARAMS, HOJE, natureza_fiscal_item="medicamento",
                                 pmpf=30.0, pmpf_multiplo=1)
    assert r.valor_referencia == pytest.approx(30.0)
    assert r.peso_pmpf == pytest.approx(1.0)


def test_pmpf_tem_prioridade_como_ancora_sobre_o_brick():
    """Brick em 10 (escala nacional) e PMPF em 30 (escala local). Um preco
    local de 28 sobrevive com o PMPF de ancora e morreria com o Brick."""
    amostra = [obs(28.0, site="farmasp"), obs(29.0, site="saojoao"), obs(30.0, site="drogaraia")]
    r = mercado.calcular_mercado(amostra, PARAMS, HOJE, vum_brick=10.0, segmento_brick="GEN",
                                 natureza_fiscal_item="medicamento", custo=15.0,
                                 pmpf=30.0, pmpf_multiplo=1)
    assert r.n == 3, "a banda ancorada no PMPF nao pode apagar os precos locais"


# --- Ancora competitiva com 1-2 lojas (causa dos 73 itens) ---

def test_observacoes_locais_saem_mesmo_sem_atingir_n_min_local():
    amostra = [obs(20.0, site="farmasp"), obs(15.0, site="panvel"), obs(16.0, site="paguemenos")]
    r = mercado.calcular_mercado(amostra, PARAMS, HOJE)
    assert r.alvo_so_local is False, "1 loja local nao define o alvo"
    assert len(r.observacoes_locais) == 1, "mas o local observado ancora piso/teto"
    menor, maior, _ = mercado.ancora_competitiva_local(list(r.observacoes_locais), PARAMS)
    assert menor == pytest.approx(20.0), "1 loja local ja ancora o PISO"
    assert maior is None, "mas nao o TETO: o maximo de 1 observacao nao e' o maximo da praca"


def test_teto_competitivo_so_sai_com_tres_lojas():
    amostra = [obs(20.0, site="farmasp"), obs(22.0, site="saojoao"), obs(25.0, site="drogaraia")]
    menor, maior, _ = mercado.ancora_competitiva_local(amostra, PARAMS)
    assert menor == pytest.approx(20.0) and maior == pytest.approx(25.0)


def test_ancora_competitiva_respeita_n_min_lojas():
    import copy
    p = copy.deepcopy(PARAMS)
    p["mercado"]["ancora_competitiva"]["n_min_lojas"] = 2
    amostra = [obs(20.0, site="farmasp")]
    assert mercado.ancora_competitiva_local(amostra, p) == (None, None, "")


def test_cluster_volta_a_agir_sob_pmpf_com_tres_lojas():
    """PROFENID 100mg INJ (12/08/2026): PMPF R$ 7,65 contra oito lojas entre
    R$ 30,92 e R$ 43,49. A banda do PMPF apagava as oito e a sugestao saia a
    R$ 7,79 -- 20% do mercado. Tres lojas independentes ja bastam para o
    cluster devolver o mercado real."""
    lista = [obs(36.99, site="saopaulo"), obs(38.99, site="saojoao"),
             obs(38.44, site="precopopular"), obs(43.29, site="paguemenos")]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=None, pmpf=7.65)
    assert r.cluster_acima_brick is True
    assert r.mediana is not None and r.mediana > 30.0


def test_cluster_sob_pmpf_nao_age_com_duas_lojas():
    """DORALGINA C/4: com duas fontes so, devolver preco que o PMPF rejeitou e'
    exatamente o erro de apresentacao que a banda existe para pegar."""
    lista = [obs(60.0, site="drogaraia"), obs(62.0, site="paguemenos")]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=None, pmpf=5.72)
    assert r.cluster_acima_brick is False


# ── dispersao_por_site (item 3 do plano de melhorias estatisticas, 2026-08-30) ──

LOCAIS = {"farmasp", "saojoao", "drogaraia", "nissei"}


def test_dispersao_por_site_mede_desvio_da_mediana_dos_outros_locais():
    # site "instavel" ora acima ora abaixo dos outros dois locais; os outros
    # dois concordam sempre entre si (dispersao ~0).
    por_ean = {
        "ean1": [obs(10.0, site="farmasp"), obs(10.0, site="saojoao"), obs(15.0, site="nissei")],
        "ean2": [obs(20.0, site="farmasp"), obs(20.0, site="saojoao"), obs(14.0, site="nissei")],
        "ean3": [obs(30.0, site="farmasp"), obs(30.0, site="saojoao"), obs(30.0, site="nissei")],
        "ean4": [obs(8.0, site="farmasp"), obs(8.0, site="saojoao"), obs(8.5, site="nissei")],
        "ean5": [obs(12.0, site="farmasp"), obs(12.0, site="saojoao"), obs(12.1, site="nissei")],
    }
    resultado = mercado.dispersao_por_site(por_ean, LOCAIS, n_min_pares=5)
    # farmasp e saojoao sempre concordam ENTRE SI; o desvio residual que sobra
    # vem so' de nissei entrar na mediana "dos outros" -- por isso os dois
    # ficam iguais entre si e bem abaixo do site que realmente diverge.
    assert resultado["farmasp"]["dispersao"] == pytest.approx(resultado["saojoao"]["dispersao"])
    assert resultado["nissei"]["dispersao"] > resultado["farmasp"]["dispersao"]


def test_dispersao_por_site_ignora_ean_com_menos_de_tres_locais():
    por_ean = {"ean1": [obs(10.0, site="farmasp"), obs(50.0, site="saojoao")]}
    resultado = mercado.dispersao_por_site(por_ean, LOCAIS, n_min_pares=1)
    assert resultado == {}


def test_dispersao_por_site_exige_n_min_pares():
    por_ean = {
        "ean1": [obs(10.0, site="farmasp"), obs(10.0, site="saojoao"), obs(20.0, site="nissei")],
    }
    resultado = mercado.dispersao_por_site(por_ean, LOCAIS, n_min_pares=5)
    assert resultado == {}  # so' 1 par por site, abaixo do minimo


def test_dispersao_por_site_aplica_apelido_antes_de_agrupar():
    # "saopaulo" e' o nome antigo de "farmasp" -- sem o apelido, as duas
    # entrariam como sites distintos e o agrupamento por EAN quebraria.
    por_ean = {
        f"ean{i}": [obs(10.0, site="saopaulo"), obs(10.0, site="saojoao"), obs(10.0 + i, site="nissei")]
        for i in range(1, 6)
    }
    resultado = mercado.dispersao_por_site(
        por_ean, {"saopaulo", "saojoao", "nissei"}, apelidos_site={"saopaulo": "farmasp"}, n_min_pares=5)
    assert "farmasp" in resultado
    assert "saopaulo" not in resultado
    assert resultado["farmasp"]["n"] == 5


# ── hampel_por_serie_temporal (item 5 do plano de melhorias estatisticas, 2026-08-30) ──

def _serie(precos, site="nissei"):
    return [obs(p, site=site, dias_atras=len(precos) - i) for i, p in enumerate(precos)]


def test_hampel_marca_queda_pontual_na_propria_serie():
    # 8 pontos estaveis em ~10 e um unico ponto caindo pra 4 -- nenhum outro
    # site precisa mudar para isto ser pego (diferente da camada 4, cross-site).
    serie = _serie([10.0, 10.1, 9.9, 10.0, 4.0, 10.2, 9.8, 10.0])
    mantidas, descartadas = mercado.hampel_por_serie_temporal(serie, n_min=5)
    assert len(descartadas) == 1
    assert descartadas[0].observacao.preco == 4.0
    assert descartadas[0].camada == "hampel_temporal"
    assert len(mantidas) == 7


def test_hampel_nao_marca_serie_estavel():
    serie = _serie([10.0, 10.1, 9.9, 10.0, 10.2, 9.8, 10.0])
    mantidas, descartadas = mercado.hampel_por_serie_temporal(serie, n_min=5)
    assert descartadas == []
    assert len(mantidas) == len(serie)


def test_hampel_nao_age_com_historico_curto():
    serie = _serie([10.0, 4.0, 10.0])  # so' 3 pontos, abaixo do n_min default (5)
    mantidas, descartadas = mercado.hampel_por_serie_temporal(serie)
    assert descartadas == []
    assert len(mantidas) == 3


def test_hampel_preserva_observacoes_sem_preco():
    serie = _serie([10.0, 10.1, 9.9, 10.0, 4.0, 10.2, 9.8])
    sem_preco = mercado.Observacao(site="nissei", preco=None, status="TIMEOUT", data_hora=None)
    mantidas, descartadas = mercado.hampel_por_serie_temporal(serie + [sem_preco], n_min=5)
    assert sem_preco in mantidas
    assert len(descartadas) == 1


# ── suavizar_ewma_temporal (item 4 do plano de melhorias estatisticas, 2026-08-30) ──

def test_ewma_pondera_mais_o_ponto_mais_recente():
    serie = [obs(10.0, dias_atras=20), obs(20.0, dias_atras=0)]
    resultado = mercado.suavizar_ewma_temporal(serie, HOJE, half_life_dias=7.0)
    assert 15.0 < resultado.preco < 20.0


def test_ewma_ponto_unico_devolve_o_proprio_preco():
    serie = [obs(12.34, dias_atras=3)]
    resultado = mercado.suavizar_ewma_temporal(serie, HOJE, half_life_dias=7.0)
    assert resultado.preco == pytest.approx(12.34)


def test_ewma_meia_vida_decai_pela_metade():
    # dois pontos, um exatamente 1 half-life mais velho que o outro: o peso do
    # mais velho e' metade do mais novo.
    serie = [obs(10.0, dias_atras=7), obs(20.0, dias_atras=0)]
    resultado = mercado.suavizar_ewma_temporal(serie, HOJE, half_life_dias=7.0)
    esperado = (10.0 * 0.5 + 20.0 * 1.0) / 1.5
    assert resultado.preco == pytest.approx(esperado, abs=1e-3)


def test_ewma_lista_vazia_ou_so_com_precos_invalidos_devolve_none():
    assert mercado.suavizar_ewma_temporal([], HOJE, half_life_dias=7.0) is None
    invalida = mercado.Observacao(site="nissei", preco=None, status="TIMEOUT", data_hora=HOJE)
    assert mercado.suavizar_ewma_temporal([invalida], HOJE, half_life_dias=7.0) is None


def test_ewma_herda_status_e_data_da_observacao_mais_recente():
    serie = [
        obs(10.0, dias_atras=10, status="OK"),
        obs(30.0, dias_atras=0, status="MARKETPLACE"),
    ]
    resultado = mercado.suavizar_ewma_temporal(serie, HOJE, half_life_dias=7.0)
    assert resultado.status == "MARKETPLACE"
    assert resultado.data_hora == HOJE


def test_ewma_sem_data_hora_pesa_como_se_fosse_hoje():
    serie = [obs(10.0, dias_atras=30), mercado.Observacao(
        site="teste", preco=20.0, status="OK", data_hora=None)]
    resultado = mercado.suavizar_ewma_temporal(serie, HOJE, half_life_dias=7.0)
    # o ponto sem data pesa como "hoje" (peso 1.0), dominando o ponto de 30
    # dias atras (peso quase zero) -- resultado bem mais perto de 20 que de 10.
    assert resultado.preco > 19.0
