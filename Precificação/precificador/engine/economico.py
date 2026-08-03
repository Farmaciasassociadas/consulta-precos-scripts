"""Motor economico: fiscal (segregacao), piso, tier, alvo, travas, grade.

Funcoes puras, sem I/O. Ver PLANO_SISTEMA_PRECIFICACAO.md Parte 2 (fiscal),
Parte 3.3 (piso/travas) e ESTUDO_PRECIFICACAO_DROGARIA.md (tier/alvo) para a
motivacao de cada regra.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
    if custo is None:
        return ResultadoPrecificacao("REVISAO_MANUAL_SEM_CUSTO_VALIDADO", None, "Sem custo validado por NF.")

    if tier == "REVISAO_HUMANA":
        return ResultadoPrecificacao(
            "REVISAO_MANUAL", None, "Classificacao exige conferencia humana antes de definir preco.", tier=tier
        )

    if lucro_liquido_alvo_pct is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_SEM_MARKUP", None, "Classificacao sem regra financeira cadastrada.", tier=tier
        )

    if divergencia_brick_web:
        return ResultadoPrecificacao(
            "DIVERGENCIA_BRICK_WEB", None,
            "Mediana web e preco de mercado (Brick) divergem mais de 25%: possivel erro de apresentacao/EAN.",
            tier=tier,
        )

    if valor_referencia_mercado is not None and valor_referencia_mercado < custo:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_CUSTO_OU_EMBALAGEM", None,
            "Mercado (Brick/web) abaixo do custo validado: investigar custo ou apresentacao.", tier=tier,
        )

    piso_valor = piso(custo, params, natureza_fiscal_item)
    alvo_econ = alvo_economico(custo, params, natureza_fiscal_item, lucro_liquido_alvo_pct)
    alvo_valor = calcular_alvo(tier, valor_referencia_mercado, alvo_econ)

    if teto_cmed is not None and piso_valor > teto_cmed:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_PISO_ACIMA_DO_TETO", None,
            "Piso minimo tecnico ultrapassa o teto CMED: nao se autoriza margem negativa.",
            piso=piso_valor, tier=tier,
        )

    if alvo_valor < piso_valor:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_PISO_ACIMA_DO_MERCADO", None,
            "O alvo de mercado ficou abaixo do preco minimo tecnico.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    grade = arredondar_grade(alvo_valor, piso_valor, teto_cmed, params["grade"]["terminacoes"])
    if grade.preco is None:
        return ResultadoPrecificacao(
            "REVISAO_MANUAL_GRADE_IMPOSSIVEL", None, grade.motivo or "Nenhum preco de grade valido.",
            piso=piso_valor, alvo=alvo_valor, tier=tier,
        )

    if preco_atual is not None and preco_atual > 0:
        variacao_maxima = params["trava"]["variacao_maxima_pct"]
        variacao = abs(grade.preco / preco_atual - 1)
        if variacao > variacao_maxima:
            return ResultadoPrecificacao(
                "REVISAO_MANUAL_VARIACAO_ALTA", None,
                f"Preco recomendado ({grade.preco:.2f}) varia {variacao * 100:.1f}% do praticado hoje "
                f"({preco_atual:.2f}), acima do limite de {variacao_maxima * 100:.0f}% por rodada.",
                piso=piso_valor, alvo=alvo_valor, tier=tier,
            )

    return ResultadoPrecificacao(
        "OK", grade.preco, "Preco dentro da politica da categoria, respeitando piso, teto e variacao maxima.",
        piso=piso_valor, alvo=alvo_valor, tier=tier,
    )
