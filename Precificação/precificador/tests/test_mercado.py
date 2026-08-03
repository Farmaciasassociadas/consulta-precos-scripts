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
    assert r.valor_referencia == 25.0 * (1 + PARAMS["mercado"]["brick"]["spread_etiqueta"])
    assert r.confianca == "MEDIA"


def test_sem_brick_usa_so_web():
    lista = [obs(20.0), obs(21.0), obs(19.5)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=None)
    assert r.peso_brick == 0.0
    fator = PARAMS["mercado"]["fator_fisico"]["default"]
    assert r.valor_referencia == median([20.0, 21.0, 19.5]) * fator


def test_divergencia_brick_web_e_sinalizada():
    # web muito acima do Brick (ex.: EAN com apresentacao trocada)
    lista = [obs(50.0), obs(52.0), obs(48.0)]
    r = mercado.calcular_mercado(lista, PARAMS, HOJE, vum_brick=20.0, segmento_brick="GEN")
    assert r.divergencia_brick_web is True


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
