"""Motor economico: fiscal (segregacao), piso, tier, alvo, travas, grade.

Funcoes puras, sem I/O. Ver PLANO_SISTEMA_PRECIFICACAO.md Parte 2 (fiscal),
Parte 3.3 (piso/travas) e ESTUDO_PRECIFICACAO_DROGARIA.md (tier/alvo) para a
motivacao de cada regra.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    premissas = params["premissas"]
    return 1 - premissas["cartao_pct"] - premissas["despesas_fixas_pct"] - aliquota_simples_efetiva(params, natureza)


def divisor_alvo(params: dict[str, Any], natureza: str, lucro_liquido_alvo_pct: float) -> float:
    return divisor_piso(params, natureza) - lucro_liquido_alvo_pct


def piso(custo: float, params: dict[str, Any], natureza: str) -> float:
    piso_simples = custo / divisor_piso(params, natureza)
    piso_contribuicao = custo + params["premissas"]["contribuicao_minima_reais"]
    return max(piso_simples, piso_contribuicao)


def alvo_economico(custo: float, params: dict[str, Any], natureza: str, lucro_liquido_alvo_pct: float) -> float:
    return custo / divisor_alvo(params, natureza, lucro_liquido_alvo_pct)


TIERS = ("PRECO_IMAGEM", "PADRAO", "PROTECAO_MARGEM", "REVISAO_HUMANA")


def determinar_tier(
    papel_politica: str | None,
    curva_abc: str | None,
    n_concorrentes: int,
    cv: float | None,
    tem_brick: bool,
) -> str:
    if papel_politica == "REVISAO_HUMANA":
        return "REVISAO_HUMANA"

    e_imagem = (
        (n_concorrentes >= 4 and cv is not None and cv <= 0.15)
        or (curva_abc == "A" and (cv is None or cv <= 0.35))
        or papel_politica == "PRECO_IMAGEM"
    )
    e_protecao = (
        (n_concorrentes == 0 and not tem_brick)
        or curva_abc == "C"
        or (not tem_brick and n_concorrentes < 2)
        or papel_politica == "PROTECAO_MARGEM"
    )

    if e_protecao:
        # Falta de mercado ou giro fraco pesa mais que um sinal isolado de imagem:
        # sem evidencia solida, protege margem em vez de inventar competitividade
        # (ESTUDO_PRECIFICACAO_DROGARIA.md, secao 6).
        return "PROTECAO_MARGEM"
    if e_imagem:
        return "PRECO_IMAGEM"
    return "PADRAO"


def calcular_alvo(
    tier: str,
    valor_referencia_mercado: float | None,
    alvo_econ: float,
) -> float:
    if tier in ("PRECO_IMAGEM", "PADRAO") and valor_referencia_mercado is not None:
        return valor_referencia_mercado * 0.99
    if tier == "PROTECAO_MARGEM" and valor_referencia_mercado is not None:
        return min(alvo_econ, valor_referencia_mercado * 1.15)
    return alvo_econ


@dataclass(frozen=True)
class ResultadoGrade:
    preco: float | None
    motivo: str | None = None


def arredondar_grade(alvo: float, piso_valor: float, teto: float | None, terminacoes: list[float]) -> ResultadoGrade:
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
    return ResultadoGrade(min(opcoes, key=lambda v: abs(v - alvo)))


@dataclass(frozen=True)
class ResultadoPrecificacao:
    status: str
    preco_sugerido: float | None
    justificativa: str
    piso: float | None = None
    alvo: float | None = None
    tier: str | None = None


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
) -> ResultadoPrecificacao:
    """Sempre tenta produzir um preco sugerido; so retorna None quando nao ha
    nenhuma base (nem custo nem mercado) ou o resultado seria matematicamente
    impossivel (piso > teto). Nos demais casos o status sinaliza o motivo de
    revisao, mas o preco vem preenchido (conversa 2026-08-03).
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
        grade = arredondar_grade(alvo_mercado, 0.0, teto_cmed, params["grade"]["terminacoes"])
        return ResultadoPrecificacao(
            "OK_SEM_CUSTO_BASE_MERCADO", grade.preco,
            "Sem custo validado por NF: preco sugerido apenas pela referencia de mercado (Brick/web), "
            "sem checagem de margem. Confirme o custo assim que possivel.",
            alvo=alvo_mercado, tier=tier,
        )

    if lucro_liquido_alvo_pct is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_SEM_MARKUP", None, "Classificacao sem regra financeira cadastrada.", tier=tier
        )

    piso_valor = piso(custo, params, natureza_fiscal_item)
    alvo_econ = alvo_economico(custo, params, natureza_fiscal_item, lucro_liquido_alvo_pct)

    if teto_cmed is not None and piso_valor > teto_cmed:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_PISO_ACIMA_DO_TETO", None,
            "Piso minimo tecnico ultrapassa o teto CMED: nao se autoriza margem negativa.",
            piso=piso_valor, tier=tier,
        )

    if divergencia_brick_web:
        alvo_valor = max(calcular_alvo(tier, valor_referencia_mercado, alvo_econ), piso_valor)
        grade = arredondar_grade(alvo_valor, piso_valor, teto_cmed, params["grade"]["terminacoes"])
        return ResultadoPrecificacao(
            "DIVERGENCIA_BRICK_WEB", grade.preco,
            "Mediana web e preco de mercado (Brick) divergem mais de 25%: possivel erro de apresentacao/EAN. "
            "Preco sugerido mantido apenas como referencia ate a divergencia ser conferida.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    if valor_referencia_mercado is not None and valor_referencia_mercado < custo:
        grade = arredondar_grade(piso_valor, piso_valor, teto_cmed, params["grade"]["terminacoes"])
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM", grade.preco,
            "Mercado (Brick/web) abaixo do custo validado: investigar custo ou apresentacao. "
            "Preco sugerido no piso tecnico ate a investigacao.",
            piso=piso_valor, tier=tier,
        )

    alvo_valor = calcular_alvo(tier, valor_referencia_mercado, alvo_econ)
    status_margem = "OK"
    justificativa_margem = "Preco dentro da politica da categoria, respeitando piso, teto e variacao maxima."
    if alvo_valor < piso_valor:
        # Mercado nao sustenta a margem-alvo da categoria, mas o piso ja garante
        # a contribuicao minima: vender no piso ainda e melhor que nao sugerir nada.
        alvo_valor = piso_valor
        status_margem = "OK_MARGEM_REDUZIDA"
        justificativa_margem = (
            "O alvo de mercado ficou abaixo do preco minimo tecnico: sugerido o piso "
            "(margem reduzida a contribuicao minima) em vez de bloquear a sugestao."
        )

    grade = arredondar_grade(alvo_valor, piso_valor, teto_cmed, params["grade"]["terminacoes"])
    if grade.preco is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_GRADE_IMPOSSIVEL", None, grade.motivo or "Nenhum preco de grade valido.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    # preco_atual (praticado hoje) e reconhecidamente nao confiavel (cadastro
    # com erro de embalagem/apresentacao): nao trava mais a sugestao. A trava
    # de bom senso passa a comparar contra o mercado (Brick/web), a ancora
    # confiavel, com tolerancia variavel por tier (config/parametros.toml).
    if valor_referencia_mercado is not None and valor_referencia_mercado > 0:
        variacao_maxima = params["trava"]["variacao_maxima_mercado_por_tier"].get(
            tier, params["trava"]["variacao_maxima_mercado_por_tier"]["PADRAO"]
        )
        variacao = abs(grade.preco / valor_referencia_mercado - 1)
        if variacao > variacao_maxima:
            return ResultadoPrecificacao(
                "REVISAO_MANUAL_DIVERGENCIA_MERCADO_FORTE", grade.preco,
                f"Preco recomendado ({grade.preco:.2f}) varia {variacao * 100:.1f}% da referencia de "
                f"mercado ({valor_referencia_mercado:.2f}), acima do limite de {variacao_maxima * 100:.0f}% "
                f"do tier {tier}. Sugestao mantida para referencia; conferir antes de aplicar.",
                piso=piso_valor, alvo=alvo_valor, tier=tier,
            )

    return ResultadoPrecificacao(
        status_margem, grade.preco, justificativa_margem,
        piso=piso_valor, alvo=alvo_valor, tier=tier,
    )
