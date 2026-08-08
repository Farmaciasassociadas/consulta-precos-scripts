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
    # Vizinhanca: quantos concorrentes LOCAIS sobraram apos as 4 camadas e se o
    # alvo foi calculado so com eles. `n` continua sendo o total (locais +
    # remotos), porque os remotos seguem validando o preco.
    n_local: int = 0
    alvo_so_local: bool = False
    precos_alvo: tuple[float, ...] = ()


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


STATUS_PRECO_VALIDO = ("OK", "MARKETPLACE")
# MARKETPLACE = vendedor terceiro dentro do site da farmácia (ex.: Droga Raia
# marketplace). Decisão 2026-08-05: não descartar mais -- passa a compor o
# preço de referência, só que com peso reduzido (mercado.marketplace.peso,
# default 0.90) na mediana final, porque é um canal menos confiável que o
# preço vendido pela própria farmácia (pode ter ágio ou desconto de vendedor
# independente). Continua sujeito às mesmas camadas de frescor/âncora/MAD.


def _camada_1_natureza(obs: list[Observacao]) -> tuple[list[Observacao], list[Descarte]]:
    mantidas, descartadas = [], []
    for o in obs:
        if o.status not in STATUS_PRECO_VALIDO or o.preco is None or o.preco <= 0:
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


def _peso_observacao(status: str, params: dict[str, Any]) -> float:
    if status == "MARKETPLACE":
        return params["mercado"].get("marketplace", {}).get("peso", 1.0)
    return 1.0


def _mediana_ponderada(observacoes: list[Observacao], params: dict[str, Any]) -> float | None:
    """Mediana da lista de precos, dando peso reduzido a observacoes de
    marketplace (vendedor terceiro). Quando todos os pesos sao iguais
    (nenhuma observacao de marketplace no grupo), cai exatamente na mediana
    padrao (statistics.median) -- sem essa igualdade de pesos, uma lista de
    tamanho par teria a media dos dois centrais; a versao ponderada abaixo
    devolve so um deles, entao so diverge quando ha peso misto de verdade.

    ATENCAO (medido em 2026-08-06): com peso misto e n pequeno esta funcao e
    um DEGRAU, nao uma media. Para [10,12,20,22], descontar uma observacao
    devolve 20 ou 12 conforme QUAL foi descontada -- nunca 16 (a mediana
    simples). Isso esta matematicamente correto para mediana ponderada, mas
    significa que generalizar pesos por site tornaria o preco instavel: um
    site a menos na coleta mudaria a referencia em ~60%. Por isso a
    preferencia de vizinhanca e resolvida SELECIONANDO quem entra no alvo
    (local x remoto), e nao atribuindo peso numerico por site aqui."""
    pares = [(o.preco, _peso_observacao(o.status, params)) for o in observacoes if o.preco is not None]
    if not pares:
        return None
    if len({peso for _, peso in pares}) <= 1:
        return median(preco for preco, _ in pares)

    ordenado = sorted(pares, key=lambda par: par[0])
    peso_total = sum(peso for _, peso in ordenado)
    acumulado = 0.0
    for preco, peso in ordenado:
        acumulado += peso
        if acumulado >= peso_total / 2:
            return preco
    return ordenado[-1][0]


def selecionar_vizinhanca(
    mantidas: list[Observacao], params: dict[str, Any]
) -> tuple[list[Observacao], int, bool]:
    """Escolhe QUEM define o alvo de preco: so os concorrentes locais, quando
    houver o minimo configurado, senao todos.

    Os sites remotos nunca sao descartados -- eles ja passaram pelas 4 camadas e
    continuam contando para `n`, para o CV e para a divergencia Brick/web. O que
    esta funcao decide e apenas de quem sai a mediana que vira preco.

    Devolve (observacoes_do_alvo, n_local, alvo_so_local).
    """
    cfg = params["mercado"].get("vizinhanca")
    if not cfg or not cfg.get("ativo"):
        return mantidas, 0, False
    locais_cfg = set(cfg.get("sites_locais") or ())
    locais = [o for o in mantidas if o.site in locais_cfg]
    # "saopaulo" e o nome ANTIGO de "farmasp": e a MESMA loja. Contar os dois
    # inflava a vizinhanca (medido em 2026-08-07: 64 EANs atingiam o minimo de 3
    # com so 2 lojas distintas, e a loja duplicada pesava dobrado na mediana).
    apelidos = {k: v for k, v in (cfg.get("apelidos_site") or {}).items()}
    lojas_distintas = {apelidos.get(o.site, o.site) for o in locais}
    if len(lojas_distintas) >= cfg.get("n_min_local", 3):
        return locais, len(lojas_distintas), True
    return mantidas, len(lojas_distintas), False


def evidencia_remota_confiavel(
    n_total: int, cv: float | None, params: dict[str, Any]
) -> bool:
    """Ha concorrencia remota boa o bastante para NAO rebaixar o item?

    Sem isto, um item de Curva A popular que os locais ainda nao vendem cairia
    para PROTECAO_MARGEM justamente quando mais precisa de preco competitivo.
    """
    cfg = params["mercado"].get("vizinhanca")
    if not cfg or not cfg.get("ativo"):
        return True
    if n_total < cfg.get("n_remoto_confiavel", 4):
        return False
    return cv is not None and cv <= cfg.get("cv_remoto_confiavel", 0.20)


def _cv(precos: list[float]) -> float | None:
    if len(precos) < 2:
        return None
    m = median(precos)
    if m == 0:
        return None
    variancia = sum((p - m) ** 2 for p in precos) / len(precos)
    return (variancia ** 0.5) / m


def _peso_brick(
    n_web: int,
    cv: float | None,
    tem_brick: bool,
    cfg: dict[str, Any],
    alvo_so_local: bool = False,
) -> float:
    """Peso do Brick no blend.

    `alvo_so_local` = ha vizinhanca confiavel (>= n_min_local LOJAS distintas).
    Nesse caso o Brick cai para `com_vizinhanca_local`: ele e' auditoria de preco
    medio NACIONAL, que dilui redes de desconto e regioes mais baratas --
    evidencia fraca perto de concorrentes reais da mesma cidade, medidos hoje.
    Medido em 2026-08-07: o Brick causava 56% dos 176 itens precificados abaixo
    do menor concorrente local (caso BUPROVIL: Brick 13,93 contra concorrentes
    reais de 19,58 a 27,50).

    Sem vizinhanca local o Brick mantem o peso antigo -- ali ele e' a melhor
    evidencia disponivel, e rebaixa-lo deixaria o item sem ancora nenhuma.
    """
    if not tem_brick:
        return 0.0
    if alvo_so_local and "com_vizinhanca_local" in cfg:
        return cfg["com_vizinhanca_local"]
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


def _fator_fisico(
    segmento_brick: str | None,
    natureza_fiscal_item: str | None,
    params: dict[str, Any],
) -> float:
    """Fator que converte a mediana web (preco de site) em estimativa de
    balcao fisico.

    Para medicamentos com segmento Brick conhecido (RX/GEN/SIM/NMED), o fator
    e calibrado empiricamente contra auditoria fisica real (Brick) -- pode
    ser < 1 (balcao mais barato que o site) quando os dados confirmarem isso
    para aquele segmento especifico.

    Para o restante do catalogo (sem segmento Brick -- tipicamente perfumaria,
    conveniencia, puericultura), NAO ha auditoria fisica propria: nesse caso
    usa-se `mercado.premio_balcao`, um PREMIO (fator >= 1) por natureza
    fiscal, calibrado a partir do estudo Procon-SP 2025 (site das proprias
    redes e, em media, 13,88% mais barato que o balcao em generico e 3,73%
    em referencia) e da observacao operacional do usuario de que o balcao
    tende a ser mais caro que o site, nao mais barato (decisao 2026-08-05).
    Isso substitui o antigo fallback fixo `fator_fisico.default` (0.90, que
    presumia balcao mais barato para QUALQUER categoria sem base real).
    """
    cfg_fator = params["mercado"]["fator_fisico"]
    if segmento_brick and segmento_brick in cfg_fator:
        return cfg_fator[segmento_brick]

    cfg_premio = params["mercado"].get("premio_balcao")
    if cfg_premio and natureza_fiscal_item and natureza_fiscal_item in cfg_premio:
        return cfg_premio[natureza_fiscal_item]

    return cfg_fator["default"]


def calcular_mercado(
    observacoes: list[Observacao],
    params: dict[str, Any],
    data_referencia: date,
    vum_brick: float | None = None,
    segmento_brick: str | None = None,
    natureza_fiscal_item: str | None = None,
) -> ResultadoMercado:
    """Calcula a referencia de mercado de um EAN, combinando web filtrada e Brick.

    `vum_brick` e o preco de mercado (Brick) ja em R$; `segmento_brick` seleciona
    o fator fisico por categoria (RX/GEN/SIM/NMED) para converter a mediana web
    em estimativa de loja fisica antes do blend. `natureza_fiscal_item`
    ('medicamento'/'perfumaria_higiene'/'padrao') so e usado quando NAO ha
    segmento Brick, para aplicar o premio de balcao por categoria em vez do
    fator fixo antigo -- ver `_fator_fisico`.
    """
    cfg = params["mercado"]["outliers"]
    cfg_brick = params["mercado"]["brick"]
    fator_fisico = _fator_fisico(segmento_brick, natureza_fiscal_item, params)
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
    mediana_pre_ancora = _mediana_ponderada(pre_ancora, params)
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

    # `n` e `cv` continuam medindo TODAS as observacoes que sobreviveram as 4
    # camadas -- os remotos seguem valendo como evidencia de que o preco esta
    # certo. So a mediana que vira alvo e restrita a vizinhanca.
    precos = [o.preco for o in filtro.mantidas]
    n = len(precos)
    cv = _cv(precos)

    observacoes_alvo, n_local, alvo_so_local = selecionar_vizinhanca(
        list(filtro.mantidas), params)
    mediana_bruta = _mediana_ponderada(observacoes_alvo, params)
    mercado_web = mediana_bruta * fator_fisico if mediana_bruta is not None else None

    peso = _peso_brick(n, cv, mercado_brick is not None, params["mercado"]["peso_brick"],
                       alvo_so_local=alvo_so_local)

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
                    # `min`: esta regra existe para CONFIAR MENOS no Brick quando
                    # o concorrente real sustenta preco maior. Atribuir o peso
                    # direto poderia AUMENTA-lo onde a vizinhanca local ja o
                    # rebaixou (com_vizinhanca_local), invertendo a intencao.
                    peso = min(peso, cfg_cluster["peso_brick"])

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
        n_local=n_local,
        alvo_so_local=alvo_so_local,
        precos_alvo=tuple(o.preco for o in observacoes_alvo if o.preco is not None),
    )
