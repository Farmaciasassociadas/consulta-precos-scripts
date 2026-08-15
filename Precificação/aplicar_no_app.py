"""Leva o resultado da analise do estoque para a base viva do app.

Tres gravacoes, todas com backup e todas idempotentes:

  1. eans.txt          -- reordenado. A ordem do arquivo E' a ordem da coleta
                          (io_dados.carregar_eans devolve a lista na ordem lida),
                          entao por o item de maior estoque parado no topo muda o
                          que a proxima varredura cobre primeiro. Nenhuma linha e'
                          removida e o sufixo ";preco" e' preservado.
  2. eans_negativos.csv -- marca propria que ficou de fora da lista.
  3. categorias_produtos.csv -- classificacao auditada contra classe terapeutica,
                          Brick e PMC. NAO toca em quem tem origem
                          "manual_minipreco": decisao humana manda.

Uso:
    python aplicar_no_app.py --planilha "...PRECIFICADO v3.xlsx" [--dry-run]
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

ORIGEM = "estoque_erp_2026-08-14"


def backup(caminho: Path) -> Path:
    destino = caminho.with_name(
        f"{caminho.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}_pre_estoque_erp{caminho.suffix}")
    shutil.copy2(caminho, destino)
    return destino


def priorizar_eans(df: pd.DataFrame, marca_propria: set[str], normalizar, arquivo: Path,
                   dry_run: bool) -> str:
    """Sobe para o topo de eans.txt quem nao tem NENHUM concorrente coletado,
    ordenado pelo dinheiro parado na prateleira."""
    valor = {}
    for _, r in df.iterrows():
        if r["concorrentes_com_preco"] or r["k"] in marca_propria:
            continue
        custo = r["custo_real"] if r["custo_real"] and r["custo_real"] > 0 else 0.0
        valor[r["k"]] = float(custo) * float(r["estoque"] or 0)

    linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
    # Item que nem esta em eans.txt nunca sera coletado: reordenar nao resolve,
    # tem de entrar na lista.
    presentes = {normalizar(l.split(";", 1)[0]) for l in linhas}
    novos = [r["ean"] for _, r in df.iterrows()
             if r["k"] in valor and r["k"] not in presentes]
    linhas.extend(str(e) for e in novos)
    # -valor ordena decrescente; a chave secundaria preserva a ordem original
    # dentro de cada grupo, para a fila nao embaralhar a cada rodada.
    def chave(item: tuple[int, str]) -> tuple[int, float, int]:
        i, linha = item
        k = normalizar(linha.split(";", 1)[0])
        return (0, -valor[k], i) if k in valor else (1, 0.0, i)

    ordenadas = [linha for _, linha in sorted(enumerate(linhas), key=chave)]
    assert sorted(ordenadas) == sorted(linhas), "reordenacao nao pode perder linha"
    topo = sum(1 for l in ordenadas[:len(valor)] if normalizar(l.split(";", 1)[0]) in valor)
    if not dry_run:
        backup(arquivo)
        arquivo.write_text("\n".join(ordenadas) + "\n", encoding="utf-8")
    return (f"eans.txt: {len(linhas)} linhas ({len(novos)} acrescentadas), {topo} sem coleta "
            f"no topo (R$ {sum(valor.values()):,.0f} de estoque parado)")


def completar_marca_propria(faltantes: list[str], arquivo: Path, dry_run: bool) -> str:
    if not faltantes:
        return "eans_negativos.csv: nada a acrescentar"
    if not dry_run:
        backup(arquivo)
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        with open(arquivo, "a", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows([[agora, ean] for ean in faltantes])
    return f"eans_negativos.csv: +{len(faltantes)} EAN(s) de marca propria ({', '.join(faltantes)})"


def gravar_categorias(df: pd.DataFrame, normalizar, dry_run: bool) -> str:
    from config_app import ARQUIVO_CATEGORIAS_DISPONIVEIS, ARQUIVO_CATEGORIAS_PRODUTOS
    from dados_compartilhados import carregar_opcoes_categoria, salvar_categorias_produtos

    permitidas = tuple(carregar_opcoes_categoria(ARQUIVO_CATEGORIAS_DISPONIVEIS))
    atuais = pd.read_csv(ARQUIVO_CATEGORIAS_PRODUTOS, encoding="utf-8-sig",
                         dtype=str).fillna("")
    # Chave existente vence a nossa: o arquivo grava o EAN preenchido a 13 e
    # gravar a versao crua criaria uma segunda linha para o mesmo produto.
    por_norm = {normalizar(r["ean"]): r["ean"] for _, r in atuais.iterrows()}
    intocaveis = {normalizar(r["ean"]) for _, r in atuais.iterrows()
                  if r["origem"] == "manual_minipreco"}

    novas, preservadas = {}, 0
    for _, r in df.iterrows():
        categoria = (r["categoria_final"] or "").strip()
        if not categoria or categoria not in permitidas:
            continue
        if r["k"] in intocaveis:
            preservadas += 1
            continue
        chave = por_norm.get(r["k"], str(r["ean"]).zfill(13))
        novas[chave] = {"categoria": categoria, "origem": ORIGEM,
                        "regra": r.get("evidencia_categoria") or "grupo do ERP"}
    if not dry_run:
        backup(ARQUIVO_CATEGORIAS_PRODUTOS)
        salvar_categorias_produtos(ARQUIVO_CATEGORIAS_PRODUTOS, novas, permitidas)
    mudam = sum(1 for k, v in novas.items()
                if v["categoria"] != atuais.set_index("ean")["categoria"].get(k, ""))
    return (f"categorias_produtos.csv: {len(novas)} EANs gravados ({mudam} mudam de categoria), "
            f"{preservadas} preservados por serem manual_minipreco")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import calcular_preco_sugerido as motor
    from config_app import ARQUIVO_EANS, ARQUIVO_EANS_NEGATIVOS
    from classificador_categorias import carregar_marcas_proprias, e_marca_propria
    from config_app import ARQUIVO_MARCAS_PROPRIAS

    df = pd.read_excel(args.planilha, sheet_name="Estoque precificado")
    df["k"] = df["ean"].map(motor.normalizar_ean)
    # A evidencia da auditoria so sai na aba de mudancas; quem nao mudou ficou
    # com a categoria do grupo do ERP.
    mudou = pd.read_excel(args.planilha, sheet_name="Mudanca de categoria")
    df["evidencia_categoria"] = df["ean"].map(
        dict(zip(mudou["ean"], mudou["evidencia_categoria"])))
    marca_propria = motor.carregar_marca_propria()

    marcas = carregar_marcas_proprias(ARQUIVO_MARCAS_PROPRIAS)
    faltantes = [str(r["ean"]) for _, r in df.iterrows()
                 if r["k"] not in marca_propria and e_marca_propria(r["descricao"], marcas)]

    print(priorizar_eans(df, marca_propria, motor.normalizar_ean, ARQUIVO_EANS, args.dry_run))
    print(completar_marca_propria(faltantes, ARQUIVO_EANS_NEGATIVOS, args.dry_run))
    print(gravar_categorias(df, motor.normalizar_ean, args.dry_run))
    if args.dry_run:
        print("\n(dry-run: nada foi gravado)")


if __name__ == "__main__":
    main()
