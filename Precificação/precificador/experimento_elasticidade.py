"""Fase 4: monta o experimento que mede elasticidade de verdade.

Tudo no motor hoje usa DISPERSAO DE PRECO como proxy de sensibilidade (o CV
decide tier, peso do Brick e ate a lista de chamariz). Proxy nao e medida. Com
venda propria acumulada da para medir, e o desenho abaixo e o mesmo de Anderson
& Simester (Quantitative Marketing and Economics, 2003) na escala de uma loja.

DESENHO CRUZADO (cross-over), nao A/B simples: cada par de itens comparaveis
troca de lado na metade do periodo. Sem a troca, qualquer sazonalidade ou
ruptura de estoque no meio do teste vira "efeito de preco" -- e numa farmacia
recem-aberta, com demanda ainda subindo, um A/B puro mediria a rampa, nao o
preco.

    bloco 1 (semanas 1-4): item A com +delta, item B sem mexer
    bloco 2 (semanas 5-8): item A sem mexer, item B com +delta

O par e formado dentro da MESMA subcategoria e em faixa de preco proxima, para
que os dois enfrentem o mesmo cliente e a mesma concorrencia.

Uso:
    python experimento_elasticidade.py            # gera o plano
    python experimento_elasticidade.py --delta 0.05

Saida: experimento_elasticidade.csv, com o preco de cada item em cada bloco.
Depois de rodar, comparar UNIDADES VENDIDAS (nao faturamento) entre blocos.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

import db
from engine import economico, parametros

SAIDA = Path(__file__).parent / "experimento_elasticidade.csv"


def candidatos(conn: sqlite3.Connection, rodada_id: int) -> list[sqlite3.Row]:
    """Itens elegiveis: Curva A (giro real), 3+ concorrentes locais medidos,
    preco e custo conhecidos, e status limpo.

    Curva A porque so ali ha unidades suficientes em 4 semanas para o teste ter
    poder estatistico -- item de cauda longa que vende 2 por mes nao mede nada.
    """
    conn.row_factory = sqlite3.Row
    return conn.execute("""
        SELECT r.ean, r.descricao, r.categoria_provisoria, r.custo, r.preco_sugerido,
               r.n_concorrentes, r.piso, b.curva_abc
        FROM recomendacao r
        JOIN preco_brick b ON b.ean = r.ean
        WHERE r.rodada_id = ? AND b.curva_abc = 'A'
          AND r.preco_sugerido IS NOT NULL AND r.custo IS NOT NULL
          AND r.n_concorrentes >= 3 AND r.status LIKE 'OK%'
        ORDER BY r.categoria_provisoria, r.preco_sugerido
    """, (rodada_id,)).fetchall()


def formar_pares(itens: list[sqlite3.Row], max_pares: int) -> list[tuple]:
    """Pareia vizinhos na mesma subcategoria e faixa de preco proxima (<= 25%).

    Vizinhos na lista ja ordenada por (categoria, preco): o par mais parecido
    que existe sem inventar um modelo de similaridade.
    """
    pares = []
    usados = set()
    for a, b in zip(itens, itens[1:]):
        if a["ean"] in usados or b["ean"] in usados:
            continue
        if a["categoria_provisoria"] != b["categoria_provisoria"]:
            continue
        if not a["preco_sugerido"] or abs(b["preco_sugerido"] / a["preco_sugerido"] - 1) > 0.25:
            continue
        pares.append((a, b))
        usados.update({a["ean"], b["ean"]})
        if len(pares) >= max_pares:
            break
    return pares


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--delta", type=float, default=0.03,
                    help="variacao de preco testada (0.03 = 3%%)")
    ap.add_argument("--pares", type=int, default=40, help="numero de pares (80 itens)")
    args = ap.parse_args()

    params = parametros.carregar()
    conn = db.connect()
    rodada_id = conn.execute("SELECT MAX(id) FROM rodada").fetchone()[0]
    itens = candidatos(conn, rodada_id)
    pares = formar_pares(itens, args.pares)

    linhas = []
    for i, (a, b) in enumerate(pares, start=1):
        for papel, item in (("A", a), ("B", b)):
            base = item["preco_sugerido"]
            tratado = base * (1 + args.delta)
            # O piso continua valendo mesmo em experimento: nao se testa
            # elasticidade vendendo abaixo da contribuicao minima.
            grade = economico.arredondar_grade(
                tratado, item["piso"] or item["custo"], None,
                params["grade"]["terminacoes"], params)
            tratado = grade.preco or tratado
            linhas.append({
                "par": i, "papel": papel, "ean": item["ean"],
                "descricao": item["descricao"], "categoria": item["categoria_provisoria"],
                "custo": round(item["custo"], 2), "preco_base": round(base, 2),
                "preco_tratado": round(tratado, 2),
                "bloco_1_semanas_1_a_4": round(tratado if papel == "A" else base, 2),
                "bloco_2_semanas_5_a_8": round(base if papel == "A" else tratado, 2),
            })

    with open(SAIDA, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(linhas)

    print(f"{len(pares)} pares ({len(linhas)} itens) em {SAIDA.name}")
    print(f"delta testado: {args.delta:+.0%} | duracao: 8 semanas (2 blocos de 4)")
    print()
    print("Como ler o resultado, ao fim das 8 semanas:")
    print("  1. Some as UNIDADES vendidas de cada item em cada bloco (nao o faturamento:")
    print("     faturamento sobe com o preco e esconde a queda de volume).")
    print("  2. Elasticidade = (variacao % de unidades) / (variacao % de preco), por item.")
    print("  3. Agregue por categoria -- item a item o ruido domina com 4 semanas.")
    print()
    print("Como usar depois: substituir o CV por elasticidade medida em")
    print("economico.determinar_tier e recalibrar [grade.limiar].tolerancia_pct")
    print("e [ranking].rank_alvo_por_curva com evidencia em vez de proxy.")
    conn.close()


if __name__ == "__main__":
    main()
