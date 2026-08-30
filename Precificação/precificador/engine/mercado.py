"""Motor de mercado: exclusao de outliers (4 camadas) + blend Brick/web.

Todas as funcoes sao puras: recebem dados e parametros, devolvem resultado.
Nenhuma leitura de arquivo ou banco acontece aqui (ver PLANO_SISTEMA_PRECIFICACAO.md
Parte 3.1 e 3.2 para a motivacao de cada regra).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
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
    # Brick descartado por incoerencia de unidade (ver _brick_incoerente).
    brick_descartado: bool = False
    # PMPF-PR ja normalizado por multiplo, e o peso com que entrou no blend.
    pmpf: float | None = None
    peso_pmpf: float = 0.0
    # Vizinhanca: quantos concorrentes LOCAIS sobraram apos as 4 camadas e se o
    # alvo foi calculado so com eles. `n` continua sendo o total (locais +
    # remotos), porque os remotos seguem validando o preco.
    n_local: int = 0
    alvo_so_local: bool = False
    precos_alvo: tuple[float, ...] = ()
    # As observacoes que definiram o alvo, com o site preservado. `precos_alvo`
    # perde a origem, e a ancora competitiva precisa saber de QUEM e' cada preco
    # (ver ancora_competitiva_local).
    observacoes_alvo: tuple[Observacao, ...] = ()
    # TODAS as observacoes de sites locais que sobreviveram as 4 camadas, mesmo
    # quando sao poucas demais para definir o alvo sozinhas (alvo_so_local=False).
    # Existe porque o piso/teto competitivo precisa de uma barra mais baixa que a
    # do alvo -- ver `observacoes_locais` em selecionar_vizinhanca.
    observacoes_locais: tuple[Observacao, ...] = ()


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


# Sugestao de varias vezes o que TODO o mercado coletado pratica nao e' politica
# de preco: e' custo podre ou base de embalagem errada passando pelo markup.
# Medido em 15/08/2026 contra a internet: Paracetamol 500 C/10 saiu a R$ 313
# (mercado R$ 5,99), Vick Vaporub 12g a R$ 587 (mercado R$ 13,90-22,11), Torsilax
# C/4 a R$ 168 (mercado R$ 4,99), Loratadina C/12 a R$ 51,79 (mercado ate R$ 11).
# Nos quatro o motor validou o erro do cadastro em vez de barra-lo.
RAZAO_SANIDADE_MAX = 3.0
# Em item de centavos a razao explode sozinha: agulha descartavel sugerida a
# R$ 0,79 contra mediana de R$ 0,21 e' "4x", mas a diferenca inteira sao 58
# centavos e a coleta pode ser preco de caixa de 100. Sem este piso a guarda
# passa a apagar sugestao boa de item barato, que e' justamente onde ela nao
# tem evidencia para agir.
GAP_SANIDADE_MINIMO = 5.0


def excede_sanidade(preco: float | None, observacoes: list[Observacao],
                    teto_cmed: float | None = None,
                    razao_max: float = RAZAO_SANIDADE_MAX,
                    gap_minimo: float = GAP_SANIDADE_MINIMO) -> tuple[float, int] | None:
    """(mediana do mercado, n lojas) quando `preco` a supera `razao_max` vezes.

    Ultima linha de defesa, aplicada sobre o preco final -- inclusive o manual,
    porque o erro tipico e' o usuario aplicar a sugestao errada e ela virar
    "manual". Nao substitui as 4 camadas de outlier: elas limpam a AMOSTRA, esta
    confere o RESULTADO contra a amostra crua.

    Diferente do teto competitivo local, que so age quando as lojas proximas
    concordam entre si (CV <= 15%), aqui a dispersao nao importa. Um item que o
    mercado inteiro vende entre R$ 3 e R$ 37 nao passa a valer R$ 315 porque os
    concorrentes discordam -- a Loratadina C/12 escapava exatamente por isso.

    O PMC isenta: preco de tabela de medicamento de marca fica legitimamente
    varias vezes acima da mediana coletada, porque a coleta pega a promocao das
    grandes redes (Aradois 50mg, PMC ~R$ 57, aparece a R$ 5-12 online). Enquanto
    a sugestao respeita o teto legal, ela e' preco de tabela, nao erro de dado.
    """
    if not preco or preco <= 0:
        return None
    if teto_cmed and preco <= teto_cmed:
        return None
    # Mediana por loja antes da mediana geral: sem isso um site com 40 coletas
    # decide sozinho o centro e a guarda passa a refletir uma loja so.
    por_loja: dict[str, list[float]] = {}
    for o in observacoes:
        if o.status in STATUS_PRECO_VALIDO and o.preco and o.preco > 0:
            por_loja.setdefault(o.site, []).append(o.preco)
    if len(por_loja) < 2:
        return None
    centro = median([median(v) for v in por_loja.values()])
    if centro <= 0 or preco <= centro * razao_max or preco - centro < gap_minimo:
        return None
    return centro, len(por_loja)


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


def _camada_4b_razao(
    obs: list[Observacao], n_min: int, n_max: int, razao_max: float
) -> tuple[list[Observacao], list[Descarte]]:
    """Rede de seguranca para n pequeno SEM ancora: descarta o preco que estiver
    a mais de `razao_max` vezes (ou 1/razao_max) da mediana dos DEMAIS.

    Buraco medido em 2026-08-10: 465 EANs tem 2-4 observacoes (a camada MAD nao
    roda, `mad_n_min=5`) e 315 deles nao tem Brick (a camada de ancora tambem
    nao roda) -- ficavam sem NENHUMA protecao contra outlier. Exemplos reais:
    [7.99, 9.49, 19.49, 26.89] e [7.49, 9.29, 24.60], todos entrando inteiros
    na mediana que define o alvo.

    Usa RAZAO contra a mediana dos outros, nao MAD: com n=3 o MAD e' instavel
    (a mediana dos desvios vira o proprio desvio do meio) e derruba ponto bom.
    A razao e' grosseira de proposito -- so pega erro de apresentacao/embalagem,
    que e' a origem tipica de um spread de 3x entre farmacias.

    Excluir o proprio ponto da mediana de comparacao evita que um outlier
    "puxe" a referencia e se auto-justifique -- com n=3 ele teria peso de 1/3.
    """
    if not (n_min <= len(obs) <= n_max) or razao_max <= 1:
        return obs, []
    mantidas, descartadas = [], []
    for i, o in enumerate(obs):
        outros = [x.preco for j, x in enumerate(obs) if j != i]
        if not outros:
            mantidas.append(o)
            continue
        med_outros = median(outros)
        if med_outros <= 0:
            mantidas.append(o)
            continue
        razao = o.preco / med_outros
        if razao > razao_max or razao < 1 / razao_max:
            descartadas.append(Descarte(
                o, "razao",
                f"preco {o.preco} e' {razao:.1f}x a mediana dos demais "
                f"({med_outros:.2f}); limite {razao_max:.1f}x (n pequeno, sem ancora)"))
        else:
            mantidas.append(o)
    # Nunca esvaziar: se tudo divergir de tudo, nao ha maioria para confiar.
    if not mantidas:
        return obs, []
    return mantidas, descartadas


def hampel_por_serie_temporal(
    observacoes: list[Observacao], n_min: int = 5, n_mad: float = 3.0,
) -> tuple[list[Observacao], list[Descarte]]:
    """Deteccao de anomalia na PROPRIA serie temporal de um par (EAN, site) --
    sinal distinto da camada 4 (MAD cross-site, dentro do MESMO ciclo). Pega
    "esse site caiu 40% da noite pro dia" mesmo quando nenhum outro site
    mudou naquele ciclo -- so' possivel com o historico completo que
    `observacao_farmacia` (MP2) acumula, nao com "so' a ultima observacao"
    (formato do precos.csv do app). Ver item 5 do plano de melhorias
    estatisticas (2026-08-30).

    Identificador de Hampel, leave-one-out: cada ponto e' comparado contra a
    mediana e o MAD dos OUTROS pontos da MESMA serie -- mesma ideia de
    `_camada_4b_razao` (nao inclui o proprio ponto, para nao se
    autojustificar), aplicada no eixo do TEMPO em vez de entre sites. Nao ha
    janela deslizante de proposito: a amostragem e' irregular e esparsa
    (poucos pontos por par mesmo com 45 dias de historico), entao uma janela
    fixa deixaria pontos de fora por coincidencia de calendario, nao por
    relevancia.

    Com menos de `n_min` observacoes de preco valido, devolve tudo mantido:
    historico curto demais para acusar alguem (mesmo espirito do
    `outliers.mad_n_min` da camada 4).
    """
    validos = [(i, o.preco) for i, o in enumerate(observacoes) if o.preco is not None]
    if len(validos) < n_min:
        return list(observacoes), []

    precos_validos = [p for _, p in validos]
    indices_anomalos: set[int] = set()
    for pos, (idx, preco) in enumerate(validos):
        outros = precos_validos[:pos] + precos_validos[pos + 1:]
        med = median(outros)
        mad = 1.4826 * median(abs(p - med) for p in outros)
        e_anomalo = abs(preco - med) > n_mad * mad if mad > 0 else preco != med
        if e_anomalo:
            indices_anomalos.add(idx)

    mantidas, descartadas = [], []
    for i, o in enumerate(observacoes):
        if i in indices_anomalos:
            descartadas.append(Descarte(
                o, "hampel_temporal",
                f"preco {o.preco} destoa da propria serie historica do site "
                f"(mediana leave-one-out, limite {n_mad}x MAD)"))
        else:
            mantidas.append(o)
    return mantidas, descartadas


def suavizar_ewma_temporal(
    observacoes: list[Observacao], data_referencia: date, half_life_dias: float,
) -> Observacao | None:
    """Substitui "ultima observacao" por uma media com decaimento por TEMPO
    (nao por indice -- a coleta nao e' regular; um EWMA classico por indice
    trataria uma falha de coleta de uma semana como se fosse um ciclo a mais).

    Peso de cada ponto: 0.5 ** (dias_atras / half_life_dias) -- perde metade
    do peso a cada `half_life_dias`. Observacoes sem `data_hora` conhecida
    pesam como se fossem de HOJE (peso 1.0): mais seguro que descarta-las por
    falta de metadado, mesma postura de `_camada_2_frescor` com
    `data_hora=None`.

    Recebe as observacoes de UM (EAN, site) -- quem agrupa e' o chamador (ver
    `motor/calcular.py` do MP2). Devolve uma Observacao SINTETICA: preco
    suavizado, e site/status/data_hora herdados da observacao MAIS RECENTE (a
    camada 2 de frescor continua julgando a idade por essa data). None se a
    lista nao tiver nenhum preco valido.

    Ver item 4 do plano de melhorias estatisticas (2026-08-30). So' faz
    sentido com HISTORICO real (observacao_farmacia no MP2, que guarda todos
    os ciclos); o formato do app (precos.csv, uma linha por par) nao tem o
    que suavizar.
    """
    validas = [o for o in observacoes if o.preco is not None and o.preco > 0]
    if not validas:
        return None

    pesos = [
        1.0 if o.data_hora is None
        else 0.5 ** (max(0, (data_referencia - o.data_hora).days) / half_life_dias)
        for o in validas
    ]
    soma_pesos = sum(pesos)
    preco_suavizado = sum(o.preco * peso for o, peso in zip(validas, pesos)) / soma_pesos

    mais_recente = max(validas, key=lambda o: o.data_hora or date.min)
    return replace(mais_recente, preco=round(preco_suavizado, 4))


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
    # 4b so age onde 3 e 4 nao alcancam: n pequeno E sem ancora.
    if ancora is None or ancora <= 0:
        atual, novas = _camada_4b_razao(
            atual, cfg.get("razao_n_min", 3), cfg["mad_n_min"] - 1,
            cfg.get("razao_max", 0.0))
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
) -> tuple[list[Observacao], int, bool, list[Observacao]]:
    """Escolhe QUEM define o alvo de preco: so os concorrentes locais, quando
    houver o minimo configurado, senao todos.

    Os sites remotos nunca sao descartados -- eles ja passaram pelas 4 camadas e
    continuam contando para `n`, para o CV e para a divergencia Brick/web. O que
    esta funcao decide e apenas de quem sai a mediana que vira preco.

    Devolve (observacoes_do_alvo, n_local, alvo_so_local, observacoes_locais).

    A quarta saida existe porque DEFINIR O ALVO e ANCORAR O PISO/TETO exigem
    barras diferentes de evidencia. Definir o alvo com uma unica loja seria
    frouxo -- por isso `n_min_local`. Mas "nao ficar mais barato que a loja da
    esquina" precisa apenas de UM preco local observado: ele ja prova que
    existe alguem ao lado vendendo por aquilo.

    Medido em 2026-08-12: dos 73 itens precificados abaixo de TODOS os
    concorrentes locais, 63 tinham `alvo_so_local=False` -- o motor via 1 ou 2
    locais depois das camadas de frescor/ancora, embora o dado bruto tivesse 3
    ou 4. Como o piso competitivo so recebia ancora quando `alvo_so_local` era
    verdadeiro, ele nunca rodava nesses casos e o alvo caia nos sites REMOTOS,
    que sao mais baratos e nao disputam este cliente.
    """
    cfg = params["mercado"].get("vizinhanca")
    if not cfg or not cfg.get("ativo"):
        return mantidas, 0, False, []
    locais_cfg = set(cfg.get("sites_locais") or ())
    locais = [o for o in mantidas if o.site in locais_cfg]
    # "saopaulo" e o nome ANTIGO de "farmasp": e a MESMA loja. Contar os dois
    # inflava a vizinhanca (medido em 2026-08-07: 64 EANs atingiam o minimo de 3
    # com so 2 lojas distintas, e a loja duplicada pesava dobrado na mediana).
    apelidos = {k: v for k, v in (cfg.get("apelidos_site") or {}).items()}
    lojas_distintas = {apelidos.get(o.site, o.site) for o in locais}
    if len(lojas_distintas) >= cfg.get("n_min_local", 3):
        return locais, len(lojas_distintas), True, locais
    return mantidas, len(lojas_distintas), False, locais


def _mediana_geografica(
    observacoes: list[Observacao],
    params: dict[str, Any],
    apelidos_site: dict[str, str] | None = None,
) -> float | None:
    """Media ponderada das medianas por site, usando pesos geograficos.

    Cada concorrente contribui com UM preco (sua mediana), evitando que
    sites com mais observacoes dominem o resultado. Os pesos representam
    a relevancia geografica/proximidade daquele concorrente.

    Quando o peso geografico esta inativo ou ha poucos sites, cai na
    mediana simples (comportamento antigo), mantendo a estabilidade.
    """
    cfg = params["mercado"].get("peso_geografico")
    if not cfg or not cfg.get("ativo", False):
        return _mediana_ponderada(observacoes, params)

    apelidos = apelidos_site or {}
    # Agrupa por site normalizado (desduplica farmasp/saopaulo)
    precos_por_site: dict[str, list[float]] = {}
    for o in observacoes:
        if o.preco is None:
            continue
        site_norm = apelidos.get(o.site, o.site)
        precos_por_site.setdefault(site_norm, []).append(o.preco)

    if not precos_por_site:
        return None

    # So ativa com sites suficientes; com 1-2 sites o peso nao faz sentido
    if len(precos_por_site) < 3:
        return _mediana_ponderada(observacoes, params)

    # Mediana por site, ponderada por peso geografico
    soma_ponderada = 0.0
    soma_pesos = 0.0
    for site, precos in precos_por_site.items():
        peso = cfg.get(site, 1.0)
        mediana_site = median(precos)
        soma_ponderada += mediana_site * peso
        soma_pesos += peso

    return soma_ponderada / soma_pesos if soma_pesos > 0 else None


def ancora_competitiva_local(
    mantidas: list[Observacao], params: dict[str, Any]
) -> tuple[float | None, float | None, str]:
    """Menor e maior concorrente LOCAL que servem de ancora ao piso competitivo.

    Duas protecoes contra "cobrir um preco que nao existe no balcao":

    1. SITES EXCLUIDOS DA ANCORA (`ancora_competitiva.excluir_sites`). O site
       continua valendo para n, CV, ranking e validacao -- so nao define
       sozinho o piso. Motivo (2026-08-10, teste presencial do usuario): o
       preco ONLINE da Nissei diverge muito do preco de BALCAO dela. A coleta
       so enxerga o site, entao esse gap e conhecimento que o dado nao tem.
       Mesma logica ja usada para sites remotos: seleciona-se QUEM define o
       alvo, em vez de atribuir peso numerico (ver `selecionar_vizinhanca`).

    2. WINSORIZACAO do menor preco. Se o menor local esta mais de
       `gap_maximo_pct` abaixo do segundo menor, ele e' tratado como preco-isca
       e o SEGUNDO menor vira a ancora. Protege contra qualquer loja com
       promocao pontual, sem hardcodar quem e' confiavel.

    Devolve (menor, maior, motivo). `motivo` vazio = nenhuma protecao agiu.
    """
    cfg = params["mercado"].get("ancora_competitiva")
    precos = sorted(o.preco for o in mantidas if o.preco is not None)
    if not precos:
        return None, None, ""
    if not cfg or not cfg.get("ativo"):
        return precos[0], precos[-1], ""

    apelidos = params["mercado"].get("vizinhanca", {}).get("apelidos_site") or {}
    # ASSIMETRIA DELIBERADA entre as duas pontas -- e' estatistica, nao gosto.
    #
    # O MINIMO de uma amostra e' um limite superior do minimo verdadeiro: se
    # observei uma loja a R$ 20, existe alguem ao lado vendendo por R$ 20 ou
    # menos. Uma observacao basta para ancorar o PISO, e o erro so pode ser na
    # direcao segura (piso baixo demais).
    #
    # O MAXIMO de uma amostra pequena SUBESTIMA o maximo verdadeiro: com uma
    # loja observada eu nao sei quem e' o mais caro da praca, sei so quem eu vi.
    # Usar isso como TETO transforma o unico preco coletado -- que pode estar em
    # promocao -- em trava dura para o catalogo inteiro.
    #
    # Medido em 12/08/2026: com a mesma barra (1 loja) nas duas pontas,
    # PISO_ACIMA_DO_MERCADO saltou de 30 para 204 itens numa rodada. Por isso o
    # teto exige `n_min_lojas_teto` (3, o mesmo da vizinhanca) e o piso exige
    # apenas `n_min_lojas` (1).
    lojas = {apelidos.get(o.site, o.site) for o in mantidas if o.preco is not None}
    if len(lojas) < cfg.get("n_min_lojas", 1):
        return None, None, ""
    permite_teto = len(lojas) >= cfg.get("n_min_lojas_teto", 3)
    excluir = {s.lower() for s in (cfg.get("excluir_sites") or ())}
    motivo = ""

    elegiveis = sorted(
        o.preco for o in mantidas
        if o.preco is not None and apelidos.get(o.site, o.site).lower() not in excluir
    )
    # Nunca ficar sem ancora: se a exclusao esvaziar o conjunto, volta a usar todos.
    if not elegiveis:
        return precos[0], (precos[-1] if permite_teto else None), ""
    if len(elegiveis) < len(precos):
        motivo = (f"ancora do piso competitivo ignora {', '.join(sorted(excluir))} "
                  f"(preco online diverge do balcao)")

    menor = elegiveis[0]
    gap_max = cfg.get("gap_maximo_pct", 0.0)
    if gap_max > 0 and len(elegiveis) >= 3 and elegiveis[1] > 0:
        if 1 - menor / elegiveis[1] > gap_max:
            menor = elegiveis[1]
            extra = (f"menor local (R$ {elegiveis[0]:.2f}) ficou {1 - elegiveis[0] / elegiveis[1]:.0%} "
                     f"abaixo do 2o menor: tratado como preco-isca, ancora no 2o")
            motivo = f"{motivo}; {extra}" if motivo else extra
    return menor, (elegiveis[-1] if permite_teto else None), motivo


def dispersao_por_site(
    observacoes_por_ean: dict[str, list[Observacao]],
    sites_locais: set[str],
    apelidos_site: dict[str, str] | None = None,
    n_min_pares: int = 5,
) -> dict[str, dict[str, float]]:
    """Dispersao de cada site LOCAL em relacao aos OUTROS locais, agregada em
    todos os EANs -- generaliza a medicao manual que excluiu a Nissei da
    ancora competitiva (ver [mercado.ancora_competitiva] em parametros.toml,
    "preco da loja / mediana das outras, mesmo EAN": Nissei 1,011 mas p25
    0,866/p75 1,145, i.e. NIVEL normal e DISPERSAO alta).

    Para cada EAN com 3+ locais validos no mesmo ciclo, cada site contribui
    com |seu_preco / mediana_dos_OUTROS_locais - 1|. A dispersao final e' a
    MEDIANA desses desvios (nao a media -- mesma razao de robustez usada em
    todo o resto do motor: uma promocao pontual nao pode dominar o numero).

    Isto e' SO A MEDICAO. Nao decide sozinho quem entra em
    `ancora_competitiva.excluir_sites` -- essa continua sendo uma decisao
    humana, deliberada (ver o comentario do TOML sobre por que peso numerico
    por site foi rejeitado em favor de SELECIONAR quem entra). Rodar via
    `auditar_calibracao.py --secao dispersao_sites`.

    Devolve {site: {"n": pares usados, "dispersao": mediana dos desvios}}.
    Site com menos de `n_min_pares` fica de fora -- amostra fina demais para
    acusar alguem.
    """
    apelidos = apelidos_site or {}
    desvios: dict[str, list[float]] = {}
    for observacoes in observacoes_por_ean.values():
        por_loja: dict[str, float] = {}
        for o in observacoes:
            if (o.site not in sites_locais or o.status not in STATUS_PRECO_VALIDO
                    or not o.preco or o.preco <= 0):
                continue
            por_loja[apelidos.get(o.site, o.site)] = o.preco
        if len(por_loja) < 3:
            continue
        for site, preco in por_loja.items():
            outros = [p for s, p in por_loja.items() if s != site]
            med_outros = median(outros)
            if med_outros <= 0:
                continue
            desvios.setdefault(site, []).append(abs(preco / med_outros - 1))

    return {
        site: {"n": len(valores), "dispersao": median(valores)}
        for site, valores in desvios.items()
        if len(valores) >= n_min_pares
    }


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


def _dispersao_robusta(precos: list[float]) -> float | None:
    """Dispersao relativa em torno da MEDIANA -- NAO e' o coeficiente de
    variacao classico (que usa a media nos dois lugares).

    O campo publico ainda se chama `cv` e os parametros ainda se chamam
    `cv_baixo_limite`, `cv_max`, `cv_remoto_confiavel`. Ficam assim de
    proposito: renomear tudo mexeria em TOML, painel e historico. O nome desta
    funcao e' que foi corrigido, para ninguem recalibrar um limiar assumindo a
    definicao de livro-texto.

    Por que a distincao importa (medido em 2026-08-10): com dado limpo os dois
    praticamente coincidem (~1% de diferenca), mas com outlier presente esta
    versao chega a ficar 38% ACIMA do CV classico --

        [15; 15,5; 16; 30]  ->  0,4531 aqui  contra  0,3288 no CV classico

    e e' exatamente nesse regime que os limiares decidem (cv <= 0,15 define
    PRECO_IMAGEM; cv_max 0,20 aceita o cluster; cv <= 0,20 valida evidencia
    remota). Ou seja: esta funcao e' CONSERVADORA por construcao -- na duvida
    ela acusa mais dispersao, nao menos. Mantida assim de proposito.
    """
    if len(precos) < 2:
        return None
    m = median(precos)
    if m == 0:
        return None
    desvio_quadratico_medio = sum((p - m) ** 2 for p in precos) / len(precos)
    return (desvio_quadratico_medio ** 0.5) / m


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


def _fator_brick_para_web(segmento_brick: str | None, params: dict[str, Any]) -> float:
    """Razao Brick / mediana_web, por segmento -- fator de FONTE DE DADO.

    Calibrado como `Brick / mediana_web` em 1.523 EANs e remedido em 2026-08-10
    sobre a base atual, que reproduz os mesmos valores (GEN 0,886; NMED 0,916;
    RX 0,938; SIM 0,821). Isso mede a distancia entre a AUDITORIA NACIONAL do
    Brick e a mediana dos sites que esta loja coleta -- redes grandes do
    sul/sudeste. O Brick dilui redes de desconto e regioes mais baratas do pais
    inteiro, entao ele fica naturalmente ABAIXO da base web local.

    NAO mede canal (site x balcao) -- o nome `fator_fisico` no TOML e' legado e
    sugere o contrario. Efeito canal vive exclusivamente em
    `mercado.premio_balcao`; empilhar os dois poe dois multiplicadores sobre o
    mesmo preco.

    Uso correto: DIVIDIR o Brick por este fator, subindo-o para a escala
    regional observada -- nunca multiplicar a mediana web por ele, que empurra
    o preco para a escala nacional (mais barata) e baixa a referencia do lado
    errado.
    """
    cfg_fator = params["mercado"]["fator_fisico"]
    if segmento_brick and segmento_brick in cfg_fator:
        return cfg_fator[segmento_brick]
    return cfg_fator["default"]


def _brick_incoerente(
    vum_brick: float | None,
    mediana_web: float | None,
    n_web: int,
    custo: float | None,
    params: dict[str, Any],
) -> bool:
    """O Brick e' erro de unidade? (caixa/display em vez de unidade avulsa)

    Regra pedida pelo usuario em 2026-08-11: quando o CUSTO e os CONCORRENTES
    concordam entre si -- os dois fazem sentido -- e o Brick esta a uma ordem de
    grandeza dos dois, o errado e' o Brick. Ele e descartado inteiro, em vez de
    entrar no blend e arrastar o preco.

    Medido em 2026-08-11 nos 1.256 EANs com custo + Brick + web: a razao
    Brick/mediana_web fica em [0,5; 2,0] em 1.241 deles, em [0,33; 0,5] em 10, e
    salta direto para 20-40x em 5 -- todos apresentacao de CAIXA lida como
    unidade (DORALGINA C/4: custo 3,05, concorrentes 5,45, Brick 110,85 ->
    preco sugerido de R$ 112,99). Nao existe nada entre 2x e 20x, entao o corte
    em 3x separa os dois grupos com folga larga dos dois lados.

    Coerencia custo x web: markup mediana_web/custo tem p99 = 4,46x nesta base
    (n=2.127). `markup_max` = 6,0 fica acima do p99 -- so 7 itens ficam de fora,
    e esses sao eles proprios suspeitos.

    Exige web: sem concorrente nao ha o segundo testemunho que a regra pede, e o
    Brick continua sendo a unica ancora disponivel. Medido nesta data: zero EANs
    com Brick >= 15x o custo e nenhuma observacao web -- o vao nao existe hoje.
    """
    cfg = params["mercado"].get("brick_incoerente") or {}
    if not cfg.get("ativo") or not vum_brick or vum_brick <= 0:
        return False
    if not mediana_web or mediana_web <= 0 or n_web < cfg.get("n_min_web", 2):
        return False
    if not custo or custo <= 0:
        return False
    # Custo e web fazem sentido entre si? (web acima do custo, markup plausivel)
    if not (custo <= mediana_web <= custo * cfg.get("markup_max", 6.0)):
        return False
    razao = vum_brick / mediana_web
    razao_min = cfg.get("razao_min", 3.0)
    return razao >= razao_min or razao <= 1 / razao_min


def normalizar_pmpf(pmpf: float | None, multiplo: float | None) -> float | None:
    """PMPF por unidade de venda.

    O arquivo da SEFAZ-PR traz `Multiplo` junto com o preco: itens de caixa
    fechada ("AAS 100mg - 20 x 10 comprimidos", multiplo 20) tem o PMPF da
    CAIXA. Dividir pelo multiplo devolve a apresentacao que vai ao balcao.

    Medido em 2026-08-12 sobre 539 EANs com PMPF e 3+ lojas locais: a correlacao
    de log-preco com a mediana local sobe de 0,915 (PMPF cru) para 0,958 com a
    divisao. Sem ela, os 382 itens de multiplo > 1 entrariam 10 a 50 vezes acima
    da escala -- o mesmo erro de unidade que ja atrapalhava com o Brick.
    """
    if not pmpf or pmpf <= 0:
        return None
    m = multiplo or 1.0
    return pmpf / m if m > 0 else pmpf


def _peso_pmpf(
    tem_web: bool, alvo_so_local: bool, cfg: dict[str, Any] | None
) -> float:
    """Peso do PMPF no blend, pela forca da evidencia que ele enfrenta.

    O PMPF e a melhor ancora disponivel para esta loja e ainda assim NAO manda
    sozinho onde ha concorrente real medido hoje. Hierarquia de evidencia:

      concorrente local de hoje  >  PMPF (balcao, estadual, semestral)
                                 >  Brick (auditoria nacional)

    Medido em 2026-08-12 (539 EANs com PMPF e 3+ lojas locais): PMPF/mediana
    local tem mediana 0,98, p25 0,91 e p75 1,07 -- ele ja esta NA escala do
    balcao local, sem fator de conversao, ao contrario do Brick (0,78-0,94).
    Por isso ele entra direto no blend, e por isso o premio de balcao NAO se
    aplica sobre a parcela dele: aplicar converteria preco de balcao em preco
    de balcao de novo.

    A defasagem e o motivo de nao dar peso maior: a tabela vale por SEMESTRE
    (NPF 07/2026 cobre 01/04 a 30/09) e e media ponderada do estado inteiro,
    incluindo cidades e canais mais baratos que Maringa centro.
    """
    if not cfg:
        return 0.0
    if not tem_web:
        return cfg.get("sem_web", 0.80)
    if alvo_so_local:
        return cfg.get("com_vizinhanca_local", 0.25)
    return cfg.get("sem_vizinhanca_local", 0.45)


def _premio_balcao(natureza_fiscal_item: str | None, params: dict[str, Any]) -> float:
    """Premio de canal: converte preco de SITE em estimativa de BALCAO.

    Este e o unico lugar do motor que trata o efeito canal. Fator >= 1: o
    balcao e mais caro que o site (estudo Procon-SP 2025 -- o site das proprias
    redes e, em media, 13,88% mais barato em generico e 3,73% em referencia;
    confirmado presencialmente pelo usuario em 2026-08-10).

    Aplicado UMA VEZ, no fim, sobre a referencia ja consolidada -- nunca por
    site e nunca antes das 4 camadas. Aplicar por site antes dos filtros
    desloca a banda de ancora (que compara contra o Brick cru) e a torna
    assimetrica: o teto efetivo cai de 1,60x para 1,45x do Brick, descartando
    preco alto real com mais facilidade que preco baixo.
    """
    cfg_premio = params["mercado"].get("premio_balcao")
    if cfg_premio and natureza_fiscal_item and natureza_fiscal_item in cfg_premio:
        return cfg_premio[natureza_fiscal_item]
    return 1.0


def calcular_mercado(
    observacoes: list[Observacao],
    params: dict[str, Any],
    data_referencia: date,
    vum_brick: float | None = None,
    segmento_brick: str | None = None,
    natureza_fiscal_item: str | None = None,
    custo: float | None = None,
    pmpf: float | None = None,
    pmpf_multiplo: float | None = None,
) -> ResultadoMercado:
    """Calcula a referencia de mercado de um EAN, combinando web filtrada e Brick.

    `vum_brick` e o preco de mercado (Brick) ja em R$; `segmento_brick`
    (RX/GEN/SIM/NMED) seleciona a razao Brick/web usada para DIVIDIR o Brick,
    subindo-o para a escala regional observada antes do blend -- ver
    `_fator_brick_para_web`. `natureza_fiscal_item`
    ('medicamento'/'perfumaria_higiene'/'padrao') aplica o premio de balcao
    sobre a referencia ja consolidada, sempre, independente de haver segmento
    Brick -- ver `_premio_balcao`.
    """
    cfg = params["mercado"]["outliers"]
    cfg_brick = params["mercado"]["brick"]
    cfg_pmpf = params["mercado"].get("pmpf") or {}
    mercado_pmpf = (normalizar_pmpf(pmpf, pmpf_multiplo)
                    if cfg_pmpf.get("ativo") else None)

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
    mercado_web_pre_ancora = mediana_pre_ancora

    # GUARDA DE UNIDADE: se custo e concorrentes concordam e o Brick esta a uma
    # ordem de grandeza deles, o Brick e' que esta errado (preco de caixa lido
    # como unidade). Descartado ANTES de virar ancora da camada 3 -- se rodasse
    # depois, a propria banda [0,60; 1,60] ja teria apagado todos os precos reais
    # (n=0 -> peso_brick "sem_web" = 1,00 -> referencia = Brick puro, o caminho
    # exato do caso DORALGINA: sugestao de R$ 112,99 para um item de R$ 5,45).
    brick_descartado = _brick_incoerente(
        vum_brick, mercado_web_pre_ancora,
        len([o for o in pre_ancora if o.preco]), custo, params)
    if brick_descartado:
        vum_brick = None

    # O Brick e' auditoria NACIONAL: sobe para a escala regional observada
    # (dividir pela razao Brick/web) antes de ser comparado ou blendado com a
    # web local. Multiplicar a mediana web por este fator faz o oposto -- desce
    # o preco para a escala nacional (mais barata) e baixa a referencia.
    fator_bw = _fator_brick_para_web(segmento_brick, params)
    mercado_brick = (
        vum_brick * (1 + cfg_brick["spread_etiqueta"]) / fator_bw
        if vum_brick and fator_bw > 0 else None
    )

    # Divergencia Brick x web: bandeira de "pode ser EAN/apresentacao errada".
    # O PMPF e' a TERCEIRA TESTEMUNHA e desempata de graca -- quando ele bate
    # com um dos dois lados dentro do mesmo limite, o desacordo esta explicado e
    # nao ha o que um humano decidir: a fonte que ficou sozinha e' a errada, e as
    # camadas 3-4 (com o PMPF de ancora) ja a descartam. Sem este desempate a
    # fila era 107 itens; medido em 12/08/2026, em 69 deles o PMPF concordava com
    # um dos lados (53 com o Brick, 16 com a web) -- 65% da fila era conferencia
    # de um desacordo ja resolvido pelo motor. Sobram 38, os sem PMPF (29) e os
    # em que o PMPF discorda dos DOIS (9) -- esses sim precisam de olho.
    limite_div = cfg_brick["divergencia_brick_web_limite"]
    divergencia = False
    if mercado_brick is not None and mercado_web_pre_ancora is not None and mercado_brick > 0:
        divergencia = abs(mercado_web_pre_ancora / mercado_brick - 1) > limite_div
        if divergencia and mercado_pmpf:
            explicado = (abs(mercado_pmpf / mercado_web_pre_ancora - 1) <= limite_div
                         or abs(mercado_pmpf / mercado_brick - 1) <= limite_div)
            divergencia = not explicado

    # Camadas 3-4 (ancora + MAD) para chegar na mediana final usada no blend.
    # A ancora tem de estar na MESMA escala das observacoes (web regional): usar
    # `vum_brick` cru aqui compararia preco de site contra media nacional, o que
    # deslocava a banda [0,60; 1,60] para baixo e descartava preco alto real com
    # mais facilidade que preco baixo (assimetria medida em 2026-08-10).
    # O PMPF tem PRIORIDADE sobre o Brick como ancora da camada 3: ele e preco
    # de balcao apurado em NFC-e do proprio estado, ja na escala das observacoes
    # (razao 0,98 contra a mediana local, medida em 539 EANs), enquanto o Brick
    # e media nacional que precisa do fator de conversao para chegar perto. Uma
    # ancora que ja esta na escala certa erra menos nas duas pontas da banda.
    ancora_web = vum_brick / fator_bw if vum_brick and fator_bw > 0 else None
    if mercado_pmpf and cfg_pmpf.get("prioridade_ancora", True):
        ancora_web = mercado_pmpf
    atual, novas = _camada_3_ancora(pre_ancora, ancora_web, cfg["banda_ancora_min"], cfg["banda_ancora_max"])
    descartadas_ancora = novas

    # CLUSTER ACIMA DA BANDA: a camada de ancora existe para descartar ruido e
    # erro de apresentacao, nao para jogar fora preco de mercado real so porque
    # o Brick esta desatualizado/baixo. Se os proprios precos que ela descartou
    # por estarem acima do teto formam um cluster apertado, eles sao mercado --
    # e voltam para o conjunto, INTEIROS (a observacao, nao so a mediana).
    #
    # Devolver a observacao importa porque os precos do cluster sao justamente
    # os concorrentes CAROS, e locais com frequencia: corrigir so a mediana
    # deixaria `n`, `n_local`, `alvo_so_local`, `precos_alvo` e a ancora do piso
    # competitivo calculados sem eles -- o item perderia a vizinhanca, o alvo
    # cairia nos sites REMOTOS baratos e o piso competitivo nem rodaria. Casos
    # medidos em 2026-08-11:
    #   7896004734026 (Curva A): banda do Brick apagava Sao Joao 81,70 e Farmasp
    #     69,07; alvo caiu nos remotos de 36,59 -> sugestao 37,49 com os locais
    #     entre 54,85 e 81,70.
    #   7897595601773: sobravam 2 observacoes, tier caiu para PROTECAO_MARGEM e
    #     o preco virou custo-mais-margem (5,90) com os locais entre 26 e 29.
    #
    # Restaurar antes das camadas 4/4b deixa o resto do motor recalcular sozinho
    # (mediana, vizinhanca, peso do Brick, ancora competitiva) em vez de aplicar
    # remendo em cada um. Nao e' preciso conferir se o cluster supera a mediana
    # web: todo preco do cluster esta ACIMA do teto da banda e todo preco mantido
    # esta abaixo dele, entao devolver so pode subir a mediana.
    # A regra do cluster existe para um problema ESPECIFICO do Brick: ele pode
    # estar desatualizado e baixo, e ai os concorrentes acima da banda sao
    # mercado real. O PMPF nao tem esse problema -- e oficial, semestral e
    # apurado em NFC-e do proprio estado. Quando ele e' a ancora, devolver
    # precos que ele rejeitou desfaz justamente a protecao que ele traz.
    #
    # Medido em 12/08/2026 (DORALGINA C/4, custo R$ 3,05, PMPF R$ 5,72): a banda
    # do PMPF apagava corretamente os precos de CAIXA coletados na web, e o
    # cluster os devolvia inteiros, levando a sugestao para R$ 61,99.
    # CORRECAO 12/08/2026: desligar o cluster sob PMPF foi longe demais. O PMPF
    # e' oficial, mas e' SEMESTRAL -- quando ele esta velho ou traz outra
    # apresentacao, a banda apaga o mercado inteiro e nao sobra rede de protecao
    # nenhuma, que e' a falha exata do PROFENID 100mg INJ: PMPF R$ 7,65 contra
    # OITO lojas entre R$ 30,92 e R$ 43,49, todas apagadas -> sugestao de R$ 7,79.
    # O que separa esse caso do DORALGINA (onde a devolucao era ruim) nao e' a
    # fonte da ancora, e' quantas LOJAS INDEPENDENTES sustentam o cluster: o
    # DORALGINA tinha duas, o PROFENID tem oito. Erro de apresentacao e' de site,
    # nao se repete igual em oito. Entao sob PMPF o cluster continua vivo, so que
    # com a barra mais alta (`n_min_sob_pmpf`), contada em lojas distintas.
    cluster_acima = False
    cfg_cluster = params["mercado"].get("cluster_acima_brick")
    sob_pmpf = bool(mercado_pmpf) and cfg_pmpf.get("prioridade_ancora", True)
    n_min_cluster = (cfg_cluster or {}).get("n_min_sob_pmpf", 3) if sob_pmpf else (cfg_cluster or {}).get("n_min", 2)
    apelidos_cluster = (params["mercado"].get("vizinhanca", {}).get("apelidos_site") or {})
    if cfg_cluster and ancora_web and (mercado_brick or sob_pmpf):
        teto_banda = ancora_web * cfg["banda_ancora_max"]
        # MARKETPLACE fica de fora do cluster (nao do resto do motor): devolver
        # ao conjunto um preco que a banda ja rejeitou e' um ato FORTE de
        # confianca, e vendedor terceiro dentro do site da farmacia nao tem essa
        # credencial -- ele lista a propria apresentacao, que e' justamente a
        # origem do erro que a banda existe para pegar. Medido em 2026-08-11,
        # os unicos casos em que a devolucao levava o preco para bem acima do
        # mercado local eram sustentados so por marketplace:
        #   7891350038958: locais proprios a 8,78 e 16,99, cluster formado por
        #     drogariasp 24,98 e paguemenos 26,07, ambos MARKETPLACE -> 25,49.
        #   7891317021931: unico "local" era drogaraia 108,49, MARKETPLACE.
        # Isto e coerente com [mercado.marketplace] no TOML: a forma correta de
        # descontar marketplace e' SELECIONAR quem entra, nao dar peso numerico.
        acima = [d for d in descartadas_ancora
                 if d.observacao.preco > teto_banda and d.observacao.status != "MARKETPLACE"]
        # A contagem por LOJAS DISTINTAS so' vale sob PMPF: e' ali que a barra
        # mais alta existe para separar erro de site (1-2 fontes) de mercado
        # real (3+ lojas). No caminho do Brick a regra segue como estava, em
        # numero de observacoes -- mexer nela seria mudar comportamento medido
        # de outro caso, sem caso novo que peca isso.
        lojas_cluster = {apelidos_cluster.get(d.observacao.site, d.observacao.site) for d in acima}
        evidencia = len(lojas_cluster) if sob_pmpf else len(acima)
        if evidencia >= n_min_cluster:
            cv_cluster = _dispersao_robusta([d.observacao.preco for d in acima])
            if cv_cluster is not None and cv_cluster <= cfg_cluster["cv_max"]:
                cluster_acima = True
                atual = atual + [d.observacao for d in acima]
                devolvidas = {id(d) for d in acima}
                descartadas_ancora = [d for d in descartadas_ancora if id(d) not in devolvidas]

    descartadas += descartadas_ancora
    atual, novas = _camada_4_mad(atual, cfg["mad_n_min"], cfg["mad_multiplicador"])
    descartadas += novas
    # 4b so age onde 3 e 4 nao alcancam: n pequeno E sem ancora (sem Brick).
    # Medido em 2026-08-10: 315 EANs caiam exatamente nesse vao.
    if ancora_web is None or ancora_web <= 0:
        atual, novas = _camada_4b_razao(
            atual, cfg.get("razao_n_min", 3), cfg["mad_n_min"] - 1,
            cfg.get("razao_max", 0.0))
        descartadas += novas
    filtro = ResultadoFiltro(mantidas=tuple(atual), descartadas=tuple(descartadas))

    # `n` e `cv` continuam medindo TODAS as observacoes que sobreviveram as 4
    # camadas -- os remotos seguem valendo como evidencia de que o preco esta
    # certo. So a mediana que vira alvo e restrita a vizinhanca.
    precos = [o.preco for o in filtro.mantidas]
    n = len(precos)
    cv = _dispersao_robusta(precos)

    observacoes_alvo, n_local, alvo_so_local, observacoes_locais = selecionar_vizinhanca(
        list(filtro.mantidas), params)
    # Apelidos de site (farmasp/saopaulo) para normalizar antes da mediana geografica
    apelidos_site = {
        k: v for k, v in (params["mercado"].get("vizinhanca", {}).get("apelidos_site") or {}).items()
    }
    mediana_bruta = _mediana_geografica(observacoes_alvo, params, apelidos_site)
    mercado_web = mediana_bruta

    peso = _peso_brick(n, cv, mercado_brick is not None, params["mercado"]["peso_brick"],
                       alvo_so_local=alvo_so_local)

    # `min`: a regra do cluster existe para CONFIAR MENOS no Brick quando o
    # concorrente real sustenta preco maior. Atribuir o peso direto poderia
    # AUMENTA-lo onde a vizinhanca local ja o rebaixou (com_vizinhanca_local),
    # invertendo a intencao.
    if cluster_acima:
        peso = min(peso, cfg_cluster["peso_brick"])

    if mercado_brick is not None and mercado_web is not None:
        valor_referencia = peso * mercado_brick + (1 - peso) * mercado_web
    elif mercado_brick is not None:
        valor_referencia = mercado_brick
    else:
        valor_referencia = mercado_web

    # Premio de canal (site -> balcao), aplicado UMA VEZ sobre a referencia ja
    # consolidada. Ate aqui tudo esta na escala do preco ONLINE observado, que e'
    # a escala em que as 4 camadas e a banda de ancora operam; converter antes,
    # por site, contamina os filtros.
    premio = _premio_balcao(natureza_fiscal_item, params)
    if valor_referencia is not None and premio != 1.0:
        valor_referencia = valor_referencia * premio

    # PMPF entra por ULTIMO, DEPOIS do premio de balcao e sobre a referencia ja
    # convertida: ele JA e preco de balcao (apurado em NFC-e ao consumidor
    # final), entao multiplica-lo pelo premio converteria balcao em balcao de
    # novo. As duas parcelas ficam assim na mesma escala antes de se misturarem.
    peso_pmpf = 0.0
    if mercado_pmpf:
        peso_pmpf = _peso_pmpf(n > 0, alvo_so_local, cfg_pmpf)
        if valor_referencia is None:
            valor_referencia, peso_pmpf = mercado_pmpf, 1.0
        elif peso_pmpf > 0:
            valor_referencia = peso_pmpf * mercado_pmpf + (1 - peso_pmpf) * valor_referencia

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
        brick_descartado=brick_descartado,
        pmpf=mercado_pmpf,
        peso_pmpf=peso_pmpf,
        n_local=n_local,
        alvo_so_local=alvo_so_local,
        precos_alvo=tuple(o.preco for o in observacoes_alvo if o.preco is not None),
        observacoes_alvo=tuple(observacoes_alvo),
        observacoes_locais=tuple(observacoes_locais),
    )
