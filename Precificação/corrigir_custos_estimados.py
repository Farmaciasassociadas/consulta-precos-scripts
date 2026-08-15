"""Troca custo ESTIMADO por entrada real do ERP em custo_produtos.csv.

Quando nao ha nota, o motor preenche o custo com "50% do preco de venda" e grava
essa marca na descricao. O MiniPreco le esse valor como se fosse custo e mostra
margem na tela -- foi assim que a toalha Qualybless apareceu com 17,7% de margem
enquanto a entrada real (R$ 10,03) diz que ela sai abaixo do custo a R$ 9,99.

Onde o relatorio de estoque do ERP tem `Ult. Prc. Entrada` > 0, essa entrada e'
compra registrada e vale mais que a regra de bolso. Onde nao tem, a estimativa
fica -- e continua marcada como estimativa.

Nao mexe em linha com nota (num_notas > 0): NF manda sobre tudo.

Uso:
    python corrigir_custos_estimados.py --planilha "...v7.xlsx" [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
sys.path.insert(0, str(APP))

CAMPOS = ["ean", "descricao", "custo_medio", "qtd_total", "num_notas", "data_ultima_nota"]
MARCA = "(ESTIMADO:"


def limpar_descricao(descricao: str) -> str:
    return descricao.split(MARCA, 1)[0].strip()


def _num(valor) -> float | None:
    """Celula vazia do pandas vira NaN, e `not nan` e' False: sem isto todo item
    SEM preco sugerido escapa da guarda que compara custo com mercado."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if v != v or v <= 0 else v


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import calcular_preco_sugerido as motor
    from config_app import ARQUIVO_CUSTOS
    from dados_compartilhados import _csv_texto, _trocar_atomicamente, trava_dados

    df = pd.read_excel(args.planilha, sheet_name="Estoque precificado", dtype={"ean": str})
    # NAO e' a `Ult. Prc. Entrada` crua: ela vem na unidade da nota e as vezes e'
    # fardo (Coca-Cola 2L a R$ 61,02) ou fracao (Allexofedrin a R$ 2,13). O
    # `custo_real` da planilha ja passou pelo cruzamento com o Preco Comp.Unit,
    # pela conversao caixa->unidade e pela validacao contra as notas.
    web = pd.read_csv(Path(__file__).resolve().parent / "dados" / "pesquisa_web_2026-08-14.csv",
                      sep=";", decimal=",", dtype={"ean": str}, encoding="utf-8-sig")
    pesquisado = {motor.normalizar_ean(r["ean"]): float(r["preco_mercado_max"])
                  for _, r in web.iterrows()}

    entrada, bloqueados = {}, 0
    for _, r in df.iterrows():
        custo = r["custo_real"]
        if not custo or custo <= 0:
            continue
        # Guarda: o teto do custo e' o preco que o MERCADO cobra pelo item.
        # Comparar com o preco da propria loja nao serve -- quando o cadastro
        # esta em base de display os dois campos sobem juntos e o disparate passa
        # (Paracetamol C/10 com "custo" de R$ 235,04 e preco de venda coerente
        # com ele). So vale quando ha concorrente coletado: sem mercado, a
        # sugestao e' o proprio custo x markup e a comparacao seria circular.
        # Teto: preco coletado dos concorrentes ou, quando a coleta nao trouxe
        # nada, a faixa levantada a mao na web -- que e' observacao de mercado
        # igual, so que manual. Sem nenhuma das duas a sugestao vira custo x
        # markup e a comparacao seria circular.
        teto = pesquisado.get(motor.normalizar_ean(r["ean"]))
        if teto is None and (_num(r["concorrentes_com_preco"]) or 0) >= 1:
            teto = _num(r["preco_sugerido"])
        if (r["custo_validado"] in ("SEM NF - CUSTO IMPOSSIVEL", "CONFERIR EMBALAGEM")
                or teto is None or custo > teto):
            bloqueados += 1
            continue
        entrada[motor.normalizar_ean(r["ean"])] = float(custo)

    with open(ARQUIVO_CUSTOS, encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))

    hoje = datetime.now().strftime("%d/%m/%Y")
    trocados, sem_entrada, subestimados = [], 0, 0
    for linha in linhas:
        if MARCA not in (linha["descricao"] or ""):
            continue
        real = entrada.get(motor.normalizar_ean(linha["ean"]))
        if not real:
            sem_entrada += 1
            continue
        antigo = float(linha["custo_medio"] or 0)
        if abs(real - antigo) < 0.005:
            continue
        if antigo < real * 0.98:
            subestimados += 1
        linha["descricao"] = (f"{limpar_descricao(linha['descricao'])} "
                              f"(CUSTO DO ERP validado em {hoje}, sem NF no periodo)")
        linha["custo_medio"] = f"{real:.4f}"
        trocados.append((linha["ean"], limpar_descricao(linha["descricao"]), antigo, real))

    print(f"{len(trocados)} custos estimados trocados pelo custo validado do ERP "
          f"({subestimados} estavam subestimados); {sem_entrada} continuam estimados por "
          f"falta de custo confiavel; {bloqueados} itens bloqueados pela guarda "
          f"(custo acima do preco de venda ou embalagem por conferir)")
    for ean, desc, antigo, real in sorted(trocados, key=lambda t: -abs(t[3] - t[2]))[:12]:
        print(f"  {desc[:44]:46s} R$ {antigo:7.2f} -> R$ {real:7.2f}")

    if args.dry_run:
        print("\n(dry-run: nada gravado)")
        return
    shutil.copy2(ARQUIVO_CUSTOS, ARQUIVO_CUSTOS.with_name(
        f"custo_produtos_backup_{datetime.now():%Y%m%d_%H%M%S}_pre_troca_estimado.csv"))
    with trava_dados(ARQUIVO_CUSTOS.parent):
        _trocar_atomicamente(ARQUIVO_CUSTOS, _csv_texto(CAMPOS, linhas), "utf-8-sig")
    print(f"Gravado: {ARQUIVO_CUSTOS}")


if __name__ == "__main__":
    main()
