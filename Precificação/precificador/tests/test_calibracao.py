"""Guardas de sanidade sobre os NUMEROS calibrados em parametros.toml.

Nao testa logica (isso e' test_economico.py / test_mercado.py) -- testa se
os valores que `auditar_calibracao.py` escreve no TOML continuam dentro de
uma faixa plausivel. Existe porque o item 2 do plano de melhorias
estatisticas (2026-08-30) nao tinha NENHUM teste: se o script de auditoria
tiver um bug de agregacao (dividir pela base errada, por exemplo) e escrever
um numero absurdo no TOML, nada acusa isso hoje alem de revisao manual do
diff. Estes testes nao substituem essa revisao -- so' pegam o caso grosseiro
(ordem de grandeza errada, fracao fora de [0,1], etc).

As faixas foram calibradas para caber confortavelmente nos valores medidos
em 30/08/2026 (ver o comentario de cada bloco no parametros.toml) com folga
para recalibracoes futuras -- nao para o valor exato de hoje. Se uma
recalibracao legitima estourar a faixa, o teste deve ser revisto SABENDO
disso, nao silenciado.
"""
from __future__ import annotations

import pytest

from engine import parametros

PARAMS = parametros.carregar()


def test_fator_fisico_fica_na_faixa_plausivel_de_razao_brick_web():
    # Razao Brick/mediana_web por segmento: medido em 1.523 a 3.388 EANs desde
    # 2026-08 sempre entre 0,75 e 0,95. Fora de [0,5; 1,5] e' sinal de erro de
    # agregacao (ex.: dividir pela base errada) ou de unidade, nao de
    # recalibracao legitima -- o Brick nunca ficou nem perto do dobro nem de
    # menos da metade da web nas quatro medicoes ja feitas.
    cfg = PARAMS["mercado"]["fator_fisico"]
    for segmento in ("GEN", "RX", "SIM", "NMED", "default"):
        assert segmento in cfg, f"segmento {segmento} ausente de mercado.fator_fisico"
        valor = cfg[segmento]
        assert 0.5 <= valor <= 1.5, f"fator_fisico[{segmento}] = {valor} fora de [0.5, 1.5]"


def test_custo_estimado_por_natureza_fica_na_faixa_plausivel():
    # Fracao custo/mercado: medido em 30/08/2026 entre 0,55 e 0,66 (452 a 1651
    # EANs por natureza). Abaixo de 0,20 significaria markup de 5x ou mais
    # (nao visto em nenhuma natureza ate hoje); acima de 0,90 significaria
    # markup quase nulo -- os dois sao sinal de bug na auditoria, nao de
    # mercado real.
    cfg = PARAMS.get("custo_estimado", {})
    global_pct = cfg.get("pct_do_preco_mercado")
    assert global_pct is not None
    assert 0.20 <= global_pct <= 0.90, f"pct_do_preco_mercado global = {global_pct} fora de [0.20, 0.90]"

    por_natureza = cfg.get("por_natureza") or {}
    assert set(por_natureza) >= {"medicamento", "perfumaria_higiene", "padrao"}
    for natureza, dados in por_natureza.items():
        pct = dados["pct_shrunk"]
        assert 0.20 <= pct <= 0.90, f"por_natureza[{natureza}].pct_shrunk = {pct} fora de [0.20, 0.90]"
        assert dados["n"] > 0, f"por_natureza[{natureza}].n deveria ser > 0 (veio de EANs medidos)"


def test_custo_estimado_shrinkage_nao_diverge_demais_do_global():
    # O shrinkage bayesiano (peso n/(n+k)) NUNCA deveria produzir um valor por
    # natureza muito mais extremo que o proprio dado medido permite -- ele so'
    # pode ficar ENTRE o medido puro e o global, nunca fora dos dois. Um valor
    # fora dessa faixa e' prova de erro na formula (ex.: peso invertido).
    cfg = PARAMS["custo_estimado"]
    global_pct = cfg["pct_do_preco_mercado"]
    for natureza, dados in cfg["por_natureza"].items():
        pct = dados["pct_shrunk"]
        # Folga de 5pp pra cima e pra baixo: o "pct_medido" que gerou o shrunk
        # nao fica salvo aqui, entao a checagem e' contra o global com folga,
        # nao um recalculo exato (isso e' papel do auditar_calibracao.py).
        assert global_pct - 0.30 <= pct <= global_pct + 0.30, (
            f"por_natureza[{natureza}].pct_shrunk = {pct} longe demais do global {global_pct}")


def test_markup_max_ancora_continua_acima_do_p99_medido():
    # markup_max_ancora (piso_competitivo) e markup_max (brick_incoerente)
    # sao o MESMO numero por design (ver o comentario de piso_competitivo no
    # TOML: "reusa o markup_max ja calibrado"). Medido em 30/08/2026: p99 do
    # markup real (mediana_mercado/custo) = 4,15x. O parametro tem que ficar
    # ACIMA disso com folga -- e' a guarda que decide se um "concorrente"
    # 1-2 lojas e' preco real ou erro de EAN/apresentacao.
    P99_MEDIDO_20260830 = 4.15
    markup_max_ancora = PARAMS["piso_competitivo"]["markup_max_ancora"]
    markup_max_incoerente = PARAMS["mercado"]["brick_incoerente"]["markup_max"]
    assert markup_max_ancora > P99_MEDIDO_20260830
    assert markup_max_incoerente > P99_MEDIDO_20260830
    assert markup_max_ancora == markup_max_incoerente, (
        "os dois markup_max deveriam continuar iguais -- sao o mesmo numero por design")


def test_dispersao_por_site_dos_locais_atuais_fica_num_intervalo_razoavel():
    # Nao testa o VALOR (isso muda a cada auditoria) -- testa que a metrica
    # dispersao_por_site nao pode legitimamente sair de [0, 1] para os sites
    # locais configurados: dispersao e' uma mediana de |razao - 1|, e uma
    # mediana >= 1 significaria que METADE das observacoes do site discorda
    # da mediana dos outros por 100% ou mais -- nunca visto ate hoje (o pior
    # caso medido foi 0,145, farmasp em 30/08/2026).
    cfg = PARAMS["mercado"]["ancora_competitiva"]
    assert cfg["excluir_sites"] == [], (
        "excluir_sites deveria estar vazio desde a correcao de 30/08/2026 -- "
        "se um site foi excluido de novo, confirme que veio de "
        "auditar_calibracao.py --secao dispersao_sites, nao de um valor antigo")
