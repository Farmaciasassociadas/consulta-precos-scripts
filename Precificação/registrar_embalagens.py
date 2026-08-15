"""Cadastra fator_venda em embalagens_produtos.csv a partir das notas fiscais.

Um item comprado em fardo e vendido na unidade tem o custo da nota N vezes maior
que o unitario. `calcular_custos.py` ja sabe dividir por `fator_venda` -- o que
faltava era alguem preencher: o arquivo tinha 8 linhas.

Criterio deliberadamente estreito. O fator so entra quando DUAS fontes
independentes concordam: a razao entre o custo da nota e o `Preco Comp.Unit` do
ERP cai em cima de um inteiro, E esse inteiro e' o `Unidades por Cx.` do
cadastro. Razao sozinha nao basta -- Palmolive 85g da 7,17 e Dove da 5,10, que
nao sao embalagem nenhuma, sao desconto comercial e custo desatualizado.

Linha que ja existe nao e' tocada: as 8 atuais foram conferidas a mao.

Uso:
    python registrar_embalagens.py --planilha "...PRECIFICADO v6.xlsx" [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
sys.path.insert(0, str(APP))

NOTAS = Path(
    r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA\todas nfs.xls")
TOLERANCIA = 0.05


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import calcular_preco_sugerido as motor
    from config_app import ARQUIVO_EMBALAGENS_PRODUTOS
    from dados_compartilhados import carregar_embalagens_produtos, salvar_embalagem_produto
    from custo_das_notas import custo_por_ean, ler_entradas

    notas = custo_por_ean(ler_entradas(NOTAS), motor.normalizar_ean)
    df = pd.read_excel(args.planilha, sheet_name="Estoque precificado", dtype={"ean": str})
    df["k"] = df["ean"].map(motor.normalizar_ean)
    ja_cadastrados = {motor.normalizar_ean(e)
                      for e in carregar_embalagens_produtos(ARQUIVO_EMBALAGENS_PRODUTOS)}

    novos, ignorados = [], []
    for _, r in df.iterrows():
        registro = notas.get(r["k"])
        if not registro or not r["custo_unit_erp"] or r["custo_unit_erp"] <= 0:
            continue
        fator = registro["custo_nf"] / r["custo_unit_erp"]
        inteiro = round(fator)
        if inteiro < 2 or abs(fator - inteiro) > TOLERANCIA * inteiro:
            continue
        if r["k"] in ja_cadastrados:
            ignorados.append((r["ean"], r["descricao"], inteiro, "ja cadastrado a mao"))
            continue
        if int(r["un_cx"]) != inteiro:
            ignorados.append((r["ean"], r["descricao"], inteiro,
                              f"Unidades por Cx. do ERP diz {int(r['un_cx'])}, nota diz {inteiro}"))
            continue
        novos.append((str(r["ean"]), r["descricao"], inteiro, registro["custo_nf"],
                      r["custo_unit_erp"]))

    print(f"{len(novos)} fatores confirmados por duas fontes, {len(ignorados)} descartados")
    for ean, desc, fator, custo_nf, unit in novos:
        print(f"  +{fator:3d}x  {desc[:44]:46s} NF R$ {custo_nf:8.2f} / un R$ {unit:6.2f}")
        if not args.dry_run:
            salvar_embalagem_produto(
                ARQUIVO_EMBALAGENS_PRODUTOS, ean, "UNIDADE", fator,
                conteudo_embalagem=fator,
                origem=f"nf_x_unidades_por_cx_{fator}un_20260815")
    print()
    for ean, desc, fator, motivo in ignorados:
        print(f"  --     {desc[:44]:46s} fator {fator} descartado: {motivo}")
    if args.dry_run:
        print("\n(dry-run: nada gravado)")


if __name__ == "__main__":
    main()
