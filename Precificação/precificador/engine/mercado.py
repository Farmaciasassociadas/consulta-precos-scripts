"""Motor de mercado: exclusao de outliers (4 camadas) + blend Brick/web.

Todas as funcoes sao puras: recebem dados e parametros, devolvem resultado.
Nenhuma leitura de arquivo ou banco acontece aqui (ver PLANO_SISTEMA_PRECIFICACAO.md
Parte 3.1 e 3.2 para a motivacao de cada regra).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from statistics import median
from typing import Any

PALAVRAS_PROMOCIONAIS = (
    "clube", "assinante", "assinatura", "leve mais", "leve ", "desconto",
)
# "promoção: de R$ X por R$ Y" (sem "leve"/"clube"/"assinante") e o formato padrao
# de exibicao do preco de venda normal em quase todo site -- NAO e clube/assinatura
# nem leve-mais, entao nao distorce o preco unitario e deve ser mantido como
# preco de venda real (caso BUPROVIL 600mg C/20, 2026-08-04: 7.215 observacoes no
# banco eram descartadas so por conter "promo", mascarando o preco de concorrencia).


@dataclass(frozen=True)
class Observacao:
    site: str
    preco: float | None
    status: str
    data_hora: date | None
    observacoes: str | None = None


@dataclass(frozen=True)
class Descarte:
    observacao: Observacao
    camada: str
    motivo: str


@dataclass(frozen=True)
class ResultadoFiltro:
    mantidas: tuple[Observacao, ...]
    descartadas: tuple[Descarte, ...]


@dataclass(frozen=True)
class ResultadoMercado:
    mediana: float | None
    n: int
    cv: float | None
    confianca: str
    peso_brick: float
    valor_referencia: float | None
    divergencia_brick_web: bool
    filtro: ResultadoFiltro
    cluster_acima_brick: bool = False


def parse_data_hora(valor: str | None) -> date | None:
    if not valor:
        return None
    try:
        return datetime.strptime(valor.strip(), "%d/%m/%Y %H:%M:%S").date()
    except ValueError:
        return None


def _e_promocional(observacoes: str | None) -> bool:
    if not observacoes:
        return False
    texto = observacoes.lower()
    return any(palavra in texto for palavra in PALAVRAS_PROMOCIONAIS)


def _camada_1_natureza(obs: list[Observacao]) -> tuple[list[Observacao], list[Descarte]]:
    mantidas, descartadas = [], []
    for o in obs:
        if o.status != "OK" or o.preco is None or o.preco <= 0:
            descartadas.append(Descarte(o, "natureza", f"status={o.status!r} sem preco valido"))
        elif _e_promocional(o.observacoes):
            descartadas.append(Descarte(o, "natureza", "observacoes indicam clube/promocao/assinatura"))
        else:
            mantidas.append(o)
    return mantidas, descartadas


def _camada_2_frescor(
    obs: list[Observacao], data_referencia: date, dias_max: int
) -> tuple[list[Observacao], list[Descarte]]:
    mantidas, descartadas = [], []
    for o in obs:
        if o.data_hora is None:
            mantidas.append(o)  # sem data conhecida: nao penaliza, so a camada de frescor nao se aplica
            continue
        idade = (data_referencia - o.data_hora).days
        if idade > dias_max:
            descartadas.append(Descarte(o, "frescor", f"observacao com {idade} dias (limite {dias_max})"))
        else:
            mantidas.append(o)
    return mantidas, descartadas


def _camada_3_ancora(
    obs: list[Observacao], ancora: float | None, banda_min: float, banda_max: float
) -> tuple[list[Observacao], list[Descarte]]:
    if ancora is None or ancora <= 0 or not obs:
        return obs, []
    piso, teto = ancora * banda_min, ancora * banda_max
    mantidas, descartadas = [], []
    for o in obs:
        if o.preco < piso or o.preco > teto:
            descartadas.append(Descarte(o, "ancora", f"preco {o.preco} fora de [{piso:.2f}; {teto:.2f}] da ancora {ancora:.2f}"))
        else:
            mantidas.append(o)
    return mantidas, descartadas


def _camada_4_mad(
    obs: list[Observacao], n_min: int, multiplicador: float
) -> tuple[list[Observacao], list[Descarte]]:
    if len(obs) < n_min:
        return obs, []
    precos = [o.preco for o in obs]
    med = median(precos)
    mad = 1.4826 * median(abs(p - med) for p in precos)
    if mad == 0:
        return obs, []
    limite = multiplicador * mad
    mantidas, descartadas = [], []
    for o in obs:
        if abs(o.preco - med) > limite:
            descartadas.append(Descarte(o, "mad", f"preco {o.preco} a {abs(o.preco - med):.2f} da mediana (limite {limite:.2f})"))
        else:
            mantidas.append(o)
    return mantidas, descartadas


def filtrar_outliers(
    observacoes: list[Observacao],
    params: dict[str, Any],
    data_referencia: date,
    ancora: float | None = None,
) -> ResultadoFiltro:
    cfg = params["mercado"]["outliers"]
    descartadas: list[Descarte] = []

    atual, novas = _camada_1_natureza(observacoes)
    descartadas += novas
    atual, novas = _camada_2_frescor(atual, data_referencia, cfg["frescor_dias_max"])
    descartadas += novas
    atual, novas = _camada_3_ancora(atual, ancora, cfg["banda_ancora_min"], cfg["banda_ancora_max"])
    descartadas += novas
    atual, novas = _camada_4_mad(atual, cfg["mad_n_min"], cfg["mad_multiplicador"])
    descartadas += novas

    return ResultadoFiltro(mantidas=tuple(atual), descartadas=tuple(descartadas))


def _cv(precos: list[float]) -> float | None:
    if len(precos) < 2:
        return None
    m = median(precos)
    if m == 0:
        return None
    variancia = sum((p - m) ** 2 for p in precos) / len(precos)
    return (variancia ** 0.5) / m


def _peso_brick(n_web: int, cv: float | None, tem_brick: bool, cfg: dict[str, Any]) -> float:
    if not tem_brick:
        return 0.0
    if n_web == 0:
        return cfg["sem_web"]
    if n_web <= 2:
        return cfg["web_n_ate_2"]
    if n_web <= 4:
        return cfg["web_n_3_a_4"]
    if cv is not None and cv <= cfg["cv_baixo_limite"]:
        return cfg["web_n_5_mais_cv_baixo"]
    if cv is not None and cv > cfg["cv_alto_limite"]:
        return cfg["web_n_5_mais_cv_alto"]
    return (cfg["web_n_5_mais_cv_baixo"] + cfg["web_n_5_mais_cv_alto"]) / 2


def calcular_mercado(
    observacoes: list[Observacao],
    params: dict[str, Any],
    data_referencia: date,
    vum_brick: float | None = None,
    segmento_brick: str | None = None,
) -> ResultadoMercado:
    """Calcula a referencia de mercado de um EAN, combinando web filtrada e Brick.

    `vum_brick` e o preco de mercado (Brick) ja em R$; `segmento_brick` seleciona
    o fator fisico por categoria (RX/GEN/SIM/NMED) para converter a mediana web
    em estimativa de loja fisica antes do blend.
    """
    cfg = params["mercado"]["outliers"]
    cfg_fator = params["mercado"]["fator_fisico"]
    cfg_brick = params["mercado"]["brick"]
    fator_fisico = cfg_fator.get(segmento_brick or "", cfg_fator["default"])
    mercado_brick = vum_brick * (1 + cfg_brick["spread_etiqueta"]) if vum_brick else None

    # Camadas 1-2 primeiro (natureza + frescor), sem depender do Brick.
    descartadas: list[Descarte] = []
    pre_ancora, novas = _camada_1_natureza(observacoes)
    descartadas += novas
    pre_ancora, novas = _camada_2_frescor(pre_ancora, data_referencia, cfg["frescor_dias_max"])
    descartadas += novas

    # Divergencia Brick x web e calculada ANTES da camada de ancora: se a camada de
    # ancora rodasse primeiro, ela apagaria justamente os pontos que provam a
    # divergencia (o Brick e a propria ancora do filtro), mascarando o problema.
    precos_pre_ancora = [o.preco for o in pre_ancora]
    mediana_pre_ancora = median(precos_pre_ancora) if precos_pre_ancora else None
    mercado_web_pre_ancora = mediana_pre_ancora * fator_fisico if mediana_pre_ancora is not None else None
    divergencia = False
    if mercado_brick is not None and mercado_web_pre_ancora is not None and mercado_brick > 0:
        divergencia = abs(mercado_web_pre_ancora / mercado_brick - 1) > cfg_brick["divergencia_brick_web_limite"]

    # Camadas 3-4 (ancora + MAD) para chegar na mediana final usada no blend.
    atual, novas = _camada_3_ancora(pre_ancora, vum_brick, cfg["banda_ancora_min"], cfg["banda_ancora_max"])
    descartadas_ancora = novas
    descartadas += novas
    atual, novas = _camada_4_mad(atual, cfg["mad_n_min"], cfg["mad_multiplicador"])
    descartadas += novas
    filtro = ResultadoFiltro(mantidas=tuple(atual), descartadas=tuple(descartadas))

    precos = [o.preco for o in filtro.mantidas]
    n = len(precos)
    mediana_bruta = median(precos) if precos else None
    cv = _cv(precos)
    mercado_web = mediana_bruta * fator_fisico if mediana_bruta is not None else None

    peso = _peso_brick(n, cv, mercado_brick is not None, params["mercado"]["peso_brick"])

    # Cluster consistente de concorrentes ACIMA da banda do Brick: a camada de
    # ancora existe para descartar ruido/erro de apresentacao, nao para jogar
    # fora um preco de mercado real so porque o Brick esta desatualizado/baixo.
    # Se os proprios preços descartados por estarem acima do teto da banda
    # formam um cluster apertado (baixa dispersao, n minimo), confiamos nesse
    # cluster como piso do valor de referencia em vez de colar no Brick puro
    # (evita deixar dinheiro na mesa quando o concorrente sustenta preco maior).
    cluster_acima = False
    cfg_cluster = params["mercado"].get("cluster_acima_brick")
    if cfg_cluster and vum_brick and mercado_brick:
        teto_banda = vum_brick * cfg["banda_ancora_max"]
        precos_acima = [
            d.observacao.preco for d in descartadas_ancora
            if d.camada == "ancora" and d.observacao.preco > teto_banda
        ]
        if len(precos_acima) >= cfg_cluster["n_min"]:
            cv_cluster = _cv(precos_acima)
            if cv_cluster is not None and cv_cluster <= cfg_cluster["cv_max"]:
                mediana_cluster = median(precos_acima)
                referencia_cluster = mediana_cluster * fator_fisico
                if referencia_cluster > (mercado_web if mercado_web is not None else mercado_brick):
                    cluster_acima = True
                    mercado_web = referencia_cluster
                    peso = cfg_cluster["peso_brick"]

    if mercado_brick is not None and mercado_web is not None:
        valor_referencia = peso * mercado_brick + (1 - peso) * mercado_web
    elif mercado_brick is not None:
        valor_referencia = mercado_brick
    else:
        valor_referencia = mercado_web

    if n >= 3:
        confianca = "ALTA"
    elif n >= 1 or mercado_brick is not None:
        confianca = "MEDIA"
    else:
        confianca = "BAIXA"

    return ResultadoMercado(
        mediana=mediana_bruta,
        n=n,
        cv=cv,
        confianca=confianca,
        peso_brick=peso,
        valor_referencia=valor_referencia,
        divergencia_brick_web=divergencia,
        filtro=filtro,
        cluster_acima_brick=cluster_acima,
    )
