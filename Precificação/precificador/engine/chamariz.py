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


@dataclass(frozen=True)
class CandidatoChamariz:
    ean: str
    segmento: str  # RX / GEN / SIM / NMED (preco_brick.segmento)
    posicao_mais_vendidos: int  # 1 = mais vendido no segmento
    n_concorrentes: int
    cv: float | None


@dataclass(frozen=True)
class ItemSelecionado:
    ean: str
    segmento: str
    score: float


def calcular_score(candidato: CandidatoChamariz, posicao_max: int) -> float:
    """Score 0-1: 50% giro (posicao no Brick), 30% comparabilidade (n de
    concorrentes), 20% dispersao (CV baixo = mais confiavel/comparavel)."""
    posicao = max(1, min(candidato.posicao_mais_vendidos, posicao_max))
    giro_norm = 1 - (posicao - 1) / max(1, posicao_max - 1)
    comparabilidade_norm = min(candidato.n_concorrentes, 9) / 9
    dispersao_norm = 1 - min(candidato.cv, 1.0) if candidato.cv is not None else 0.5
    return 0.5 * giro_norm + 0.3 * comparabilidade_norm + 0.2 * dispersao_norm


def selecionar_chamariz(
    candidatos: list[CandidatoChamariz],
    top_n_por_segmento: int,
    posicao_max: int = 3000,
    n_concorrentes_minimo: int = 3,
) -> list[ItemSelecionado]:
    """Seleciona o Top N por segmento (RX/GEN/SIM/NMED), ordenado por score.

    Exige `n_concorrentes_minimo` concorrentes com preco valido: sem isso,
    "empatar com o menor concorrente" nao tem base solida o suficiente para
    virar uma politica automatica de preco.
    """
    elegiveis = [c for c in candidatos if c.n_concorrentes >= n_concorrentes_minimo]
    por_segmento: dict[str, list[CandidatoChamariz]] = {}
    for c in elegiveis:
        por_segmento.setdefault(c.segmento, []).append(c)

    selecionados: list[ItemSelecionado] = []
    for segmento, itens in por_segmento.items():
        pontuados = sorted(
            ((c, calcular_score(c, posicao_max)) for c in itens),
            key=lambda par: -par[1],
        )
        for c, score in pontuados[:top_n_por_segmento]:
            selecionados.append(ItemSelecionado(ean=c.ean, segmento=segmento, score=score))
    return selecionados


def alvo_chamariz(precos_concorrentes: list[float], desconto_maximo_pct: float) -> float | None:
    """Preco-alvo do chamariz: empata ou fica levemente abaixo do menor
    concorrente elegivel. `desconto_maximo_pct` e um limite parametrizado
    (config/parametros.toml) -- nunca um desconto livre. Piso economico e
    teto CMED continuam sendo aplicados por fora (aplicar_travas), como para
    qualquer outro item."""
    if not precos_concorrentes:
        return None
    return min(precos_concorrentes) * (1 - desconto_maximo_pct)
