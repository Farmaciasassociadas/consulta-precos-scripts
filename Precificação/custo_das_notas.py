"""Le o "Relatorio de entradas por nota" do ERP (.xls) e devolve o custo real por EAN.

O relatorio e' hierarquico: linhas de cabecalho para filial / fornecedor / numero
da nota, e uma linha por item. Vale a linha de item, identificada por ter codigo
de barras.

Custo unitario que interessa = `Valor Total do Item` / `Qtde. Unitaria`. O total
do item ja soma ICMS-ST, IPI, frete, seguro e outras despesas e ja desconta o
desconto -- e' o custo posto na prateleira. O `Valor Unitario Bruto` sozinho e' o
preco de tabela do fornecedor, que e' justamente o que o campo de custo do ERP
costuma guardar (e por isso subestima o custo dos itens com ST).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import xlrd
from xlrd.xldate import xldate_as_datetime

COL = {"data_nota": 5, "cfop": 8, "ean": 9, "descricao": 10, "unitario_bruto": 18,
       "qtde": 19, "total_bruto": 23, "desconto": 24, "total_liquido": 25, "ipi": 26,
       "icms_st": 27, "frete": 31, "outras": 32, "seguro": 33, "total_item": 34,
       "preco_venda": 35, "fornecedor_nome": 39}

# Devolucao / remessa / bonificacao nao formam custo de compra.
CFOP_COMPRA = ("1.102", "2.102", "1.101", "2.101", "1.403", "2.403", "1.152", "2.152")


@dataclass(frozen=True)
class EntradaNF:
    ean: str
    descricao: str
    data: date | None
    fornecedor: str
    qtde: float
    unitario_bruto: float
    custo_unitario: float   # total do item / qtde -- com ST, IPI, frete
    icms_st: float
    total_item: float


def _num(valor) -> float:
    try:
        return float(valor)
    except (TypeError, ValueError):
        return 0.0


def _texto(valor) -> str:
    return str(valor).strip()


def ler_entradas(caminho: Path) -> list[EntradaNF]:
    sh = xlrd.open_workbook(str(caminho)).sheet_by_index(0)
    entradas: list[EntradaNF] = []
    fornecedor = ""
    for r in range(sh.nrows):
        linha = sh.row_values(r)
        rotulo = _texto(linha[1])
        if "Fornecedor:" in rotulo:
            fornecedor = rotulo.split(":", 1)[1].strip()
            continue
        ean = _texto(linha[COL["ean"]])
        if not ean or not ean[0].isdigit():
            continue
        qtde = _num(linha[COL["qtde"]])
        total = _num(linha[COL["total_item"]])
        if qtde <= 0 or total <= 0:
            continue
        bruto = _num(linha[COL["data_nota"]])
        entradas.append(EntradaNF(
            ean=ean,
            descricao=_texto(linha[COL["descricao"]]),
            data=xldate_as_datetime(bruto, 0).date() if bruto > 0 else None,
            fornecedor=fornecedor,
            qtde=qtde,
            unitario_bruto=_num(linha[COL["unitario_bruto"]]),
            custo_unitario=total / qtde,
            icms_st=_num(linha[COL["icms_st"]]),
            total_item=total,
        ))
    return entradas


def custo_por_ean(entradas: list[EntradaNF], normalizar) -> dict[str, dict]:
    """Consolida por EAN. O custo que vale e' o da ULTIMA nota -- e' o que a
    proxima reposicao vai custar. A media do periodo entra so como referencia."""
    por_ean: dict[str, list[EntradaNF]] = {}
    for e in entradas:
        por_ean.setdefault(normalizar(e.ean), []).append(e)
    consolidado = {}
    for ean, itens in por_ean.items():
        itens = sorted(itens, key=lambda e: (e.data or date.min))
        ultima = itens[-1]
        qtde_total = sum(i.qtde for i in itens)
        consolidado[ean] = {
            "custo_nf": ultima.custo_unitario,
            "custo_nf_medio": sum(i.total_item for i in itens) / qtde_total,
            "unitario_bruto_nf": ultima.unitario_bruto,
            "tem_icms_st": any(i.icms_st > 0 for i in itens),
            "data_ultima_nf": ultima.data,
            "fornecedor": ultima.fornecedor,
            "qtde_comprada": qtde_total,
            "n_notas": len(itens),
            "descricao_nf": ultima.descricao,
        }
    return consolidado


if __name__ == "__main__":
    import sys
    entradas = ler_entradas(Path(sys.argv[1]))
    print(f"{len(entradas)} linhas de item")
    norm = lambda v: "".join(c for c in str(v) if c.isdigit()).lstrip("0") or "0"
    consolidado = custo_por_ean(entradas, norm)
    print(f"{len(consolidado)} EANs distintos")
    com_st = sum(1 for v in consolidado.values() if v["tem_icms_st"])
    print(f"{com_st} com ICMS-ST")
