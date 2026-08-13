"""Worklist de RECOLETA, priorizada por dinheiro parado na prateleira.

Nao coleta: decide o que coletar. A coleta em si roda no app
(`C:\\Users\\docze\\ConsultaPrecosEAN`, Violentmonkey + abas) -- os sites sao
SPA e a busca depende da sessao do navegador do app; qualquer atalho por fetch
devolve resultado de outro termo, o que e' pior que dado faltando.

Tres motivos, nesta ordem de prejuizo medido em 12/08/2026:
  1. NUNCA_VARRIDO  -- o site nao tem NENHUM registro do EAN. Nao e' "nao
     encontrou": e' que nunca tentou. farmasp so cobriu 22,7% do catalogo.
  2. VENCIDO        -- ultima coleta com mais de `dias_max` dias. A ultima
     varredura completa foi 31/07; hoje o dado tem 12 dias.
  3. SEM_PRECO      -- tentou e nao achou. So vale reconsultar se o item tem
     estoque; se o site nao vende aquilo, insistir nao muda nada.
"""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

import db

SITES = ("drogaraia", "saopaulo", "saojoao", "nissei", "panvel",
         "paguemenos", "drogariasp", "farmasp", "precopopular")
SAIDA = Path(__file__).parent.parent / "fila_coleta.csv"


def _data(txt: str | None) -> datetime | None:
    try:
        return datetime.strptime(txt, "%d/%m/%Y %H:%M:%S") if txt else None
    except ValueError:
        return None


def montar(conn, rodada_id: int, dias_max: int = 7) -> list[dict]:
    hoje = datetime.now()
    coletas: dict[tuple[str, str], tuple[str, datetime | None]] = {}
    for ean, site, status, dh in conn.execute(
            "SELECT ean, site, status, data_hora FROM preco_concorrente"):
        chave = (ean, site)
        anterior = coletas.get(chave)
        atual = (status, _data(dh))
        if anterior is None or (atual[1] and anterior[1] and atual[1] > anterior[1]):
            coletas[chave] = atual

    linhas = []
    # Marca propria fica FORA da fila: o preco vem da lista do fornecedor e nao
    # existe concorrente para consultar. Sem este filtro a fila abria com
    # SANTO HABITO CREATINA (R$ 2.700 parados, 9 sites "nunca varridos") --
    # nove buscas que nunca vao achar nada.
    for ean, desc, estoque, valor in conn.execute(
            """SELECT r.ean, r.descricao, e.estoque_atual, e.valor_total_venda
               FROM recomendacao r
               LEFT JOIN estoque e ON e.ean = r.ean
               LEFT JOIN produto pr ON pr.ean = r.ean
               WHERE r.rodada_id = ? AND COALESCE(pr.marca_propria, 0) = 0""", (rodada_id,)):
        tem_estoque = (estoque or 0) > 0
        for site in SITES:
            status, quando = coletas.get((ean, site), (None, None))
            if status is None:
                motivo = "1_NUNCA_VARRIDO"
            elif quando and (hoje - quando).days > dias_max:
                motivo = "2_VENCIDO"
            elif status in ("NAO_ENCONTRADO", "INDISPONIVEL") and tem_estoque:
                motivo = "3_SEM_PRECO"
            else:
                continue
            linhas.append({
                "motivo": motivo, "ean": ean, "site": site,
                "descricao": desc, "estoque": estoque or 0,
                "valor_em_estoque": round(valor or 0, 2),
                "ultima_coleta": quando.strftime("%d/%m/%Y") if quando else "",
                "ultimo_status": status or "",
            })
    # dinheiro parado primeiro; dentro do mesmo item, o motivo mais grave antes
    linhas.sort(key=lambda x: (-x["valor_em_estoque"], x["motivo"]))
    return linhas


def agrupar_por_ean(linhas: list[dict]) -> list[dict]:
    """Uma linha por EAN -- que e' como a coleta roda (abre o item, varre os
    sites). Nove linhas do mesmo EAN nao sao nove itens, e somar `valor` por
    linha multiplicaria o estoque da loja por nove."""
    por_ean: dict[str, dict] = {}
    for linha in linhas:
        item = por_ean.setdefault(linha["ean"], {
            "ean": linha["ean"], "descricao": linha["descricao"],
            "estoque": linha["estoque"], "valor_em_estoque": linha["valor_em_estoque"],
            "sites": [], "nunca_varrido": 0, "vencido": 0, "sem_preco": 0,
        })
        item["sites"].append(linha["site"])
        item[{"1_NUNCA_VARRIDO": "nunca_varrido", "2_VENCIDO": "vencido",
              "3_SEM_PRECO": "sem_preco"}[linha["motivo"]]] += 1
    for item in por_ean.values():
        item["sites"] = " ".join(sorted(set(item["sites"])))
    return sorted(por_ean.values(),
                  key=lambda x: (-x["valor_em_estoque"], -x["nunca_varrido"]))


def main() -> None:
    conn = db.connect()
    rodada_id = conn.execute("SELECT MAX(id) FROM rodada").fetchone()[0]
    linhas = montar(conn, rodada_id)
    with SAIDA.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=list(linhas[0].keys()))
        escritor.writeheader()
        escritor.writerows(linhas)

    por_motivo: dict[str, int] = {}
    por_site: dict[str, int] = {}
    for linha in linhas:
        por_motivo[linha["motivo"]] = por_motivo.get(linha["motivo"], 0) + 1
        por_site[linha["site"]] = por_site.get(linha["site"], 0) + 1
    itens = agrupar_por_ean(linhas)
    saida_ean = SAIDA.with_name("fila_coleta_por_item.csv")
    with saida_ean.open("w", encoding="utf-8-sig", newline="") as fh:
        escritor = csv.DictWriter(fh, fieldnames=list(itens[0].keys()))
        escritor.writeheader()
        escritor.writerows(itens)

    print(f"rodada {rodada_id}: {len(linhas)} consultas em {len(itens)} itens")
    print(f"  {SAIDA}")
    print(f"  {saida_ean}")
    for motivo, n in sorted(por_motivo.items()):
        print(f"  {motivo:18s} {n:6d} consultas")
    print("  nunca varrido, por site:", ", ".join(
        f"{s}={n}" for s, n in sorted(
            ((s, sum(1 for x in linhas if x["site"] == s and x["motivo"] == "1_NUNCA_VARRIDO"))
             for s in SITES), key=lambda x: -x[1]) if n))
    com_estoque = [x for x in itens if x["estoque"] > 0]
    print(f"  itens COM estoque na fila: {len(com_estoque)}, "
          f"R$ {sum(x['valor_em_estoque'] for x in com_estoque):,.0f} de mercadoria sem preço conferido")
    print(f"  destes, {sum(1 for x in com_estoque if x['nunca_varrido'])} têm ao menos um site nunca varrido")


if __name__ == "__main__":
    main()
