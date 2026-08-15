"""Lista unica e priorizada do que corrigir NO ERP, ordenada por dinheiro.

Nao e um relatorio de analise -- e a fila de digitacao. Cada linha diz o campo,
o valor de hoje, o valor a por e a evidencia. Item sem evidencia forte fica de
fora: fila cheia de "talvez" nao e usada.

Uso:
    python gerar_urgentes_erp.py [--planilha X.xlsx] [--saida Y.xlsx]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from gerar_acoes_cadastro import candidatos, dv_ok, digitos, norm

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
sys.path.insert(0, str(APP))

PLANILHA_PADRAO = Path(
    r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA"
    r"\Planilha de itens em estoque tratado - PRECIFICADO.xlsx")

# Precos conferidos um a um na internet em 15/08/2026 (ver dados/pesquisa_web_*).
# So entram aqui os que tem fonte -- o resto sai das regras abaixo.
WEB = {
    "7899547543896": (5.99, 7.99, "Drogasil, Droga Raia e Pacheco"),
    "78911222": (13.90, 22.11, "CliqueFarma (9 farmacias) e Sao Joao"),
    "7896714257594": (3.76, 6.55, "CliqueFarma e Preco Popular"),
    "7896094931879": (3.53, 4.98, "CliqueFarma, Drogaria Globo e Droga Raia"),
    "7896714292533": (34.50, 90.26, "6 farmacias, de Drogaria Sao Paulo a Pense Farma"),
    "7896104994009": (52.90, 59.90, "Amazon, Sao Joao e VileoFarma"),
    "7891106910118": (28.70, 35.00, "CliqueFarma (Bayer C/10) -- dado de 2023"),
    "7891317017668": (49.15, 80.46, "Drogaria Minas Brasil e Coop Drogaria"),
    "7891317025045": (28.50, 89.89, "Preco Popular, Panvel e Drogasil (generico)"),
    "7891000062661": (44.64, 102.58, "Amazon e Farmacias Sao Joao"),
    "7896544902176": (18.57, 24.99, "Drogarias Pacheco (micropore 5x4,5)"),
}

CAMPO_PRECO = "Preco de Promocao (o preco praticado)"
CAMPO_CUSTO = "Ult. Prc. Entrada / Preco de Compra"


def carregar(planilha: Path) -> pd.DataFrame:
    df = pd.read_excel(planilha, sheet_name="Estoque precificado", dtype={"ean": str})
    comp = pd.read_excel(planilha, sheet_name="Comparacao meu preco", dtype={"ean": str})
    df = df.merge(comp[["ean", "mercado_min", "mercado_max", "lojas_na_faixa"]],
                  on="ean", how="left")
    apr = pd.read_excel(planilha, sheet_name="Apresentacao divergente", dtype={"ean": str})
    df["apresentacao_divergente"] = df["ean"].isin(apr["ean"])
    df["k"] = df["ean"].map(norm)
    return df


def acoes(df: pd.DataFrame, pmc: dict[str, float]) -> pd.DataFrame:
    """Uma linha por acao. `dinheiro` e' o criterio de ordem: o que muda mais
    caixa vem primeiro, seja margem entregue de graca ou venda que nao acontece."""
    out = []

    def add(r, prio, acao, campo, de, para, motivo, evidencia, dinheiro):
        out.append({
            "prioridade": prio, "acao": acao, "ean": r["ean"],
            "descricao": r["descricao"], "campo_no_erp": campo,
            "valor_hoje": round(float(de), 2) if de is not None else None,
            "valor_novo": round(float(para), 2) if para is not None else None,
            "estoque": r["estoque"], "dinheiro_em_jogo": round(float(dinheiro), 2),
            "motivo": motivo, "evidencia": evidencia})

    for _, r in df.iterrows():
        k, est = r["k"], float(r["estoque"] or 0)
        custo = r["custo_real"] if pd.notna(r["custo_real"]) else 0
        prat = r["preco_praticado"] if pd.notna(r["preco_praticado"]) else 0
        faixa = WEB.get(k)

        # 1. Custo impossivel: acima do proprio preco de venda e sem NF.
        #    O pipeline ja zera `custo_real` nesses (senao vira piso e empurra a
        #    sugestao), entao o valor que ainda esta NO ERP -- que e' o que a
        #    loja precisa corrigir -- so aparece em custo_unit_erp/ult_entrada.
        if r["custo_validado"] == "SEM NF - CUSTO IMPOSSIVEL":
            no_erp = max([v for v in (r["custo_unit_erp"], r["ult_entrada"])
                          if pd.notna(v) and v > 0], default=0)
            if no_erp > 0:
                add(r, 1, "CORRIGIR CUSTO", CAMPO_CUSTO, no_erp,
                    round(faixa[0] * 0.6, 2) if faixa else None,
                    f"custo R$ {no_erp:.2f} acima do proprio preco de venda "
                    f"(R$ {prat:.2f}) e sem NF que comprove",
                    (f"mercado vende a R$ {faixa[0]:.2f}-{faixa[1]:.2f} ({faixa[2]}); "
                     f"valor novo e' uma estimativa -- confira a nota"
                     if faixa else "sem nota fiscal no periodo: confira a ultima entrada"),
                    no_erp * max(est, 1))

        # 2. Acima do PMC: teto legal, nao admite excecao.
        teto = pmc.get(k)
        if teto and prat > teto * 1.001:
            novo = min(r["preco_sugerido"], teto) if pd.notna(r["preco_sugerido"]) else teto
            add(r, 1, "BAIXAR PRECO (acima do PMC)", CAMPO_PRECO, prat, novo,
                f"venda {prat / teto - 1:.0%} acima do teto legal da CMED (PMC R$ {teto:.2f})",
                "tabela CMED", (prat - novo) * max(est, 1))

        # 3. Preco fora da faixa conferida na internet.
        if faixa and prat > 0:
            minimo, maximo, fonte = faixa
            if prat < minimo * 0.95:
                add(r, 2, "SUBIR PRECO", CAMPO_PRECO, prat, minimo,
                    f"vendendo {1 - prat / minimo:.0%} abaixo do menor concorrente",
                    f"R$ {minimo:.2f}-{maximo:.2f} em {fonte}", (minimo - prat) * est)
            elif prat > maximo * 1.05:
                add(r, 2, "BAIXAR PRECO", CAMPO_PRECO, prat, maximo,
                    f"vendendo {prat / maximo - 1:.0%} acima do maior concorrente",
                    f"R$ {minimo:.2f}-{maximo:.2f} em {fonte}", (prat - maximo) * est)

        # 4. Marca propria com custo em base de embalagem errada. NF e cadastro
        #    concordam, entao nenhuma guarda pega -- mas custo 2x+ o proprio
        #    preco de venda, repetido em toda a linha, e' fator de venda faltando.
        if (custo > 0 and prat > 0 and custo > prat * 1.8
                and r["custo_validado"] == "CONFIRMADO PELA NF"):
            add(r, 2, "CADASTRAR FATOR DE VENDA", "embalagens_produtos.csv (fator_venda)",
                custo, None,
                f"custo R$ {custo:.2f} e' {custo / prat:.1f}x o proprio preco de venda",
                "NF e cadastro concordam: a nota vem em outra base de embalagem",
                (custo - prat) * est)

        # 5. EAN que nao fecha o digito verificador.
        if not dv_ok(digitos(r["ean"])):
            novo = next((c for c, _ in candidatos(r["ean"]) if dv_ok(c)), None)
            if novo:
                add(r, 3, "CORRIGIR EAN", "Barras", None, None,
                    "codigo nao fecha o digito verificador: nunca casa com coleta nem CMED",
                    f"codigo provavel {novo}", custo * est)
                out[-1]["valor_hoje"] = r["ean"]
                out[-1]["valor_novo"] = novo

    a = pd.DataFrame(out)
    return a.sort_values(["prioridade", "dinheiro_em_jogo"], ascending=[True, False])


def formatar(caminho: Path) -> None:
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    largura = {"prioridade": 11, "acao": 28, "ean": 16, "descricao": 46,
               "campo_no_erp": 34, "valor_hoje": 14, "valor_novo": 14,
               "estoque": 10, "dinheiro_em_jogo": 17, "motivo": 62, "evidencia": 62}
    cor = {1: "FFC7CE", 2: "FFD9A0", 3: "FFEB9C"}
    wb = load_workbook(caminho)
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        nomes = [c.value for c in ws[1]]
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="44546A")
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for i, nome in enumerate(nomes, start=1):
            letra = get_column_letter(i)
            ws.column_dimensions[letra].width = largura.get(nome, 16)
            if nome in ("ean", "valor_hoje", "valor_novo"):
                for c in ws[letra][1:]:
                    if isinstance(c.value, str):
                        c.number_format = "@"
                        c.alignment = Alignment(horizontal="left")
                    elif nome != "ean":
                        c.number_format = r'_-"R$" * #,##0.00_-;-"R$" * #,##0.00_-'
            elif nome == "dinheiro_em_jogo":
                for c in ws[letra][1:]:
                    c.number_format = r'_-"R$" * #,##0.00_-;-"R$" * #,##0.00_-'
        if "prioridade" in nomes:
            letra = get_column_letter(nomes.index("prioridade") + 1)
            for c in ws[letra][1:]:
                if c.value in cor:
                    c.fill = PatternFill("solid", fgColor=cor[c.value])
    wb.save(caminho)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", default=str(PLANILHA_PADRAO))
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    planilha = Path(args.planilha)
    saida = Path(args.saida) if args.saida else planilha.with_name("URGENTE - CORRIGIR NO ERP.xlsx")

    import calcular_preco_sugerido as motor
    pmc = {k: v["pmc"] for k, v in motor.carregar_referencia().items() if v.get("pmc")}

    df = carregar(planilha)
    a = acoes(df, pmc)

    with pd.ExcelWriter(saida, engine="openpyxl") as xl:
        for nome, prio in (("1 - Faca hoje", 1), ("2 - Esta semana", 2), ("3 - Quando der", 3)):
            a[a["prioridade"].eq(prio)].to_excel(xl, sheet_name=nome, index=False)
        a.to_excel(xl, sheet_name="Tudo", index=False)
    formatar(saida)

    print(a.groupby(["prioridade", "acao"])
          .agg(itens=("ean", "count"), dinheiro=("dinheiro_em_jogo", "sum"))
          .round(0).to_string())
    print(f"\nTotal: {len(a)} acoes | Gravado: {saida}")


if __name__ == "__main__":
    main()
