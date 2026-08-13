"""Selecao automatica de itens chamariz/KVI (Key Value Items).

Um item chamariz busca empatar ou ficar levemente abaixo do menor concorrente
elegivel -- excecao estrategica controlada, lista pequena e revisada
periodicamente (nao e o padrao do catalogo; ver DOCX "Diagnostico e Plano
v4", Secao 4, e "Motor de Precificacao v5", Secao 2).

Selecao 100% automatica e reproduzivel, sem curadoria manual: usa a posicao
no ranking de mais vendidos do Brick (`preco_brick.posicao_mais_vendidos`,
1 = mais vendido) como proxy de giro/recorrencia real -- e dado de auditoria
de mercado real, nao estimativa -- cruzado com comparabilidade (numero de
concorrentes com preco valido na ultima rodada) e dispersao (CV): quanto
menor a dispersao entre concorrentes, mais padronizado/comparavel o item e.

Funcoes puras: recebem candidatos ja montados (de fora, via SQL), devolvem a
selecao. Nenhum I/O acontece aqui.
"""
from __future__ import annotations

from dataclasses import dataclass


PESOS_PADRAO = {"giro": 0.40, "margem": 0.30, "comparabilidade": 0.20, "dispersao": 0.10}


@dataclass(frozen=True)
class CandidatoChamariz:
    ean: str
    segmento: str  # RX / GEN / SIM / NMED (preco_brick.segmento)
    posicao_mais_vendidos: int  # 1 = mais vendido no segmento
    n_concorrentes: int
    cv: float | None
    # Margem bruta que SOBRA depois do desconto de chamariz, isto e, calculada
    # sobre o menor concorrente elegivel e nao sobre o preco sugerido. E' o que
    # separa "item que atrai cliente e ainda paga a conta" de "item que so
    # queima margem". None = desconhecida (custo ou concorrencia faltando).
    margem_pos_desconto: float | None = None


@dataclass(frozen=True)
class ItemSelecionado:
    ean: str
    segmento: str
    score: float


def calcular_score(
    candidato: CandidatoChamariz,
    posicao_max: int,
    pesos: dict[str, float] | None = None,
    margem_referencia: float = 0.35,
) -> float:
    """Score 0-1 combinando giro, margem que sobra, comparabilidade e dispersao.

    A componente de MARGEM entrou em 12/08/2026 a pedido do usuario ("escolha 7
    dos mais lucrativos e vendidos"). Ela usa a margem que resta DEPOIS do
    desconto de chamariz: entre dois itens de giro parecido, o chamariz certo e
    o que ainda paga a conta ao ser rebaixado. Sem ela, o item de margem magra
    e giro alto ganhava a disputa e virava desconto sobre desconto.

    `margem_referencia` normaliza a margem em 0-1 (0,35 = margem que satura a
    componente). Margem desconhecida recebe 0,5, o mesmo tratamento neutro que
    o CV ausente ja recebia -- nunca 0, que eliminaria o item so por falta de
    dado de custo.
    """
    p = {**PESOS_PADRAO, **(pesos or {})}
    posicao = max(1, min(candidato.posicao_mais_vendidos, posicao_max))
    giro_norm = 1 - (posicao - 1) / max(1, posicao_max - 1)
    comparabilidade_norm = min(candidato.n_concorrentes, 9) / 9
    dispersao_norm = 1 - min(candidato.cv, 1.0) if candidato.cv is not None else 0.5
    if candidato.margem_pos_desconto is None:
        margem_norm = 0.5
    else:
        margem_norm = max(0.0, min(candidato.margem_pos_desconto / margem_referencia, 1.0))
    return (p["giro"] * giro_norm
            + p["margem"] * margem_norm
            + p["comparabilidade"] * comparabilidade_norm
            + p["dispersao"] * dispersao_norm)


def selecionar_chamariz(
    candidatos: list[CandidatoChamariz],
    top_n_global: int,
    posicao_max: int = 3000,
    n_concorrentes_minimo: int = 3,
    pesos: dict[str, float] | None = None,
    margem_minima: float = 0.0,
) -> list[ItemSelecionado]:
    """Seleciona os Top N do catalogo INTEIRO, ordenados por score.

    Sem cota por segmento (mudanca de 12/08/2026). A cota antiga -- top 8 de
    cada um dos 4 segmentos, 32 itens -- obrigava a rebaixar 8 itens de NMED
    mesmo quando nenhum deles era conhecido do bairro, so para preencher a
    cota. Imagem de preco se forma sobre poucos itens que o cliente sabe de cor
    (Hamilton & Chernev, JM 2013), e esses poucos nao se distribuem em cotas
    iguais por categoria.

    Exige `n_concorrentes_minimo` concorrentes com preco valido: sem isso,
    "empatar com o menor concorrente" nao tem base solida o suficiente para
    virar uma politica automatica de preco. `margem_minima` descarta item que
    ficaria sem margem nenhuma depois do desconto -- chamariz e' investimento
    em trafego, nao doacao.
    """
    elegiveis = [
        c for c in candidatos
        if c.n_concorrentes >= n_concorrentes_minimo
        and (c.margem_pos_desconto is None or c.margem_pos_desconto >= margem_minima)
    ]
    pontuados = sorted(
        ((c, calcular_score(c, posicao_max, pesos)) for c in elegiveis),
        key=lambda par: (-par[1], par[0].ean),
    )
    return [ItemSelecionado(ean=c.ean, segmento=c.segmento, score=score)
            for c, score in pontuados[:top_n_global]]


def alvo_chamariz(precos_concorrentes: list[float], desconto_maximo_pct: float) -> float | None:
    """Preco-alvo do chamariz: empata ou fica levemente abaixo do menor
    concorrente elegivel. `desconto_maximo_pct` e um limite parametrizado
    (config/parametros.toml) -- nunca um desconto livre. Piso economico e
    teto CMED continuam sendo aplicados por fora (aplicar_travas), como para
    qualquer outro item."""
    if not precos_concorrentes:
        return None
    return min(precos_concorrentes) * (1 - desconto_maximo_pct)
