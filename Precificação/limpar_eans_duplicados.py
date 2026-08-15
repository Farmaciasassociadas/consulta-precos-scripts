"""Remove do eans.txt as linhas que repetem o mesmo EAN em duas grafias.

A coleta grava o GTIN preenchido a 13 ("0086201223370") e o ERP/NF grava o
codigo cru ("86201223370"); as duas formas convivem no arquivo e cada uma
consome um ciclo de coleta do mesmo produto. Ver [[colecao-grava-gtin-...]].

Qual grafia sobrevive: a que os sites JA responderam. A busca no site e' feita
com o codigo como esta escrito, entao manter a grafia que nunca trouxe preco
seria trocar um duplicado por um EAN morto. Empate resolve pela linha que tem
";preco" e, por ultimo, pela posicao (a fila ja esta priorizada).

Uso:
    python limpar_eans_duplicados.py [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
ARQUIVO = APP / "eans.txt"
PRECOS = APP / "precos.csv"
STATUS_VALIDO = {"OK", "PROMOCAO", "SEM_ESTOQUE_COM_PRECO"}


def normalizar(linha: str) -> str:
    digitos = "".join(c for c in linha.split(";", 1)[0] if c.isdigit())
    return digitos.lstrip("0") or digitos


def coletas_por_grafia() -> dict[str, int]:
    """Quantas coletas COM PRECO cada grafia ja rendeu."""
    contagem: dict[str, int] = defaultdict(int)
    if not PRECOS.exists():
        return contagem
    with open(PRECOS, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            ean = (row.get("ean") or "").strip()
            preco = (row.get("preco") or "").strip()
            if ean and preco and (row.get("status") or "") in STATUS_VALIDO:
                contagem[ean] += 1
    return contagem


def escolher(linhas: list[tuple[int, str]], sucessos: dict[str, int]) -> str:
    def nota(item: tuple[int, str]) -> tuple[int, int, int]:
        i, linha = item
        grafia = linha.split(";", 1)[0]
        return (-sucessos.get(grafia, 0), 0 if ";" in linha else 1, i)

    vencedora = min(linhas, key=nota)[1]
    if ";" not in vencedora:  # nao perder o preco proprio que estava na outra linha
        com_preco = next((l for _, l in linhas if ";" in l), None)
        if com_preco:
            vencedora = f"{vencedora};{com_preco.split(';', 1)[1]}"
    return vencedora


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    linhas = [l for l in ARQUIVO.read_text(encoding="utf-8", errors="replace").splitlines()
              if l.strip()]
    sucessos = coletas_por_grafia()

    grupos: dict[str, list[tuple[int, str]]] = defaultdict(list)
    for i, linha in enumerate(linhas):
        grupos[normalizar(linha)].append((i, linha))

    mantidas, removidas = {}, []
    for ean, itens in grupos.items():
        escolhida = escolher(itens, sucessos)
        mantidas[ean] = (min(i for i, _ in itens), escolhida)
        removidas.extend(l for _, l in itens if l != escolhida)

    saida = [linha for _, linha in sorted(mantidas.values())]
    assert len({normalizar(l) for l in saida}) == len(saida), "sobrou duplicado"
    assert {normalizar(l) for l in saida} == set(grupos), "perdeu EAN"

    print(f"{len(linhas)} linhas -> {len(saida)} ({len(removidas)} duplicatas removidas)")
    for l in removidas[:10]:
        print(f"  removida: {l}")
    if not args.dry_run:
        shutil.copy2(ARQUIVO, ARQUIVO.with_name(
            f"eans_backup_{datetime.now():%Y%m%d_%H%M%S}_pre_dedup.txt"))
        ARQUIVO.write_text("\n".join(saida) + "\n", encoding="utf-8")
        print(f"Gravado: {ARQUIVO}")
    else:
        print("(dry-run: nada foi gravado)")


if __name__ == "__main__":
    main()
