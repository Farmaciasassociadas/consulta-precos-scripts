"""Leva os EANs importados das entradas para a base VIVA do app.

Por que existe: importar_entradas.py grava em precificador.db, que e' a base do
motor de precificacao batch. O Consulta Precos / MiniPreco NAO le esse banco --
ele le tres arquivos proprios. EAN que nao entra neles simplesmente nao existe
para o app: nao aparece na lista, nao e' coletado, fica sem categoria.

  1. eans.txt               -- a lista mestre da coleta. So acrescenta; nunca
                               remove nem reordena, e preserva o sufixo ";preco".
  2. categorias_produtos.csv -- categoria. O app SO aceita "PAI > FILHO"
                               (categorias_disponiveis.txt); nivel pai sozinho
                               e' recusado e o item aparece sem categoria.
                               Nao toca em quem tem origem "manual_minipreco":
                               decisao humana manda.
  3. custo_produtos.csv     -- descricao e custo medio das notas.

Chave: EAN preenchido com zeros a 13, que e' como o app grava. O ERP guarda o
codigo cru; sem o preenchimento o mesmo produto vira duas chaves.

Uso:
    python aplicar_eans_no_app.py outputs/eans_entradas_itens.txt [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "precificador"))
from caminhos import CONSULTA_PRECOS  # noqa: E402

sys.path.insert(0, str(CONSULTA_PRECOS))

DB = Path(__file__).parent / "precificador" / "precificador.db"
ORIGEM = f"entradas_nf_{datetime.now():%Y-%m-%d}"


def pad13(valor: str) -> str:
    """Chave do app: digitos preenchidos com zero a esquerda ate 13."""
    digitos = "".join(c for c in str(valor or "") if c.isdigit())
    return digitos.zfill(13) if len(digitos) < 13 else digitos


def backup(caminho: Path) -> None:
    if caminho.exists():
        destino = caminho.with_name(
            f"{caminho.stem}_backup_{datetime.now():%Y%m%d_%H%M%S}_pre_entradas{caminho.suffix}")
        shutil.copy2(caminho, destino)
        print(f"  backup: {destino.name}")


def dados_do_banco(eans: list[str]) -> dict[str, dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    marcas = ",".join("?" * len(eans))
    itens: dict[str, dict] = {}
    for r in conn.execute(
        f"SELECT p.ean, p.descricao, s.classificacao_exata AS categoria, "
        f"AVG(n.custo_unitario) AS custo, SUM(n.quantidade) AS qtd, COUNT(n.id) AS notas "
        f"FROM produto p LEFT JOIN subcategoria_classificada s ON s.ean = p.ean "
        f"LEFT JOIN custo_nf n ON n.ean = p.ean "
        f"WHERE p.ean IN ({marcas}) GROUP BY p.ean", eans
    ):
        itens[pad13(r["ean"])] = dict(r)
    return itens


def aplicar_eans(itens: dict[str, dict], dry_run: bool) -> None:
    from config_app import ARQUIVO_EANS

    existentes = set()
    linhas = []
    if ARQUIVO_EANS.exists():
        linhas = ARQUIVO_EANS.read_text(encoding="utf-8-sig").splitlines()
        for linha in linhas:
            bruto = linha.split(";")[0].split(",")[0].split("\t")[0].strip()
            if bruto:
                existentes.add(pad13(bruto))

    novos = [e for e in itens if e not in existentes]
    print(f"eans.txt: {len(existentes)} ja na lista, {len(novos)} a acrescentar")
    if novos and not dry_run:
        backup(ARQUIVO_EANS)
        ARQUIVO_EANS.write_text("\n".join(linhas + novos) + "\n", encoding="utf-8")


def aplicar_categorias(itens: dict[str, dict], dry_run: bool) -> None:
    from config_app import ARQUIVO_CATEGORIAS_DISPONIVEIS, ARQUIVO_CATEGORIAS_PRODUTOS
    from dados_compartilhados import carregar_opcoes_categoria, salvar_categorias_produtos

    permitidas = tuple(carregar_opcoes_categoria(ARQUIVO_CATEGORIAS_DISPONIVEIS))
    atuais: dict[str, str] = {}
    if ARQUIVO_CATEGORIAS_PRODUTOS.exists():
        with ARQUIVO_CATEGORIAS_PRODUTOS.open(encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh):
                atuais[pad13(linha.get("ean", ""))] = (linha.get("origem") or "").strip()

    gravar, recusadas, humanas = {}, [], 0
    for ean, dados in itens.items():
        categoria = (dados.get("categoria") or "").strip()
        if not categoria:
            continue
        if atuais.get(ean) == "manual_minipreco":
            humanas += 1
            continue
        if categoria not in permitidas:
            recusadas.append(f"{ean} {categoria}")
            continue
        gravar[ean] = {"categoria": categoria, "origem": ORIGEM}

    print(f"categorias_produtos.csv: {len(gravar)} a gravar, "
          f"{humanas} preservados (manual_minipreco), {len(recusadas)} fora da lista permitida")
    for linha in recusadas:
        print(f"    RECUSADA  {linha}")
    if gravar and not dry_run:
        backup(ARQUIVO_CATEGORIAS_PRODUTOS)
        salvar_categorias_produtos(ARQUIVO_CATEGORIAS_PRODUTOS, gravar, permitidas)


def aplicar_custos(itens: dict[str, dict], dry_run: bool) -> None:
    from config_app import ARQUIVO_CUSTOS

    campos = ["ean", "descricao", "custo_medio", "qtd_total", "num_notas", "data_ultima_nota"]
    atuais: dict[str, dict] = {}
    if ARQUIVO_CUSTOS.exists():
        with ARQUIVO_CUSTOS.open(encoding="utf-8-sig", newline="") as fh:
            for linha in csv.DictReader(fh):
                atuais[pad13(linha.get("ean", ""))] = linha

    novos = 0
    for ean, dados in itens.items():
        if dados.get("custo") is None:
            continue
        novos += ean not in atuais
        atuais[ean] = {
            "ean": ean,
            "descricao": dados.get("descricao") or atuais.get(ean, {}).get("descricao", ""),
            "custo_medio": f"{dados['custo']:.4f}",
            "qtd_total": f"{dados.get('qtd') or 0:g}",
            "num_notas": str(dados.get("notas") or 0),
            "data_ultima_nota": atuais.get(ean, {}).get("data_ultima_nota", ""),
        }

    print(f"custo_produtos.csv: {len(atuais)} linhas no total ({novos} EANs novos)")
    if not dry_run:
        backup(ARQUIVO_CUSTOS)
        with ARQUIVO_CUSTOS.open("w", encoding="utf-8", newline="") as fh:
            escritor = csv.DictWriter(fh, fieldnames=campos)
            escritor.writeheader()
            for ean in sorted(atuais):
                escritor.writerow({c: atuais[ean].get(c, "") for c in campos})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("txt", type=Path, help="arquivo com um EAN por linha")
    ap.add_argument("--dry-run", action="store_true", help="so mostra, nao grava")
    args = ap.parse_args()

    eans = [l.strip() for l in args.txt.read_text(encoding="utf-8").splitlines() if l.strip()]
    itens = dados_do_banco(eans)
    print(f"{len(eans)} EANs no arquivo, {len(itens)} encontrados no precificador.db\n")

    aplicar_eans(itens, args.dry_run)
    aplicar_categorias(itens, args.dry_run)
    aplicar_custos(itens, args.dry_run)
    if args.dry_run:
        print("\n(dry-run: nada foi gravado)")


if __name__ == "__main__":
    main()
