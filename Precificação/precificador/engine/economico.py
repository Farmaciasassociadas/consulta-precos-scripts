"""Motor economico: fiscal (segregacao), piso, tier, alvo, travas, grade.

Funcoes puras, sem I/O. Ver PLANO_SISTEMA_PRECIFICACAO.md Parte 2 (fiscal),
Parte 3.3 (piso/travas) e ESTUDO_PRECIFICACAO_DROGARIA.md (tier/alvo) para a
motivacao de cada regra.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from engine.chamariz import alvo_chamariz

RAZOES_EMBALAGEM_FIXAS = [2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 24, 25, 30, 40, 48, 50, 60, 100]


def corrigir_preco_atual(
    venda_unit: float | None,
    preco_anterior: float | None,
    custo_final: float | None,
    pmc_val: float | None,
    vum_brick: float | None,
) -> tuple[float | None, str | None]:
    """Detecta e corrige (ou descarta) um preco unitario absurdo.
    PMC/CMED nao serve como ancora unica: o cadastro oficial pode estar preso
    a uma apresentacao (qtde de unidades) diferente da caixa comercial.
    Prioridade de ancora: Brick > PMC > preco anterior > custo."""
    if venda_unit is None:
        return None, None

    ancoras = []
    if vum_brick:
        ancoras.append(("Brick", vum_brick, 2.0))
    if pmc_val:
        ancoras.append(("PMC/CMED", pmc_val, 1.05))
    if preco_anterior:
        ancoras.append(("preco anterior no banco", preco_anterior, 3.0))
    if custo_final:
        ancoras.append(("custo (markup maximo 10x)", custo_final, 10.0))
    if not ancoras:
        return venda_unit, None

    nome_ref, ancora, tolerancia = ancoras[0]
    if venda_unit <= ancora * tolerancia:
        return venda_unit, None

    melhor_razao, melhor_dif, melhor_ref = None, None, None
    for razao in RAZOES_EMBALAGEM_FIXAS:
        corrigido = venda_unit / razao
        if ancora * 0.2 <= corrigido <= ancora * tolerancia:
            dif = abs(corrigido - ancora)
            if melhor_dif is None or dif < melhor_dif:
                melhor_razao, melhor_dif, melhor_ref = razao, dif, nome_ref

    if not melhor_razao:
        razao_bruta = venda_unit / ancora
        banda_min = max(0.10, 1.5 / razao_bruta) if razao_bruta > 0 else 0.10
        for razao in range(2, 101):
            if razao in RAZOES_EMBALAGEM_FIXAS:
                continue
            corrigido = venda_unit / razao
            if ancora * banda_min <= corrigido <= ancora * tolerancia:
                dif = abs(corrigido - ancora)
                if melhor_dif is None or dif < melhor_dif:
                    melhor_razao, melhor_dif, melhor_ref = razao, dif, nome_ref

    if not melhor_razao:
        outras_ancoras = []
        if pmc_val and pmc_val != ancora:
            outras_ancoras.append(("PMC/CMED", pmc_val, 1.05))
        if vum_brick and vum_brick != ancora:
            outras_ancoras.append(("Brick", vum_brick, 2.0))
        if custo_final and custo_final != ancora:
            outras_ancoras.append(("custo", custo_final, 10.0))
        for ref_nome, ref_valor, ref_tol in outras_ancoras:
            for razao in range(2, 101):
                corrigido = venda_unit / razao
                razao_bruta = venda_unit / ref_valor
                banda_min = max(0.10, 1.5 / razao_bruta) if razao_bruta > 0 else 0.10
                if ref_valor * banda_min <= corrigido <= ref_valor * ref_tol:
                    dif = abs(corrigido - ref_valor)
                    if melhor_dif is None or dif < melhor_dif:
                        melhor_razao, melhor_dif, melhor_ref = razao, dif, ref_nome

    if melhor_razao:
        corrigido = venda_unit / melhor_razao
        return corrigido, (
            f"preco incoerente corrigido: dividido por {melhor_razao} "
            f"(erro de embalagem/apresentacao no ERP)."
        )

    return None, (
        f"preco descartado: R$ {venda_unit:.2f} incoerente com {nome_ref} "
        f"(R$ {ancora:.2f}) e nenhuma razao de embalagem ate 100x explicou a diferenca."
    )


def preco_atual_e_outlier_historico(
    preco_atual: float | None,
    mediana_sugerido_historico: float | None,
    banda_min: float = 0.5,
    banda_max: float = 2.0,
) -> bool:
    """True se preco_atual estiver fora de uma banda ampla em torno da mediana
    de preco_sugerido nas rodadas anteriores do mesmo EAN. Puramente informativo:
    reforca na justificativa que o cadastro esta desatualizado, nao trava preco."""
    if preco_atual is None or mediana_sugerido_historico is None or mediana_sugerido_historico <= 0:
        return False
    razao = preco_atual / mediana_sugerido_historico
    return razao < banda_min or razao > banda_max

# Categorias cuja natureza legal e "medicamento" para fins de Lei 10.147/2000
# (regime monofasico) -- taxonomia antiga (grupo pai do relatorio de NF) e
# nova (POLITICA_MARKUP_POR_CATEGORIA.csv) misturadas, ate o de-para oficial
# existir (pendencia 5.4 do plano). Perfumaria/higiene tem monofasico proprio
# (NCM 3303-3307 etc.) mas nao e "medicamento" para efeito de ICMS-ST tipico.
PREFIXOS_MEDICAMENTO = ("ETICOS", "GENERICO", "GENÉRICO", "SIMILAR", "REFERENCIA", "REFERÊNCIA", "LIBERADO")
PREFIXOS_PERFUMARIA_HIGIENE = ("PERFUMARIA",)


# De-para do segmento auditado do Brick para o eixo da taxonomia interna.
# NMED (nao-medicamento) fica de fora de proposito: ele nao diz QUAL categoria
# de perfumaria/varejo o item e, entao nao da para corrigir nada com ele.
EIXO_POR_SEGMENTO_BRICK = {"GEN": "GENERICO", "RX": "ETICOS", "SIM": "SIMILAR"}
EIXOS_MEDICAMENTO = ("ETICOS", "GENERICO", "SIMILAR")

# Subcategoria usada ao resgatar um item de fora do eixo medicamento (ver
# resgatar_eixo_perdido). Nao ha subcategoria original para herdar -- "HIGIENE
# PESSOAL"/"ACESSORIOS" nao mapeia para RX/USO CONTINUO/CONTROLADO -- e a
# amostra auditada em 2026-08-10 (82 itens com PMC fora do eixo medicamento)
# mostrou predominancia de produtos de venda livre (Strepsils, Salonpas,
# Canesten): O.T.C/MIP e o destino mais seguro, nunca CONTROLADO/RX.
SUBCATEGORIA_RESGATE = {"ETICOS": "O.T.C/MIP", "GENERICO": "O.T.C/MIP", "SIMILAR": "O.T.C/MIP-SIMILAR"}


def corrigir_eixo_por_brick(
    categoria: str | None, segmento_brick: str | None, categorias_validas
) -> tuple[str | None, str]:
    """Corrige o EIXO (GENERICO/ETICOS/SIMILAR) usando o segmento do Brick.

    Medido em 2026-08-06: dos 434 itens com segmento Brick e eixo cadastrado,
    111 divergem (26%), quase todos com brick=GEN e ERP=ETICOS. Isso NAO muda
    aliquota (natureza_fiscal olha o prefixo de medicamento + ICMS-ST, e os tres
    eixos sao medicamento), mas muda o lucro-alvo da politica: ETICOS > RX pede
    10% e GENERICO > RX pede 15%. Classificar generico como etico subprecifica.

    So a primeira parte muda; a subcategoria (RX, USO CONTINUO, CONTROLADO...)
    e preservada, porque o Brick nao sabe dela. Se a categoria resultante nao
    existir na taxonomia oficial, nada e alterado.

    Devolve (categoria, motivo). `motivo` vazio significa "nada mudou".
    """
    eixo_brick = EIXO_POR_SEGMENTO_BRICK.get((segmento_brick or "").upper())
    if not eixo_brick or not categoria or " > " not in categoria:
        return categoria, ""
    eixo_atual, _, subcategoria = categoria.partition(" > ")
    eixo_atual = eixo_atual.strip()
    if eixo_atual not in EIXOS_MEDICAMENTO or eixo_atual == eixo_brick:
        return categoria, ""
    subcategoria = subcategoria.strip()
    for candidata in _subcategorias_equivalentes(eixo_brick, subcategoria):
        corrigida = f"{eixo_brick} > {candidata}"
        if corrigida in categorias_validas:
            return corrigida, (f"eixo corrigido de {eixo_atual} para {eixo_brick} "
                               f"pelo segmento Brick")
    return categoria, ""


def resgatar_eixo_perdido(
    categoria: str | None, segmento_brick: str | None, categorias_validas
) -> tuple[str | None, str]:
    """Resgata para o eixo medicamento um item cadastrado fora dele (PERFUMARIA,
    VAREJO, EXCLUSIVOS) quando o segmento Brick indica RX/GEN/SIM.

    Motivado por auditoria de 2026-08-10: 82 EANs em referencia_categoria_brick.csv
    tinham pmc_maximo preenchido (prova de que sao medicamento CMED -- so
    medicamento tem PMC) mas estavam fora do eixo medicamento; 5 desses geraram
    preco sugerido absurdo (ate R$ 553 num item de R$ 35 no mercado) porque o
    motor aplicou a margem-alvo de perfumaria em vez da de medicamento.
    corrigir_eixo_por_brick nao pega este caso: ela exige eixo_atual ja em
    EIXOS_MEDICAMENTO (linha ~150), entao um item em PERFUMARIA/VAREJO nunca
    passa pelo gate, mesmo com segmento_brick preenchido.

    So atua com segmento_brick preenchido (RX/GEN/SIM) -- os itens que so tem
    pmc_maximo, sem segmento, nao tem eixo conhecido e ficam de fora de
    proposito (ver auditar_eixo_sombra.py, que os sinaliza para revisao
    humana em vez de corrigir automaticamente).

    Sem subcategoria original para herdar (PERFUMARIA/VAREJO nao tem RX/USO
    CONTINUO/CONTROLADO), o destino e sempre O.T.C/MIP: a amostra auditada
    mostrou predominancia de venda livre, e O.T.C/MIP e a subcategoria de
    menor risco (nunca classifica como CONTROLADO por engano).

    Devolve (categoria, motivo). `motivo` vazio significa "nada mudou".
    """
    eixo_brick = EIXO_POR_SEGMENTO_BRICK.get((segmento_brick or "").upper())
    if not eixo_brick or not categoria or " > " not in categoria:
        return categoria, ""
    eixo_atual, _, _ = categoria.partition(" > ")
    eixo_atual = eixo_atual.strip()
    if eixo_atual in EIXOS_MEDICAMENTO:
        return categoria, ""
    corrigida = f"{eixo_brick} > {SUBCATEGORIA_RESGATE[eixo_brick]}"
    if corrigida in categorias_validas:
        return corrigida, (f"eixo resgatado de {eixo_atual} para {eixo_brick} "
                           f"pelo segmento Brick (item era medicamento cadastrado fora do eixo)")
    return categoria, ""


def _subcategorias_equivalentes(eixo: str, subcategoria: str):
    """Mesma subcategoria escrita de formas diferentes conforme o eixo.

    A taxonomia usa "SIMILAR > RX-SIMILAR" e "SIMILAR > O.T.C/MIP-SIMILAR",
    enquanto os outros eixos usam "RX" e "O.T.C/MIP" puros. Sem este de-para,
    66 dos 111 itens divergentes ficariam sem correcao so por causa do nome.
    """
    yield subcategoria
    if eixo == "SIMILAR":
        yield f"{subcategoria}-SIMILAR"
    else:
        # Caminho inverso: vindo de SIMILAR para GENERICO/ETICOS.
        for sufixo in ("-SIMILAR",):
            if subcategoria.endswith(sufixo):
                yield subcategoria[: -len(sufixo)]


def natureza_fiscal(classificacao: str | None, tem_icms_st: bool) -> str:
    """Classifica o item em 'medicamento' / 'perfumaria_higiene' / 'padrao'.

    Heuristica por categoria + evidencia empirica de ICMS-ST na NF, na
    ausencia de NCM no relatorio de compras (ver plano, pendencia 5.4:
    pedir a coluna NCM ao ERP fecha isso de forma definitiva).
    """
    cat = (classificacao or "").upper()
    e_medicamento = cat.startswith(PREFIXOS_MEDICAMENTO)
    e_perfumaria_higiene = cat.startswith(PREFIXOS_PERFUMARIA_HIGIENE)
    if e_medicamento and tem_icms_st:
        return "medicamento"
    if e_medicamento or e_perfumaria_higiene:
        return "perfumaria_higiene"
    return "padrao"


def aliquota_simples_nominal(params: dict[str, Any]) -> float:
    """Aliquota efetiva nominal da faixa atual do Anexo I, antes de qualquer segregacao."""
    cfg = params["simples"]["aliquota_nominal"]
    rbt12, faixa_pct, deduzir = cfg["rbt12_referencia_reais"], cfg["faixa_pct"], cfg["parcela_deduzir_reais"]
    return (rbt12 * faixa_pct - deduzir) / rbt12


def aliquota_simples_efetiva(params: dict[str, Any], natureza: str) -> float:
    nominal = aliquota_simples_nominal(params)
    multiplicador = params["simples"]["segregacao"]["multiplicador"][natureza]
    return nominal * multiplicador


def divisor_piso(params: dict[str, Any], natureza: str) -> float:
    """Divisor do ALVO economico: rateia a estrutura inteira (fixa + variavel).

    Continua incluindo `despesas_fixas_pct` de proposito -- e o preco que a loja
    precisa praticar NO MIX para pagar a estrutura. Nao confundir com o piso
    minimo de venda, que usa `divisor_piso_contribuicao` (ver `piso`).
    """
    premissas = params["premissas"]
    return (1 - premissas["cartao_pct"] - premissas["despesas_fixas_pct"]
            - despesas_de_comercializacao(params) - aliquota_simples_efetiva(params, natureza))


def despesas_de_comercializacao(params: dict[str, Any], tem_pbm: bool = False) -> float:
    """Despesas por unidade vendida que NAO sao cartao nem Simples.

    Duas parcelas novas em 12/08/2026, ambas parametrizadas em [premissas]:

    PBM: a autorizadora cobra taxa de servico sobre a venda subsidiada. Na DRE
    e' Despesa de Comercializacao, e incide SO no item vendido via programa --
    por isso e' argumento, nao constante. Zerado por padrao ate a taxa do
    contrato ser confirmada; parametro errado aqui e' pior que ausente.

    Reforma tributaria (CBS/IBS): a fase de aliquotas-teste de 2026 tem
    tratamento proprio para empresa do Simples Nacional. Tambem zerado ate a
    contabilidade confirmar por escrito se ha incidencia efetiva alem do DAS --
    inventar 1% aqui deslocaria o alvo de 3.041 itens com base em palpite.
    """
    premissas = params["premissas"]
    total = premissas.get("despesas_variaveis_pct", 0.0)
    total += premissas.get("cbs_ibs_pct", 0.0)
    if tem_pbm:
        total += premissas.get("pbm_taxa_pct", 0.0)
    return total


def divisor_piso_contribuicao(params: dict[str, Any], natureza: str) -> float:
    """Divisor do PISO de venda: so o que custa POR UNIDADE VENDIDA.

    Despesa fixa (aluguel, folha, energia) e custo do PERIODO, nao do produto:
    ela nao desaparece se a unidade nao for vendida. Ratea-la por unidade no piso
    faz o motor recusar venda que ainda daria contribuicao positiva -- medido em
    2026-08-07, com a despesa fixa dentro do piso: 33,6% do catalogo tinha
    markup ate o menor concorrente local abaixo dos 23% de margem bruta que o
    piso entao exigia, 354 itens ficavam presos em `alvo == piso` e 142 saiam
    mais caros que TODOS os concorrentes.

    A despesa fixa continua coberta -- pelo ALVO (divisor_piso) e pela meta de
    margem do mix, nao por uma trava item a item.
    """
    premissas = params["premissas"]
    return (1 - premissas["cartao_pct"] - despesas_de_comercializacao(params)
            - aliquota_simples_efetiva(params, natureza))


def divisor_alvo(params: dict[str, Any], natureza: str, lucro_liquido_alvo_pct: float) -> float:
    return divisor_piso(params, natureza) - lucro_liquido_alvo_pct


def margem_bruta_minima(params: dict[str, Any], natureza: str) -> float:
    """Margem bruta minima aplicavel, por natureza fiscal.

    `margem_bruta_minima_pct` (0,25) e' um piso CEGO: ignora custo, categoria e
    concorrencia. Medido em 2026-08-10, ele era a causa provavel de boa parte
    dos 135 itens em MERCADO_LOCAL_ABAIXO_DO_PISO e dos 16,3% precificados
    acima do maior concorrente local. Em generico 25% e' folgado; em item de
    alto giro e baixo valor agregado, e' o que tira o item do mercado.

    `margem_bruta_minima_por_natureza` permite afrouxar onde o mercado e'
    apertado sem baixar o piso do catalogo inteiro. Natureza ausente da
    sub-tabela = usa o valor global.
    """
    por_natureza = params["premissas"].get("margem_bruta_minima_por_natureza") or {}
    if natureza in por_natureza:
        return por_natureza[natureza]
    return params["premissas"].get("margem_bruta_minima_pct", 0.0)


def piso(custo: float, params: dict[str, Any], natureza: str) -> float:
    piso_simples = custo / divisor_piso_contribuicao(params, natureza)
    piso_contribuicao = custo + params["premissas"]["contribuicao_minima_reais"]
    margem_minima = margem_bruta_minima(params, natureza)
    if margem_minima > 0 and margem_minima < 1:
        piso_margem = custo / (1 - margem_minima)
        return max(piso_simples, piso_contribuicao, piso_margem)
    return max(piso_simples, piso_contribuicao)


def piso_minimo(custo: float, params: dict[str, Any], natureza: str) -> float:
    """O menor preco que ainda paga a estrutura variavel -- sem a margem-alvo.

    Diferenca para `piso`: fica de fora `margem_bruta_minima`, que e' META de
    rentabilidade da DRE, nao restricao fisica. Sobram os dois pisos que sao
    restricao de verdade: cobrir imposto e despesa variavel de comercializacao
    (`divisor_piso_contribuicao`) e deixar a contribuicao minima em reais.

    Uso: itens em que o piso cheio nao cabe abaixo de NENHUM concorrente local.
    Ali a escolha real e' entre vender com pouca margem e nao vender -- e item
    parado nao realiza margem nenhuma. Decisao do usuario em 12/08/2026:
    "aplique a menor margem possivel neles e bola pra frente".
    """
    return max(custo / divisor_piso_contribuicao(params, natureza),
               custo + params["premissas"]["contribuicao_minima_reais"])


EMBALAGENS_USUAIS = (2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 24, 25, 30, 36, 48, 50, 100)


def fator_venda_provavel(custo_nf: float, mercado: float, params: dict[str, Any]) -> int:
    """Quantas unidades a NF traz, deduzido do proprio dado.

    A conta nao e' `custo / mercado`: o preco de mercado ja carrega margem. Com
    margem bruta tipica `m`, o custo unitario do concorrente e' `mercado*(1-m)`,
    entao o fator e' `custo_nf / (mercado * (1-m))`. Arredondar para a
    embalagem comercial mais proxima evita fator quebrado.

    Validado em 12/08/2026 no unico caso com a embalagem escrita no nome --
    SAB PROTEX CREAM 85G **C/12**: razao crua 7,9 e a formula devolve 12. Os
    outros tres da mesma leva (TALENTO, CHOCOTRIO, NEVRALGEX) convergem para
    embalagens comerciais padrao pela mesma conta.

    E' SUGESTAO, nao correcao automatica: quem confirma e' a NF. Um fator errado
    grava custo errado no catalogo inteiro do item.
    """
    margem = (params.get("embalagem") or {}).get("margem_referencia_pct", 0.35)
    if mercado <= 0 or custo_nf <= 0:
        return 1
    bruto = custo_nf / (mercado * (1 - margem))
    return min(EMBALAGENS_USUAIS, key=lambda k: abs(k - bruto))


def pct_custo_estimado(natureza: str | None, params: dict[str, Any]) -> float:
    """Fracao do preco de mercado usada como custo ESTIMADO quando o item nao
    tem custo validado por NF (ver `aplicar_travas`, status
    OK_SEM_CUSTO_BASE_MERCADO -- so' afeta o painel/relatorio, nunca bloqueia
    o preco sugerido).

    Item 6 do plano de melhorias estatisticas (2026-08-30): substitui a
    constante global unica (`custo_estimado.pct_do_preco_mercado`, 0,60 desde
    sempre, igual pra todo item) por um valor com SHRINKAGE BAYESIANO por
    natureza fiscal -- mesmo raciocinio de Efron & Morris (1973) para a media
    de varios grupos: `pct = peso*pct_natureza_medido + (1-peso)*pct_global`,
    `peso = n_natureza/(n_natureza + k)`. Com pouca evidencia na natureza, o
    resultado fica perto do global; com muita (como hoje: 452 a 1651 EANs por
    natureza), fica perto do proprio numero medido.

    Os `pct_shrunk` ja' vem PRE-CALCULADOS no TOML por
    `auditar_calibracao.py --secao shrinkage`: o `n` por natureza so' existe
    no momento da auditoria (roda sobre a base completa), nao no calculo por
    item. Natureza ausente da tabela (ou None) cai no `pct_do_preco_mercado`
    global -- o mesmo fallback de sempre.
    """
    cfg = params.get("custo_estimado", {})
    global_pct = cfg.get("pct_do_preco_mercado", 0.60)
    por_natureza = cfg.get("por_natureza") or {}
    if natureza and natureza in por_natureza:
        return por_natureza[natureza].get("pct_shrunk", global_pct)
    return global_pct


def alvo_economico(custo: float, params: dict[str, Any], natureza: str, lucro_liquido_alvo_pct: float) -> float:
    return custo / divisor_alvo(params, natureza, lucro_liquido_alvo_pct)


def classificar_xyz(cv_demanda: float | None, params: dict[str, Any]) -> str | None:
    """X (previsivel) / Y (oscilante) / Z (erratica), pelo CV da demanda semanal.

    Segundo eixo da matriz ABC-XYZ. Devolve None quando nao ha historico
    suficiente -- que e' a situacao de HOJE: a loja nao tem semanas de venda
    acumuladas, e CV de demanda com menos de `semanas_minimas` pontos e ruido,
    nao previsibilidade. Nesse caso nenhum premio e' aplicado (ver
    `premio_risco_xyz`), que e' o comportamento seguro.
    """
    cfg = params.get("xyz") or {}
    if not cfg.get("ativo") or cv_demanda is None:
        return None
    if cv_demanda <= cfg.get("limite_x", 0.25):
        return "X"
    if cv_demanda <= cfg.get("limite_y", 0.50):
        return "Y"
    return "Z"


def premio_risco_xyz(curva_abc: str | None, classe_xyz: str | None,
                     params: dict[str, Any]) -> float:
    """Acrescimo ao lucro-alvo por risco de estoque, pela celula ABC-XYZ.

    A logica e' de risco de INVENTARIO, nao de sensibilidade a preco: item de
    alto valor e demanda erratica (celula AZ) exige estoque de seguranca grande
    e corre risco real de vencer na prateleira; a margem tem de pagar esse
    risco. Item AX gira sozinho e nao precisa de premio nenhum.

    Devolve 0,0 sem classificacao XYZ -- que e' o caso do catalogo inteiro ate
    a loja acumular `xyz.semanas_minimas` semanas de venda.
    """
    cfg = params.get("xyz") or {}
    if not cfg.get("ativo") or not classe_xyz or not curva_abc:
        return 0.0
    return (cfg.get("premio", {}) or {}).get(f"{curva_abc}{classe_xyz}", 0.0)


def margem_bruta_meta_mix(params: dict[str, Any]) -> float:
    """Margem bruta que o MIX inteiro precisa entregar para a DRE fechar.

    Soma tudo que a margem bruta tem de pagar antes de virar lucro: estrutura
    fixa rateada, cartao, despesas de comercializacao, o Simples (na aliquota
    da natureza mais cara, para nao subestimar) e o lucro liquido pretendido.

    Nao confundir com o alvo POR ITEM: item a item, a margem varia de propósito
    -- magra onde o cliente compara, gorda onde nao compara. Esta e' a media
    ponderada que o conjunto tem de alcancar, e e' a unica que paga contas.
    """
    premissas = params["premissas"]
    return (premissas["despesas_fixas_pct"]
            + premissas["cartao_pct"]
            + despesas_de_comercializacao(params)
            + aliquota_simples_efetiva(params, "padrao")
            + premissas.get("lucro_liquido_meta_mix_pct", 0.0))


def ajuste_lucro_alvo_mix(
    margem_bruta_realizada: float | None,
    params: dict[str, Any],
) -> tuple[float, str]:
    """De quanto subir o lucro-alvo para o MIX fechar a meta -- e so nos itens
    que podem absorver isso sem perder cliente.

    Fecha o laco que faltava: hoje o motor otimiza item a item e a margem
    agregada e' consequencia, nao objetivo. Se o conjunto fica abaixo da meta da
    DRE, a correcao NAO pode sair dos itens com vizinhanca visivel -- subir
    preco onde o cliente compara e' exatamente como se perde cliente. Sai dos
    itens de baixa comparabilidade, que e' o subsidio cruzado feito na ordem
    certa: primeiro descobre-se o buraco, depois quem pode pagar por ele.

    O ajuste e' limitado por `ajuste_maximo_pp`: se o buraco for grande demais
    para a cauda longa cobrir, o certo e' aparecer no relatorio e virar decisao
    de compra ou de estrutura, nao ser espremido em silencio no preco.

    Devolve (acrescimo em pontos de lucro-alvo, motivo).
    """
    cfg = params.get("mix") or {}
    if not cfg.get("ativo") or margem_bruta_realizada is None:
        return 0.0, ""
    meta = margem_bruta_meta_mix(params)
    folga = meta - margem_bruta_realizada
    if folga <= cfg.get("tolerancia_pp", 0.01):
        return 0.0, (f"Mix em {margem_bruta_realizada:.1%} contra meta de "
                     f"{meta:.1%}: dentro da tolerancia, sem ajuste.")
    ajuste = min(folga, cfg.get("ajuste_maximo_pp", 0.05))
    aviso = ""
    if folga > cfg.get("ajuste_maximo_pp", 0.05):
        aviso = (f" ATENCAO: faltam {folga:.1%} e o ajuste esta limitado a "
                 f"{ajuste:.1%} -- o resto NAO se resolve no preco (rever compra, "
                 f"mix ou estrutura).")
    return ajuste, (f"Mix em {margem_bruta_realizada:.1%} contra meta de {meta:.1%}: "
                    f"lucro-alvo elevado em {ajuste:.1%} apenas nos itens sem "
                    f"vizinhanca local visivel.{aviso}")


TIERS = ("PRECO_IMAGEM", "PADRAO", "PROTECAO_MARGEM", "REVISAO_HUMANA")

# Categorias "formadoras de preco": decisao de negocio 2026-08-30. Uso
# continuo (recorrencia alta, cliente fixa a percepcao de preco da farmacia
# nesses itens) e anticoncepcional (mesma logica, alta comparacao entre
# farmacias) devem ficar o MAIS PERTO POSSIVEL do menor preco pesquisado, nao
# so "com mercado" como o tier PRECO_IMAGEM generico ja trata. O nome da
# subcategoria e' o mesmo de politica_markup.csv (ETICOS/GENERICO/SIMILAR >
# USO CONTINUO e > ANTICONCEPCIONAL), entao nao precisa de cadastro novo.
MARCADORES_FORMADOR_OPINIAO = ("USO CONTINUO", "ANTICONCEPCIONAL")


def e_formador_opiniao(categoria: str | None) -> bool:
    if not categoria:
        return False
    cat = categoria.upper()
    return any(marcador in cat for marcador in MARCADORES_FORMADOR_OPINIAO)


def determinar_tier(
    papel_politica: str | None,
    curva_abc: str | None,
    n_concorrentes: int,
    cv: float | None,
    tem_brick: bool,
    categoria: str | None = None,
) -> str:
    if papel_politica == "REVISAO_HUMANA":
        return "REVISAO_HUMANA"

    e_imagem = (
        (n_concorrentes >= 4 and cv is not None and cv <= 0.15)
        or (curva_abc == "A" and (cv is None or cv <= 0.35))
        or papel_politica == "PRECO_IMAGEM"
    )
    # Curva C so forca protecao quando a evidencia de mercado e' de fato fraca.
    # Curva C sozinha nao basta: como `e_protecao` vence `e_imagem`
    # incondicionalmente, um item C com 6 concorrentes e CV 5% -- mercado
    # perfeitamente medido -- seria tratado como se nao tivesse mercado nenhum.
    # Medido em 2026-08-10 sem a condicao `mercado_fraco`: 66% do catalogo
    # (2.533 itens) caia em PROTECAO_MARGEM, que tambem aperta a trava de
    # variacao (0.30 vs 0.50).
    mercado_fraco = n_concorrentes < 3
    e_protecao = (
        (n_concorrentes == 0 and not tem_brick)
        or (curva_abc == "C" and mercado_fraco)
        or (not tem_brick and n_concorrentes < 2)
        or papel_politica == "PROTECAO_MARGEM"
    )

    # Formador de preco vence o heuristico de mercado fraco: sem esta excecao
    # um item USO CONTINUO/ANTICONCEPCIONAL (papel=PRECO_IMAGEM em
    # politica_markup.csv) com vizinhanca local fraca -- curva C com <3
    # concorrentes, ou sem Brick com <2 -- caia em PROTECAO_MARGEM mesmo com a
    # politica pedindo o oposto. Sem NENHUMA evidencia de mercado o item
    # continua seguro: calcular_alvo cai no alvo economico quando
    # valor_referencia_mercado e' None, entao nao ha preco "inventado" aqui.
    if papel_politica == "PRECO_IMAGEM" and e_formador_opiniao(categoria):
        return "PRECO_IMAGEM"

    if e_protecao:
        # Falta de mercado ou giro fraco pesa mais que um sinal isolado de imagem:
        # sem evidencia solida, protege margem em vez de inventar competitividade
        # (ESTUDO_PRECIFICACAO_DROGARIA.md, secao 6).
        return "PROTECAO_MARGEM"
    if e_imagem:
        return "PRECO_IMAGEM"
    return "PADRAO"


def alvo_por_ranking(
    tier: str,
    precos_concorrentes: list[float],
    params: dict[str, Any],
    curva_abc: str | None = None,
    categoria: str | None = None,
) -> float | None:
    """Posiciona o preço num RANKING de concorrentes elegíveis, em vez de
    perseguir sempre o menor preço. Decisão de negócio 2026-08-05: a loja não
    precisa ser a mais barata -- fica deliberadamente em 2º/3º lugar (ou pior,
    conforme configurado por tier), escolhendo o MAIOR preço que ainda garanta
    essa posição. Chamariz/KVI ficam fora desta função (tratados como exceção
    comercial à parte, cadastro futuro).

    EXCEÇÃO 2026-08-30: categorias formadoras de preço (uso contínuo,
    anticoncepcional -- ver `e_formador_opiniao`) ignoram curva ABC e tier e
    miram sempre o rank 1 (mais perto possível do menor preço pesquisado). A
    lucratividade continua garantida por fora: o rank 1 aqui só define o
    ALVO, e `aplicar_travas`/`arredondar_grade` nunca deixam o preço final
    abaixo do piso.

    Com poucas observações (abaixo de `ranking.n_min_observacoes`) o ranking
    não é estatisticamente confiável: devolve None para o chamador cair no
    fallback `valor_referencia_mercado * 0.99`.
    """
    cfg = params.get("ranking")
    if not cfg:
        return None
    if len(precos_concorrentes) < cfg["n_min_observacoes"]:
        return None

    ordenados = sorted(precos_concorrentes)
    if e_formador_opiniao(categoria):
        rank_alvo = 1
    else:
        # Curva ABC, quando conhecida, tem prioridade sobre o default por tier:
        # Curva A (KVI/alta visibilidade) fica mais perto do mercado (2o lugar);
        # Curva B/C (cauda longa) pode ficar mais atras (3o lugar), protegendo
        # margem sem risco relevante de perda de cliente (decisao 2026-08-05).
        cfg_curva = cfg.get("rank_alvo_por_curva", {})
        if curva_abc and curva_abc in cfg_curva:
            rank_alvo = cfg_curva[curva_abc]
        else:
            rank_alvo = cfg["rank_alvo_por_tier"].get(tier, cfg["rank_alvo_por_tier"]["PADRAO"])
    rank_alvo = min(rank_alvo, len(ordenados))

    if rank_alvo <= 1:
        return ordenados[0] * 0.99

    # Preço-alvo fica no meio-termo entre quem ocupa a posição logo abaixo do
    # rank-alvo e quem ocupa o rank-alvo: mais caro que o de baixo, mais
    # barato que o de cima -- garante a posição sem colar no concorrente.
    abaixo = ordenados[rank_alvo - 2]
    no_alvo = ordenados[rank_alvo - 1]
    return (abaixo + no_alvo) / 2


def calcular_alvo(
    tier: str,
    valor_referencia_mercado: float | None,
    alvo_econ: float,
    precos_concorrentes: list[float] | None = None,
    params: dict[str, Any] | None = None,
    curva_abc: str | None = None,
    e_chamariz: bool = False,
    categoria: str | None = None,
) -> float:
    if e_chamariz and precos_concorrentes and params is not None:
        cfg_chamariz = params.get("chamariz", {})
        alvo_chz = alvo_chamariz(precos_concorrentes, cfg_chamariz.get("desconto_maximo_pct", 0.0))
        if alvo_chz is not None:
            return alvo_chz
    if tier in ("PRECO_IMAGEM", "PADRAO") and valor_referencia_mercado is not None:
        if precos_concorrentes and params is not None:
            alvo_ranking = alvo_por_ranking(tier, precos_concorrentes, params, curva_abc, categoria)
            if alvo_ranking is not None:
                return alvo_ranking
        # Sem concorrentes suficientes para um ranking confiável: encosta na
        # referência de mercado como guarda-corpo.
        return valor_referencia_mercado * 0.99
    if tier == "PROTECAO_MARGEM" and valor_referencia_mercado is not None:
        return min(alvo_econ, valor_referencia_mercado * 1.15)
    return alvo_econ


@dataclass(frozen=True)
class ResultadoGrade:
    preco: float | None
    motivo: str | None = None


def fronteira_digito_esquerda(valor: float, degraus: list[list[float]] | None = None) -> float:
    """Proximo valor em que o DIGITO DA ESQUERDA muda (R$ 19,99 -> 20).

    O efeito de digito da esquerda (Thomas & Morwitz, JCR 2005) so dispara
    quando o digito mais a esquerda difere: R$ 19,99 e' percebido como "19 e
    pouco", R$ 20,49 como "20 e pouco". Entre 19,49 e 19,99 nao ha degrau
    perceptual -- os 50 centavos sao margem de graca.

    O passo cresce com o preco porque a granularidade que o cliente enxerga
    tambem cresce: abaixo de R$ 20 ele le o real; ate R$ 100 le a dezena de
    reais em multiplos de 5; acima disso, a dezena.
    """
    for limite, passo in (degraus or [[20.0, 1.0], [100.0, 5.0]]):
        if valor < limite:
            return (int(valor / passo) + 1) * passo
    return (int(valor / 10.0) + 1) * 10.0


def arredondar_grade(
    alvo: float,
    piso_valor: float,
    teto: float | None,
    terminacoes: list[float],
    params: dict[str, Any] | None = None,
    precos_locais: list[float] | None = None,
) -> ResultadoGrade:
    """Escolhe o preco final na grade de terminacoes.

    Base: a terminacao mais proxima do alvo. Com [grade.limiar] ativo, sobe
    dessa base ate a MAIOR terminacao que ainda respeita, ao mesmo tempo:
      - a fronteira de digito da esquerda (o cliente le o mesmo numero);
      - `tolerancia_pct` acima do alvo economico;
      - o menor concorrente local que hoje esta ACIMA de nos (nao ultrapassa
        ninguem -- a posicao no ranking nao piora).
    Ver ESTUDO_PRICING_2026 para a medicao: +1,37% de receita e +2,1% de lucro
    bruto no catalogo, com zero item passando a ser o mais caro da praca.
    """
    if teto is not None and piso_valor > teto:
        return ResultadoGrade(None, "piso acima do teto: grade impossivel")
    limite_superior = teto if teto is not None else max(alvo, piso_valor) + 5
    reais_min = int(piso_valor)
    reais_max = int(max(alvo, piso_valor, limite_superior)) + 1
    opcoes = [
        reais + termo
        for reais in range(reais_min, reais_max + 1)
        for termo in terminacoes
        if reais + termo >= piso_valor - 1e-9 and (teto is None or reais + termo <= teto + 1e-9)
    ]
    if not opcoes:
        return ResultadoGrade(None, "nenhuma terminacao da grade coube entre piso e teto")

    escolhido = min(opcoes, key=lambda v: abs(v - alvo))

    cfg = (params or {}).get("grade", {}).get("limiar") or {}
    if not cfg.get("ativo"):
        return ResultadoGrade(escolhido)

    teto_limiar = fronteira_digito_esquerda(escolhido, cfg.get("degraus"))
    acima = [p for p in (precos_locais or []) if p > escolhido + 1e-9]
    if precos_locais:
        # Ja somos o mais caro da praca: subir mais so afasta o cliente.
        teto_limiar = min(teto_limiar, min(acima) if acima else escolhido + 1e-9)
    tolerancia = cfg.get("tolerancia_pct", 0.03)
    candidatas = [
        v for v in opcoes
        if escolhido - 1e-9 <= v < teto_limiar - 1e-9 and v <= alvo * (1 + tolerancia) + 1e-9
    ]
    if not candidatas:
        return ResultadoGrade(escolhido)
    melhor = max(candidatas)
    if melhor <= escolhido + 1e-9:
        return ResultadoGrade(escolhido)
    return ResultadoGrade(
        melhor,
        f"grade elevada de R$ {escolhido:.2f} para R$ {melhor:.2f}: mesmo digito "
        f"da esquerda (fronteira R$ {teto_limiar:.2f}), sem ultrapassar concorrente local.",
    )


@dataclass(frozen=True)
class ResultadoPrecificacao:
    status: str
    preco_sugerido: float | None
    justificativa: str
    piso: float | None = None
    alvo: float | None = None
    tier: str | None = None
    custo_estimado: float | None = None


@dataclass(frozen=True)
class BandaBalcao:
    """Os tres precos que o vendedor ve no balcao."""
    vitrine: float           # preco cheio, da etiqueta
    cortesia: float | None   # concessao pequena, para o cliente que hesita
    cobrimos: float | None   # ultimo degrau, so contra preco citado pelo cliente
    ancora_pmc: float | None = None   # "de R$ X" so quando o desconto e' crivel
    motivo: str = ""


def _arredondar_para_grade_abaixo(valor: float, piso_valor: float,
                                  terminacoes: list[float]) -> float | None:
    """Maior preco da grade que nao passa de `valor` e respeita o piso.

    Desconto tem de cair numa terminacao (R$ 22,90 le como preco; R$ 22,71 le
    como calculo -- e calculo convida o cliente a negociar de novo).
    """
    candidatas = [
        reais + termo
        for reais in range(max(0, int(piso_valor) - 1), int(valor) + 2)
        for termo in terminacoes
    ]
    dentro = [v for v in candidatas if piso_valor - 1e-9 <= v <= valor + 1e-9]
    if dentro:
        return max(dentro)
    # Janela estreita demais entre piso e alvo (ex.: piso == alvo == 85,00, e a
    # grade nao tem terminacao ali). Sobe para a menor terminacao acima do piso:
    # perder o degrau inteiro seria pior que dar alguns centavos a menos de
    # desconto.
    acima = [v for v in candidatas if v >= piso_valor - 1e-9]
    return min(acima) if acima else None


def calcular_banda_balcao(
    preco_vitrine: float | None,
    piso_valor: float | None,
    params: dict[str, Any],
    menor_concorrente_local: float | None = None,
    teto_cmed: float | None = None,
) -> BandaBalcao | None:
    """Preco maximo e minimo que o vendedor pode praticar no balcao.

    Tres degraus NOMEADOS, nao um intervalo continuo: intervalo faz o vendedor
    ir direto ao minimo. A concessao e' decrescente (5%, depois o resto) para
    sinalizar que o limite chegou -- concessao de tamanho constante convida a
    mais uma rodada.

    - vitrine:  preco cheio (etiqueta, sistema, anuncio).
    - cortesia: concessao pequena para o cliente que hesita ou leva 2+ itens.
    - cobrimos: ultimo degrau. So sai quando o cliente CITA um preco concreto
      -- desconto reativo salva a venda; desconto preventivo so queima margem.

    `ancora_pmc` so vem preenchida quando o desconto contra o PMC fica numa
    faixa CRIVEL (ver [balcao] no TOML): anunciar "50% de desconto" destroi a
    credibilidade em vez de construi-la, porque o mercado inteiro pratica ~47%
    abaixo do PMC e o cliente que ja comprou o item sabe disso.

    Devolve None quando nao ha preco ou piso -- sem piso nao ha limite seguro.
    """
    cfg = params.get("balcao")
    if not cfg or not cfg.get("ativo") or preco_vitrine is None or piso_valor is None:
        return None

    terminacoes = params["grade"]["terminacoes"]
    piso_balcao = max(piso_valor, preco_vitrine * (1 - cfg.get("desconto_maximo_pct", 0.15)))

    cortesia = _arredondar_para_grade_abaixo(
        preco_vitrine * (1 - cfg.get("desconto_cortesia_pct", 0.05)),
        piso_balcao, terminacoes)
    if cortesia is not None and cortesia >= preco_vitrine:
        cortesia = None

    # "Cobrimos" encosta no menor concorrente local, nunca abaixo do piso.
    cobrimos = None
    if menor_concorrente_local and menor_concorrente_local > 0:
        alvo_cobrir = max(menor_concorrente_local, piso_balcao)
        if alvo_cobrir < preco_vitrine:
            cobrimos = _arredondar_para_grade_abaixo(alvo_cobrir, piso_balcao, terminacoes)
    if cobrimos is None:
        cobrimos = _arredondar_para_grade_abaixo(piso_balcao, piso_balcao, terminacoes)
    if cobrimos is not None and cobrimos >= preco_vitrine:
        cobrimos = None
    if cortesia is not None and cobrimos is not None and cobrimos >= cortesia:
        cortesia = None  # degraus colados nao ajudam ninguem

    ancora = None
    motivo = ""
    if teto_cmed and teto_cmed > preco_vitrine:
        desconto = 1 - preco_vitrine / teto_cmed
        minimo = cfg.get("ancora_pmc_desconto_min", 0.08)
        maximo = cfg.get("ancora_pmc_desconto_max", 0.30)
        if minimo <= desconto <= maximo:
            ancora = teto_cmed
            motivo = f"PMC R$ {teto_cmed:.2f} ({desconto:.0%} de desconto)"
        else:
            motivo = (f"PMC omitido: desconto de {desconto:.0%} fora da faixa crivel "
                      f"({minimo:.0%}-{maximo:.0%})")

    return BandaBalcao(vitrine=preco_vitrine, cortesia=cortesia, cobrimos=cobrimos,
                       ancora_pmc=ancora, motivo=motivo)


def _elevar_ao_piso_competitivo(
    alvo_valor: float,
    menor_concorrente_local: float | None,
    e_chamariz: bool,
    params: dict[str, Any],
    custo: float | None = None,
    referencia_mercado: float | None = None,
) -> tuple[float, bool, str]:
    """Nao ficar abaixo de quem esta do lado sem motivo comercial.

    Ver [piso_competitivo] em parametros.toml para a medicao que motivou a
    regra. Chamariz fica isento: la o preco abaixo do menor concorrente e
    decisao comercial deliberada, nao acidente de dado.

    Funcao separada porque roda em DOIS pontos de `aplicar_travas`: o caminho
    normal e o ramo DIVERGENCIA_BRICK_WEB, que retorna antes de chegar no
    primeiro.
    """
    cfg_comp = params.get("piso_competitivo", {})
    if not (cfg_comp.get("ativo") and not e_chamariz
            and menor_concorrente_local and menor_concorrente_local > 0):
        return alvo_valor, False, ""

    # SANIDADE DA ANCORA: um "menor concorrente" a uma ordem de grandeza do
    # custo nao e' concorrente, e' erro de EAN/apresentacao no site dele.
    # Elevar o preco ate la nao protege margem -- inventa preco.
    #
    # Medido em 12/08/2026, ao baixar a barra da ancora para 1-2 lojas: o
    # TRIDENT MENTA C/5 (custo R$ 1,81) tinha um unico "local" a R$ 28,81, que
    # e' preco de display, e o piso competitivo levou a sugestao de R$ 3,99
    # para R$ 51,49. Com 3+ lojas a winsorizacao e a camada 4b ja filtravam
    # esse tipo de erro; com 1-2 nao ha nada por baixo, entao a guarda tem de
    # estar aqui. O limite reusa o `markup_max` ja calibrado em
    # [mercado.brick_incoerente] (p99 do markup real = 4,46x; 6,0x deixa folga).
    markup_max = cfg_comp.get("markup_max_ancora", 0.0)
    if markup_max > 0 and custo and custo > 0 and menor_concorrente_local > custo * markup_max:
        return alvo_valor, False, ""

    # SEGUNDA GUARDA: nao subir muito acima da referencia CONSOLIDADA so porque
    # a unica loja local que a coleta enxergou naquele dia esta cara. O menor de
    # 1-2 observacoes e' uma amostra fina; `valor_referencia_mercado` ja combina
    # PMPF, Brick e todos os sites, entao e' a evidencia mais larga que existe.
    # Sem esta guarda (medido em 12/08/2026): TRAMADOL 50mg C/10 saia a R$ 39,99
    # contra referencia de R$ 27,87 (+43%), so porque um local estava alto.
    banda = cfg_comp.get("banda_maxima_sobre_referencia", 0.0)
    if banda > 0 and referencia_mercado and referencia_mercado > 0:
        menor_concorrente_local = min(menor_concorrente_local,
                                      referencia_mercado * (1 + banda))

    alvo_competitivo = menor_concorrente_local * (
        1 - cfg_comp.get("desconto_tolerado_pct", 0.0))
    if alvo_competitivo <= alvo_valor:
        return alvo_valor, False, ""
    return alvo_competitivo, True, (
        f" Preço elevado ao piso competitivo (R$ {alvo_competitivo:.2f}): o alvo"
        f" calculado ficava abaixo do menor concorrente da vizinhança e o item"
        f" não é chamariz -- desconto que nenhum concorrente local pratica não"
        f" atrai cliente, só reduz margem.")


def _limitar_ao_teto_competitivo(
    alvo_valor: float,
    piso_valor: float,
    maior_concorrente_local: float | None,
    e_chamariz: bool,
    params: dict[str, Any],
) -> tuple[float, str]:
    """Nao ficar acima de TODA a praca quando ha vizinhanca confiavel.

    Simetrico do piso competitivo. Medido em 2026-08-12 sobre o catalogo:
    156 itens (15,6% dos que tem >= 3 lojas locais) saiam mais caros que o
    MAIOR concorrente local -- 87 deles de Curva A, justamente os de maior
    visibilidade. A origem nao era o piso: era o teto frouxo do tier
    PROTECAO_MARGEM (`min(alvo_econ, referencia * 1,15)`), que somado ao
    premio de balcao ultrapassava o concorrente mais caro da vizinhanca.

    O piso continua vencendo: quando ele nao cabe abaixo do maior local, o
    preco fica onde esta e o status PISO_ACIMA_DO_MERCADO/CUSTO_ACIMA_DO_MERCADO
    segue sinalizando o caso (65 itens restantes na medicao). Chamariz fica de
    fora porque ja e' precificado por baixo, por decisao comercial.
    """
    cfg = params.get("teto_competitivo", {})
    if not (cfg.get("ativo") and not e_chamariz
            and maior_concorrente_local and maior_concorrente_local > 0):
        return alvo_valor, ""
    limite = maior_concorrente_local * (1 + cfg.get("folga_pct", 0.0))
    # `limite < piso_valor`: o piso vence sempre -- o item fica acima da praca e
    # o status honesto (PISO_/CUSTO_ACIMA_DO_MERCADO) segue sinalizando.
    if alvo_valor <= limite or limite < piso_valor:
        return alvo_valor, ""
    return limite, (
        f" Preço limitado ao teto competitivo (R$ {limite:.2f}): o alvo calculado"
        f" ficava acima de TODOS os concorrentes da vizinhança, o que não vende --"
        f" nenhuma margem se realiza em item que fica na prateleira.")


def aplicar_travas(
    *,
    custo: float | None,
    natureza_fiscal_item: str,
    tier: str,
    valor_referencia_mercado: float | None,
    divergencia_brick_web: bool,
    lucro_liquido_alvo_pct: float | None,
    teto_cmed: float | None,
    preco_atual: float | None,
    params: dict[str, Any],
    precos_concorrentes: list[float] | None = None,
    curva_abc: str | None = None,
    e_chamariz: bool = False,
    menor_concorrente_local: float | None = None,
    maior_concorrente_local: float | None = None,
    teto_competitivo_local: float | None = None,
    categoria: str | None = None,
) -> ResultadoPrecificacao:
    """Sempre tenta produzir um preco sugerido; so retorna None quando nao ha
    nenhuma base (nem custo nem mercado) ou o resultado seria matematicamente
    impossivel (piso > teto). Nos demais casos o status sinaliza o motivo de
    revisao, mas o preco vem preenchido.
    """
    if tier == "REVISAO_HUMANA":
        return ResultadoPrecificacao(
            "REVISAO_MANUAL", None, "Classificacao exige conferencia humana antes de definir preco.", tier=tier
        )

    if custo is None:
        if valor_referencia_mercado is None:
            return ResultadoPrecificacao(
                "REVISAO_MANUAL_SEM_CUSTO_E_SEM_MERCADO", None,
                "Sem custo validado por NF e sem referencia de mercado (Brick/web): nao ha base para sugerir preco.",
                tier=tier,
            )
        alvo_mercado = valor_referencia_mercado * 0.99
        grade = arredondar_grade(alvo_mercado, 0.0, teto_cmed, params["grade"]["terminacoes"],
                                 params, precos_concorrentes)
        # Custo ausente (ex.: item herdado da compra do ponto, sem NF): estima
        # um custo retroativo a partir do preco de mercado, so para nao deixar
        # o item "sem margem calculavel" no painel. Nao bloqueia -- e so
        # referencia ate a NF real de reposicao chegar (decisao 2026-08-05).
        pct_estimativa = pct_custo_estimado(natureza_fiscal_item, params)
        custo_estimado = (grade.preco or alvo_mercado) * pct_estimativa
        return ResultadoPrecificacao(
            "OK_SEM_CUSTO_BASE_MERCADO", grade.preco,
            "Sem custo validado por NF (ex.: item herdado de compra de ponto, sem NF de reposicao): "
            f"preco sugerido pela referencia de mercado; custo estimado em R$ {custo_estimado:.2f} "
            f"({pct_estimativa:.0%} do preco de mercado) apenas para calculo de margem no painel. "
            "Revisar com custo real assim que houver NF de reposicao.",
            alvo=alvo_mercado, tier=tier, custo_estimado=custo_estimado,
        )

    if lucro_liquido_alvo_pct is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_SEM_MARKUP", None, "Classificacao sem regra financeira cadastrada.", tier=tier
        )

    piso_valor = piso(custo, params, natureza_fiscal_item)
    alvo_econ = alvo_economico(custo, params, natureza_fiscal_item, lucro_liquido_alvo_pct)

    if teto_cmed is not None and piso_valor > teto_cmed:
        # O teto CMED e' lei: nao ha decisao a tomar, o preco E' o teto. Antes
        # isto saia como REVISAO_MANUAL e ficava parado numa fila esperando uma
        # decisao que nao existe. Decisao do usuario em 12/08/2026: "sempre que
        # ficar acima do teto, arrume para o teto".
        # Desce para a maior terminacao da grade que ainda cabe no teto (o teto
        # cru costuma ser R$ 12,34, que nao e' preco de etiqueta).
        grade_teto = arredondar_grade(
            teto_cmed, 0.01, teto_cmed, params["grade"]["terminacoes"], params, precos_concorrentes)
        preco_teto = grade_teto.preco if grade_teto.preco is not None else teto_cmed
        piso_min = piso_minimo(custo, params, natureza_fiscal_item)
        margem = 1 - custo / preco_teto if preco_teto else 0.0
        aviso = (" O preco fica abaixo ate do piso minimo (imposto + despesa variavel): "
                 "este item da PREJUIZO a cada venda -- renegociar a compra ou tirar do mix."
                 if preco_teto < piso_min else "")
        return ResultadoPrecificacao(
            "OK_TETO_CMED", preco_teto,
            f"Piso pelo custo (R$ {piso_valor:.2f}) ultrapassa o teto CMED "
            f"(R$ {teto_cmed:.2f}). Preco fixado no teto legal: margem bruta de "
            f"{margem * 100:.1f}%, abaixo da meta." + aviso,
            piso=piso_valor, alvo=preco_teto, tier=tier,
        )

    if divergencia_brick_web:
        alvo_valor = max(
            calcular_alvo(
                tier, valor_referencia_mercado, alvo_econ, precos_concorrentes, params, curva_abc,
                e_chamariz, categoria,
            ),
            piso_valor,
        )
        # O piso competitivo vale AQUI COM MAIS FORCA, nao menos: divergencia
        # significa que a referencia de mercado esta sob suspeita, e o menor
        # concorrente local observado e' a unica evidencia que sobrou de pe.
        # Sem esta chamada a protecao nao chega justamente onde o dado e' pior:
        # medido em 2026-08-11, 66,7% dos DIVERGENCIA_BRICK_WEB com ancora
        # ficavam ABAIXO do menor concorrente local, contra 11,8% dos OK.
        alvo_valor, piso_comp_aplicado, texto_comp = _elevar_ao_piso_competitivo(
            alvo_valor, menor_concorrente_local, e_chamariz, params, custo,
            valor_referencia_mercado)
        piso_grade = max(piso_valor, alvo_valor) if piso_comp_aplicado else piso_valor
        alvo_valor, texto_teto = _limitar_ao_teto_competitivo(
            alvo_valor, piso_valor, maior_concorrente_local, e_chamariz, params)
        texto_comp += texto_teto
        grade = arredondar_grade(alvo_valor, piso_grade, teto_cmed, params["grade"]["terminacoes"],
                                 params, precos_concorrentes)
        return ResultadoPrecificacao(
            "DIVERGENCIA_BRICK_WEB", grade.preco,
            "Mediana web e preco de mercado (Brick) divergem mais de 25%: possivel erro de apresentacao/EAN. "
            "Preco sugerido mantido apenas como referencia ate a divergencia ser conferida." + texto_comp,
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    if valor_referencia_mercado is not None and valor_referencia_mercado < custo:
        # Duas coisas MUITO diferentes caiam neste mesmo status ate 12/08/2026:
        #   - custo 39,89 e mercado 3,99 (SAB PROTEX C/12): 10x, e' a NF em pack
        #     vendida na unidade. Erro de DADO -- corrigir `fator_venda` em
        #     embalagens_produtos.csv, nunca digitar custo na mao.
        #   - custo 8,99 e mercado 7,55 (RISQUE ESM): 1,2x, nao ha erro nenhum,
        #     a compra e' que foi ruim. Nao adianta "investigar apresentacao".
        # O corte de 3x e' o mesmo ja calibrado em [mercado.brick_incoerente]:
        # a razao custo/mercado nao tem NADA entre 2x e 10x nesta base.
        razao_min = (params["mercado"].get("brick_incoerente") or {}).get("razao_min", 3.0)
        if custo >= valor_referencia_mercado * razao_min:
            grade = arredondar_grade(piso_valor, piso_valor, teto_cmed, params["grade"]["terminacoes"])
            return ResultadoPrecificacao(
                "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM", grade.preco,
                f"Custo (R$ {custo:.2f}) e {custo / valor_referencia_mercado:.0f}x o mercado "
                f"(R$ {valor_referencia_mercado:.2f}): a NF esta em embalagem diferente da venda. "
                f"fator_venda provavel: {fator_venda_provavel(custo, valor_referencia_mercado, params):g} "
                f"(custo unitario ficaria R$ {custo / fator_venda_provavel(custo, valor_referencia_mercado, params):.2f}). "
                "Conferir na NF e corrigir em embalagens_produtos.csv -- nao digitar custo na mao. "
                "Preco no piso tecnico ate a correcao.",
                piso=piso_valor, tier=tier,
            )
        # Compra ruim, nao erro de dado: menor margem possivel e segue o jogo.
        piso_min = piso_minimo(custo, params, natureza_fiscal_item)
        grade = arredondar_grade(piso_min, piso_min, teto_cmed, params["grade"]["terminacoes"],
                                 params, precos_concorrentes)
        if grade.preco is not None:
            return ResultadoPrecificacao(
                "OK_MARGEM_MINIMA_MERCADO", grade.preco,
                f"O mercado (R$ {valor_referencia_mercado:.2f}) esta ABAIXO do custo de NF "
                f"(R$ {custo:.2f}) -- compra ruim, nao erro de cadastro. Preco no piso minimo "
                f"(margem de {(1 - custo / grade.preco) * 100:.1f}%), acima do mercado por "
                "necessidade. Renegociar a compra ou tirar do mix.",
                piso=piso_min, alvo=piso_min, tier=tier,
            )

    alvo_valor = calcular_alvo(
        tier, valor_referencia_mercado, alvo_econ, precos_concorrentes, params, curva_abc,
        e_chamariz, categoria,
    )
    status_margem = "OK" if not e_chamariz else "OK_CHAMARIZ"
    justificativa_margem = "Preco dentro da politica da categoria, respeitando piso, teto e variacao maxima."
    if e_chamariz:
        justificativa_margem = (
            "Item selecionado como chamariz/KVI (Top vendidos do Brick + alta comparabilidade): "
            "preco alinhado ao menor concorrente elegivel, dentro do desconto maximo parametrizado, "
            "respeitando piso e teto."
        )
    if alvo_valor < piso_valor:
        # Mercado nao sustenta a margem-alvo da categoria, mas o piso ja garante
        # a contribuicao minima: vender no piso ainda e melhor que nao sugerir nada.
        alvo_valor = piso_valor
        status_margem = "OK_MARGEM_REDUZIDA"
        justificativa_margem = (
            "O alvo de mercado ficou abaixo do preco minimo tecnico: sugerido o piso "
            "(margem reduzida a contribuicao minima) em vez de bloquear a sugestao."
        )

    # PISO COMPETITIVO: nao ficar abaixo de quem esta do lado sem motivo.
    alvo_valor, piso_competitivo_aplicado, texto_comp = _elevar_ao_piso_competitivo(
        alvo_valor, menor_concorrente_local, e_chamariz, params, custo,
        valor_referencia_mercado)
    justificativa_margem += texto_comp
    # ...e vira piso DURO da grade, espelhando o que o teto competitivo ja faz
    # logo abaixo. Sem isto o arredondamento para a terminacao mais proxima
    # devolvia o item para BAIXO do menor concorrente local -- e justo por cima
    # da fronteira de digito esquerdo, que e' onde mais custa: piso de 7,21
    # virava 6,99 (-3,1%), o "7" que o cliente le vira "6". Medido em
    # 12/08/2026: 79 dos 362 itens elevados ao piso competitivo eram furados
    # assim pela propria grade que deveria respeita-lo.
    piso_grade = max(piso_valor, alvo_valor) if piso_competitivo_aplicado else piso_valor

    # TETO COMPETITIVO: simetrico do piso. Nao ficar acima de TODA a praca.
    alvo_valor, texto_teto = _limitar_ao_teto_competitivo(
        alvo_valor, piso_valor, maior_concorrente_local, e_chamariz, params)
    justificativa_margem += texto_teto
    # Quando o teto competitivo age, ele vira teto DURO da grade: sem isso o
    # arredondamento para a terminacao mais proxima devolveria o item para
    # acima do maior concorrente por alguns centavos.
    teto_grade = teto_cmed
    if texto_teto:
        teto_grade = alvo_valor if teto_cmed is None else min(teto_cmed, alvo_valor)
    # O piso competitivo CEDE para o teto: ele e' politica comercial, o teto CMED
    # e' lei. Sem esta linha o item fica sem preco nenhum (grade impossivel) --
    # dois casos em 12/08/2026, CISTEIL XPE e SILDENAFILA 50mg, onde o menor
    # concorrente local esta acima do PMC. Concorrente vendendo acima do teto
    # legal e' problema dele; o piso economico (custo) continua intocado.
    if teto_grade is not None and piso_grade > teto_grade:
        piso_grade = max(piso_valor, teto_grade)

    grade = arredondar_grade(alvo_valor, piso_grade, teto_grade, params["grade"]["terminacoes"],
                             params, precos_concorrentes)
    if grade.preco is None and piso_grade > piso_valor:
        # O piso competitivo endureceu a grade a ponto de nao sobrar terminacao
        # nenhuma entre ele e o teto. Ficar SEM preco e' pior do que ficar um
        # centavo abaixo do menor concorrente: ele e' politica comercial, nao
        # restricao dura. Cede e recalcula com o piso economico.
        grade = arredondar_grade(alvo_valor, piso_valor, teto_grade, params["grade"]["terminacoes"],
                                 params, precos_concorrentes)
    if grade.preco is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_GRADE_IMPOSSIVEL", None, grade.motivo or "Nenhum preco de grade valido.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    # preco_atual (praticado hoje) e reconhecidamente nao confiavel (cadastro
    # com erro de embalagem/apresentacao), entao NAO trava a sugestao. A trava
    # de bom senso compara contra o mercado (Brick/web), a ancora confiavel,
    # com tolerancia variavel por tier (config/parametros.toml).
    # O piso competitivo e' ancorado num concorrente LOCAL real e observado, que
    # e' evidencia melhor que `valor_referencia_mercado` (contaminado por Brick e
    # por sites remotos). Sem esta isencao a trava reclamaria justamente da
    # correcao que acabou de ser feita.
    if (valor_referencia_mercado is not None and valor_referencia_mercado > 0
            and not piso_competitivo_aplicado):
        variacao_maxima = params["trava"]["variacao_maxima_mercado_por_tier"].get(
            tier, params["trava"]["variacao_maxima_mercado_por_tier"]["PADRAO"]
        )
        variacao = abs(grade.preco / valor_referencia_mercado - 1)
        # A referencia consolidada mistura Brick nacional e sites remotos, e
        # quando ela esta contaminada esta trava faz o pior negocio possivel:
        # manda um humano conferir o preco CERTO contra um numero ERRADO.
        # Medido em 12/08/2026: TRIDENT MENTA C/5 (custo R$ 1,81) tinha um
        # "concorrente" a R$ 51,40 -- preco do display -- que levou a referencia
        # a R$ 28,81; a sugestao de R$ 4,99 estava certa e foi ela que caiu na
        # fila. Idem TALENTO 85g (custo R$ 6,40, referencia R$ 152,50, um preco
        # de caixa de bombom).
        # Duas testemunhas melhores absolvem, e basta UMA:
        #   1. VIZINHANCA -- preco entre o menor e o maior concorrente local:
        #      nao diverge do mercado que ESTE cliente compara;
        #   2. CUSTO -- a sugestao tem markup plausivel E a referencia nao tem.
        #      Nao basta a sugestao fazer sentido: se a referencia TAMBEM faz,
        #      quem esta fora e' a sugestao e a trava deve agir (e' o caso do
        #      teste de regressao com referencia a 1,05x o custo).
        # Decisao do usuario em 12/08/2026: "considere mais as farmacias
        # proximas e/ou os precos que fazem sentido com meu custo".
        cabe_na_vizinhanca = bool(
            menor_concorrente_local and maior_concorrente_local
            and menor_concorrente_local <= grade.preco <= maior_concorrente_local)
        markup_max = params.get("piso_competitivo", {}).get("markup_max_ancora", 0.0)
        coerente_com_custo = bool(
            custo and custo > 0 and markup_max > 0
            and piso_valor <= grade.preco <= custo * markup_max
            and not (custo <= valor_referencia_mercado <= custo * markup_max))
        if variacao > variacao_maxima and not (cabe_na_vizinhanca or coerente_com_custo):
            return ResultadoPrecificacao(
                "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE", grade.preco,
                f"Preco recomendado ({grade.preco:.2f}) varia {variacao * 100:.1f}% da referencia de "
                f"mercado ({valor_referencia_mercado:.2f}), acima do limite de {variacao_maxima * 100:.0f}% "
                f"do tier {tier}. Sugestao mantida para referencia; conferir antes de aplicar.",
                piso=piso_valor, alvo=alvo_valor, tier=tier,
            )

    # STATUS HONESTO: um preco acima de TODO concorrente local nao e' "OK".
    # Medido em 2026-08-07: 84 itens saiam mais caros que todos os locais com
    # status comecando em "OK_", o que escondia o problema de quem revisa. A
    # distincao importa porque a ACAO e' diferente em cada caso:
    #   custo > menor local  -> a compra e' que esta ruim: renegociar, nao subir preco
    #   custo <= menor local -> o piso e' que esta apertado para este item
    # DOIS tetos locais decidem este item, e a valvula abaixo precisa enxergar os
    # dois. `maior_concorrente_local` e' o teto largo; `teto_competitivo_local`
    # (mediana da vizinhanca + 5%, calculado no chamador) e' o apertado -- e era
    # so' o largo que chegava aqui. Quando o piso cheio caia ENTRE os dois, a
    # valvula nao disparava (o preco "cabia" embaixo do largo), mas o chamador
    # logo em seguida julgava contra o apertado e mandava para revisao manual com
    # um preco MAIS ALTO do que um custo maior teria produzido. Medido em
    # 2026-08-20: 58 itens presos em REVISAO_MANUAL_MERCADO_LOCAL_ABAIXO_DO_PISO
    # por causa dessa descontinuidade.
    teto_local_efetivo = maior_concorrente_local
    if maior_concorrente_local and teto_competitivo_local:
        teto_local_efetivo = min(maior_concorrente_local, teto_competitivo_local)
    if (teto_local_efetivo and grade.preco > teto_local_efetivo
            and not e_chamariz):
        # PRIMEIRO tenta caber no mercado com a MENOR margem possivel, antes de
        # desistir e devolver um preco que nao vende. O piso cheio carrega a
        # margem-alvo da DRE; o piso minimo carrega so imposto, despesa variavel
        # e a contribuicao em reais. Se com ele o item cabe embaixo do maior
        # concorrente local, esse e' o preco -- item parado nao realiza margem
        # nenhuma. Decisao do usuario em 12/08/2026.
        piso_min = piso_minimo(custo, params, natureza_fiscal_item)
        # Tenta o teto APERTADO e so entao o largo. Nao basta testar
        # `piso_min <= teto`: a grade pode nao achar terminacao comercial numa
        # janela estreita (caso real: piso 25.06 x teto 25.09) e devolver None.
        # Ali o teto largo ainda e' melhor que desistir da valvula e devolver o
        # preco cheio, que fica acima de todo mundo.
        grade_min = None
        for candidato_teto in (teto_local_efetivo, maior_concorrente_local):
            if not candidato_teto or piso_min > candidato_teto:
                continue
            teto_min = (candidato_teto if teto_cmed is None
                        else min(teto_cmed, candidato_teto))
            candidata = arredondar_grade(
                min(alvo_valor, teto_min), piso_min, teto_min,
                params["grade"]["terminacoes"], params, precos_concorrentes)
            if candidata.preco is not None:
                grade_min = candidata
                break
        if grade_min is not None:
            margem = 1 - custo / grade_min.preco
            return ResultadoPrecificacao(
                "OK_MARGEM_MINIMA_MERCADO", grade_min.preco,
                f"Piso cheio (R$ {piso_valor:.2f}) nao cabia abaixo do teto local "
                f"(R$ {teto_local_efetivo:.2f}). Preco recalculado no piso MINIMO "
                f"(R$ {piso_min:.2f}): margem bruta de {margem * 100:.1f}%, abaixo da meta da "
                f"categoria mas dentro do mercado. Item de baixa rentabilidade -- avaliar "
                f"compra ou substituicao no mix.",
                piso=piso_min, alvo=alvo_valor, tier=tier,
            )
        compra_ruim = bool(menor_concorrente_local and custo > menor_concorrente_local)
        if compra_ruim:
            return ResultadoPrecificacao(
                "CUSTO_ACIMA_DO_MERCADO", grade.preco,
                f"ATENCAO: o custo de aquisicao (R$ {custo:.2f}) ja supera o menor "
                f"concorrente da regiao (R$ {menor_concorrente_local:.2f}). O preco "
                f"sugerido fica acima de TODOS os concorrentes locais e nao vende. "
                f"A acao aqui e' RENEGOCIAR A COMPRA (caixa fechada, outro "
                f"distribuidor), nao subir o preco.",
                piso=piso_valor, alvo=alvo_valor, tier=tier,
            )
        return ResultadoPrecificacao(
            "PISO_ACIMA_DO_MERCADO", grade.preco,
            f"ATENCAO: o preco sugerido (R$ {grade.preco:.2f}) fica acima de TODOS os "
            f"concorrentes locais (maior: R$ {maior_concorrente_local:.2f}) porque o "
            f"piso tecnico nao cabe abaixo deles. Conferir custo e margem-alvo da "
            f"categoria antes de aplicar.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    return ResultadoPrecificacao(
        status_margem, grade.preco, justificativa_margem,
        piso=piso_valor, alvo=alvo_valor, tier=tier,
    )
