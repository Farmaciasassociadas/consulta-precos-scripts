"""Importa um relatorio 'Analitico de Entradas' (.xls do ERP) para a base mestre.

Diferente de `ingest.carregar_custos_nf`, que recarrega a tabela inteira a partir
do export completo, este importa uma FATIA: faz upsert em `produto`, refaz o
custo_nf apenas dos EANs presentes no relatorio (a entrada mais recente e' a que
vale) e classifica em `subcategoria_classificada` usando Grupo Pai > Grupo do
proprio relatorio, validado contra `politica_categoria`.

Aceita tambem XML de NF-e (modelo 55), usando o mesmo parser do app
(minipreco_dominio.extrair_nfe) -- mesma formula de custo, mesmo fator de
embalagem. O XML nao traz Grupo/Grupo Pai, entao a classificacao so sai quando
o proprio fornecedor a declara na descricao (ver EIXO_NA_DESCRICAO).

Uso: python importar_entradas.py <relatorio.xls|nota.xml> [...] [--txt saida.txt]
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "precificador"))

from caminhos import CONSULTA_PRECOS  # noqa: E402
from ingest import (  # noqa: E402
    _carregar_fatores_venda, _linhas_da_planilha, _mapear_colunas_nf, _numero, normalizar_ean,
)

sys.path.insert(0, str(CONSULTA_PRECOS))

# O eixo (ETICOS/GENERICO/SIMILAR) so entra quando o FORNECEDOR o declara na
# propria descricao do item. Nao inferir eixo por nome de marca: e' justamente
# onde o classificador do app mais erra, e eixo errado muda o lucro-alvo.
EIXO_NA_DESCRICAO = (
    (re.compile(r"-\s*REFERENCIA\s*$", re.I), "ETICOS"),
    (re.compile(r"-\s*SIMILAR\s*$", re.I), "SIMILAR"),
    (re.compile(r"-\s*GEN[EÉ]RICO\s*$|GEN\s+SDZ|\sG\s*$", re.I), "GENERICO"),
)

DB = Path(__file__).parent / "precificador" / "precificador.db"

# O 'Analitico de Entradas' usa rotulos curtos; o export completo usa os longos
# ja mapeados em ingest.ROTULOS_NF. Aqui so o que muda.
ROTULOS = {
    "barras": "barras", "produto": "descricao", "qtde": "qtde",
    "valor unit liq": "unitario", "total do item": "total_item",
    "val icms st": "icms_st", "grupo pai": "grupo_pai", "grupo": "grupo_filho",
}


def _embalagens() -> dict[str, dict]:
    """Tabela de embalagens do app, no formato que extrair_nfe espera."""
    try:
        with (CONSULTA_PRECOS / "embalagens_produtos.csv").open(encoding="utf-8-sig") as fh:
            return {"".join(c for c in str(l.get("ean") or "") if c.isdigit()): l
                    for l in csv.DictReader(fh)}
    except OSError:
        return {}


def _eixo_declarado(descricao: str) -> str:
    for padrao, eixo in EIXO_NA_DESCRICAO:
        if padrao.search(descricao):
            return eixo
    return ""


def ler_xml_nfe(caminho: Path):
    """Itens de uma NF-e pelo parser do app -- mesma formula de custo do MiniPreco."""
    from minipreco_dominio import extrair_nfe

    nota = extrair_nfe(caminho, _embalagens())
    custos, produtos = [], {}
    for item in nota.itens:
        ean, descricao = normalizar_ean(item.ean), item.descricao.strip()
        quantidade, custo = float(item.quantidade), float(item.custo_unitario)
        custos.append((ean, quantidade, custo, quantidade * custo,
                       1 if float(item.icms_st) > 0 else 0))
        # O XML nao tem Grupo/Grupo Pai. So o eixo que o FORNECEDOR escreve na
        # descricao entra como pai; o filho fica vazio de proposito.
        produtos[ean] = (descricao, _eixo_declarado(descricao), "")
    if nota.itens_ignorados:
        print(f"  {caminho.name}: ignorados -> {'; '.join(nota.itens_ignorados)}")
    return custos, produtos


def ler_relatorio_xls(caminho: Path):
    todas = _linhas_da_planilha(caminho)
    import ingest
    ingest.ROTULOS_NF, original = ROTULOS, ingest.ROTULOS_NF
    try:
        col = _mapear_colunas_nf(todas[:12])
    finally:
        ingest.ROTULOS_NF = original

    fatores = _carregar_fatores_venda()
    custos, produtos = [], {}
    for row in todas:
        if len(row) <= max(col.values()):
            continue
        ean, descricao = normalizar_ean(row[col["barras"]]), row[col["descricao"]]
        if not ean or not descricao:
            continue
        qtde, total = _numero(row[col["qtde"]]), _numero(row[col["total_item"]])
        if not (qtde and total and qtde > 0 and total > 0):
            continue
        qtde *= fatores.get(ean, 1.0)  # NF em caixa, venda em cartela
        custos.append((ean, qtde, total / qtde, total,
                       1 if (_numero(row[col["icms_st"]]) or 0) > 0 else 0))
        produtos[ean] = (str(descricao).strip(),
                         str(row[col["grupo_pai"]] or "").strip(),
                         str(row[col["grupo_filho"]] or "").strip())
    return custos, produtos


def _classificar(pai: str, filho: str, politica: set[str]) -> tuple[str, str]:
    """Grupo Pai > Grupo, caindo para so o Pai quando o par nao tem politica."""
    pai, filho = (pai or "").strip().upper(), (filho or "").strip().upper()
    exata = f"{pai} > {filho}"
    if exata in politica:
        return exata, "relatorio (pai > filho)"
    if pai in politica:
        return pai, "relatorio (so pai; par sem politica)"
    return "", ""


def importar(arquivos: list[Path], conn: sqlite3.Connection) -> list[str]:
    politica = {r[0] for r in conn.execute("SELECT classificacao_exata FROM politica_categoria")}
    custos: list[tuple] = []
    produtos: dict[str, tuple[str, str, str]] = {}
    for arquivo in arquivos:
        ler = ler_xml_nfe if arquivo.suffix.lower() == ".xml" else ler_relatorio_xls
        c, pr = ler(arquivo)
        custos += c
        produtos.update(pr)  # arquivo posterior vence: entrada mais recente
        print(f"  {arquivo.name}: {len(c)} itens / {len(pr)} EANs")

    eans = list(produtos)
    marcas = ",".join("?" * len(eans))
    conn.execute(f"DELETE FROM custo_nf WHERE ean IN ({marcas})", eans)
    conn.executemany(
        "INSERT INTO custo_nf (ean, quantidade, custo_unitario, valor_total, tem_icms_st) "
        "VALUES (?, ?, ?, ?, ?)", custos)

    classificados, sem_categoria = 0, []
    for ean, (descricao, pai, filho) in produtos.items():
        conn.execute(
            "INSERT INTO produto (ean, descricao, grupo_pai_nf, grupo_filho_nf) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(ean) DO UPDATE SET descricao = excluded.descricao, "
            "grupo_pai_nf = COALESCE(excluded.grupo_pai_nf, produto.grupo_pai_nf), "
            "grupo_filho_nf = COALESCE(excluded.grupo_filho_nf, produto.grupo_filho_nf)",
            (ean, descricao, pai or None, filho or None))
        exata, fonte = _classificar(pai, filho, politica)
        if exata:
            conn.execute(
                "INSERT INTO subcategoria_classificada (ean, classificacao_exata, fonte) "
                "VALUES (?, ?, ?) ON CONFLICT(ean) DO UPDATE SET "
                "classificacao_exata = excluded.classificacao_exata, fonte = excluded.fonte",
                (ean, exata, fonte))
            classificados += 1
        elif not conn.execute(
                "SELECT 1 FROM subcategoria_classificada WHERE ean = ?", (ean,)).fetchone():
            sem_categoria.append(f"{ean} {descricao}")
    conn.commit()
    print(f"{len(custos)} linhas de entrada / {len(produtos)} EANs / "
          f"{classificados} classificados agora / {len(sem_categoria)} sem categoria")
    for linha in sem_categoria:
        print(f"    SEM CATEGORIA  {linha}")
    return eans


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("arquivos", type=Path, nargs="+", help=".xls do ERP ou XML de NF-e")
    p.add_argument("--txt", type=Path, help="grava os EANs importados, um por linha")
    p.add_argument("--somar-txt", action="store_true",
                   help="soma aos EANs que o --txt ja tem, em vez de substituir")
    args = p.parse_args()
    conn = sqlite3.connect(DB)
    eans = set(importar(args.arquivos, conn))
    if args.txt:
        if args.somar_txt and args.txt.exists():
            eans |= {l.strip() for l in args.txt.read_text(encoding="utf-8").splitlines() if l.strip()}
        args.txt.write_text("\n".join(sorted(eans, key=int)) + "\n", encoding="utf-8")
        print(f"{args.txt} ({len(eans)} EANs)")


if __name__ == "__main__":
    main()
