"""Gera a lista de acoes de CADASTRO a partir da planilha precificada.

Sao correcoes que so a loja pode aplicar no ERP -- este script nao escreve em
lugar nenhum, so separa o que fazer de quem. Tres frentes:

  1. Acima do PMC   -- venda acima do teto legal da CMED. Baixar e obrigatorio.
  2. EAN invalido   -- codigo que nao fecha o digito verificador. Enquanto
                       estiver assim o item nunca casa com coleta nem com CMED.
  3. Sem preco de mercado -- separa "nunca foi tentado" de "foi tentado e o
                       produto nao existe nas farmacias online", que sao
                       problemas diferentes com acoes diferentes.

Uso:
    python gerar_acoes_cadastro.py [--planilha X.xlsx] [--saida Y.xlsx]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
sys.path.insert(0, str(APP))

PLANILHA_PADRAO = Path(
    r"G:\.shortcut-targets-by-id\1q0IRmUp06SR55V7qNb7wVLwWjEauQntR\DROGARIA"
    r"\Planilha de itens em estoque tratado - PRECIFICADO.xlsx")

# EANs conferidos a mao na internet em 15/08/2026 que a regra sozinha erraria:
# o digito fecha, mas o codigo e o da CAIXA (DUN/CEAN), nao o da unidade que a
# loja vende. Mesmo erro de base de embalagem, agora no proprio codigo.
CORRECAO_MANUAL = {
    "7894900681038": ("7894900681017", "lata avulsa (o 7894900681031 que fecha o "
                                       "digito e o kit com 6 latas) -- Cosmos/Systax"),
    "70847022503": ("70847022015", "lata avulsa (o 70847022503 do cadastro e o "
                                   "codigo da caixa) -- Cosmos/Bluesoft"),
}
# Confirmados na internet, batendo com a regra.
CONFERIDOS_NA_WEB = {
    "7894900010015": "Cosmos/Bluesoft, Systax e OpenFoodFacts: Coca-Cola lata 350ml",
    "7894900500004": "Cosmos/Bluesoft: Isotonico Limao Powerade 500ml",
    "7894900503005": "Cosmos/Bluesoft: Isotonico Laranja Powerade 500ml",
}


def digitos(v) -> str:
    return "".join(c for c in str(v or "") if c.isdigit())


def _dv_exato(codigo: str) -> bool:
    if len(codigo) not in (8, 12, 13, 14):
        return False
    corpo, dv = codigo[:-1], int(codigo[-1])
    soma = sum(int(c) * (3 if (len(corpo) - i) % 2 else 1) for i, c in enumerate(corpo))
    return (10 - soma % 10) % 10 == dv


def dv_ok(codigo: str) -> bool:
    """Digito verificador de GTIN, tolerante ao zero a esquerda perdido.

    UPC-A e' GTIN-12 e comeca com zero em produto importado (Monster
    070847022503, Santo Habito 070341689769). Ao passar por campo numerico o
    zero cai e sobra um codigo de 11 digitos que NAO e invalido -- so esta sem o
    preenchimento. Validar so pelo comprimento cru reprovava 7 codigos bons e
    mandava a loja "corrigir" o que ja estava certo.
    """
    cru = codigo.lstrip("0")
    # "00000" nao e um GTIN de valor zero, e' campo em branco. Sem esta guarda
    # ele passa: zfill(8) da "00000000", cuja soma e o digito sao ambos 0.
    if not cru:
        return False
    return any(_dv_exato(cru.zfill(n)) for n in (8, 12, 13, 14) if len(cru) <= n)


def com_dv(corpo: str) -> str:
    soma = sum(int(c) * (3 if (len(corpo) - i) % 2 else 1) for i, c in enumerate(corpo))
    return corpo + str((10 - soma % 10) % 10)


def norm(v) -> str:
    d = digitos(v)
    return d.lstrip("0") or d


def candidatos(bruto: str):
    """(codigo, como_foi_obtido), do mais provavel para o menos.

    Nunca devolve o proprio codigo de entrada: candidato igual ao original nao
    e' correcao nenhuma, e deixar passar obriga todo chamador a filtrar de novo.
    """
    e = digitos(bruto)
    curto = e.lstrip("0")
    vistos = {norm(e)}

    def propor(codigo: str, como: str):
        if norm(codigo) not in vistos:
            vistos.add(norm(codigo))
            return codigo, como
        return None

    tentativas = []
    if len(e) == 14:
        tentativas.append((e[1:], "DUN-14: retirado o digito de agrupamento"))
    if len(curto) == 12:
        tentativas.append(("0" + curto, "UPC-A de 12: preenchido a 13"))
    # Comprimento ja valido de GTIN: o corpo esta certo, caiu o ultimo digito.
    # Recalcular sobre o codigo inteiro daria 13 -> 14, que e o erro oposto.
    if len(curto) in (8, 13):
        tentativas.append((com_dv(curto[:-1]), "ultimo digito corrigido"))
    if len(curto) in (7, 11, 12):
        tentativas.append((com_dv(curto), "digito verificador acrescentado"))
    for codigo, como in tentativas:
        if (proposto := propor(codigo, como)):
            yield proposto


def recuperar_eans(df: pd.DataFrame, conhecidos: set[str]) -> pd.DataFrame:
    """Candidato so vale confirmado por base independente: 1 em 10 numeros
    aleatorios fecha o digito, entao fechar sozinho nao prova nada."""
    maus = df[~df["ean"].map(lambda e: dv_ok(digitos(e)))]
    linhas = []
    for _, r in maus.iterrows():
        atual = str(r["ean"])
        if atual in CORRECAO_MANUAL:
            novo, como = CORRECAO_MANUAL[atual]
            conf = "CONFERIDO NA INTERNET (a regra erraria: codigo de caixa)"
        else:
            achado = next(((c, k) for c, k in candidatos(atual)
                           if dv_ok(c) and norm(c) in conhecidos and norm(c) != norm(atual)), None)
            fraco = next(((c, k) for c, k in candidatos(atual)
                          if dv_ok(c) and norm(c) != norm(atual)), None)
            novo, como = achado or fraco or ("", "")
            if achado:
                conf = "CONFIRMADO em CMED/Brick/coleta"
            elif fraco:
                conf = "SO fecha o digito -- conferir na embalagem"
            else:
                conf = "sem candidato: nao e codigo de barras"
            if novo in CONFERIDOS_NA_WEB:
                conf = "CONFERIDO NA INTERNET"
                como += f" -- {CONFERIDOS_NA_WEB[novo]}"
        linhas.append({"ean_no_erp": atual, "descricao": r["descricao"],
                       "ean_correto": novo, "como_foi_obtido": como, "confianca": conf,
                       "estoque": r["estoque"], "custo_real": r["custo_real"],
                       "preco_praticado": r["preco_praticado"]})
    ordem = {"CONFERIDO NA INTERNET (a regra erraria: codigo de caixa)": 0,
             "CONFERIDO NA INTERNET": 1, "CONFIRMADO em CMED/Brick/coleta": 2}
    res = pd.DataFrame(linhas)
    return res.sort_values(["confianca", "estoque"], key=lambda s: s.map(ordem).fillna(9)
                           if s.name == "confianca" else -s)


def acima_do_pmc(df: pd.DataFrame, pmc: dict[str, float]) -> pd.DataFrame:
    """Venda acima do teto da CMED. O preco a aplicar e o menor entre a sugestao
    do motor e o proprio PMC -- a sugestao ja considera custo e concorrencia,
    mas o PMC e limite legal e nao admite excecao."""
    d = df.copy()
    d["pmc"] = d["ean"].map(lambda e: pmc.get(norm(e)))
    fora = d[d["pmc"].notna() & d["preco_praticado"].gt(d["pmc"] * 1.001)].copy()
    fora["preco_a_aplicar"] = fora[["preco_sugerido", "pmc"]].min(axis=1).round(2)
    fora["excesso_pct"] = (fora["preco_praticado"] / fora["pmc"] - 1)
    fora["reducao_por_unidade"] = (fora["preco_praticado"] - fora["preco_a_aplicar"]).round(2)
    return fora.sort_values("excesso_pct", ascending=False)[
        ["ean", "descricao", "preco_praticado", "pmc", "preco_sugerido",
         "preco_a_aplicar", "reducao_por_unidade", "excesso_pct", "estoque"]]


def sem_mercado(df: pd.DataFrame, precos_csv: Path) -> pd.DataFrame:
    """Separa "nunca tentado" de "tentado e o produto nao existe online".

    Sao acoes opostas: o primeiro entra na fila de coleta, o segundo nunca vai
    ter concorrente e precisa de outra ancora (PMC, lista do fornecedor ou
    decisao humana). Insistir na coleta do segundo so gasta rodada.
    """
    c = pd.read_csv(precos_csv, encoding="utf-8-sig", dtype=str, low_memory=False,
                    usecols=["ean", "status"])
    c["k"] = c["ean"].map(norm)
    tentativas = c.groupby("k").size()
    falhas = c[c["status"].ne("OK")].groupby("k").size()

    d = df[df["concorrentes_com_preco"].eq(0) & df["estoque"].gt(0)].copy()
    d["k"] = d["ean"].map(norm)
    d["tentativas"] = d["k"].map(tentativas).fillna(0).astype(int)
    d["falhas"] = d["k"].map(falhas).fillna(0).astype(int)
    d["situacao"] = d["tentativas"].map(
        lambda n: "NUNCA TENTADO -- por na fila de coleta" if n == 0
        else "TENTADO E NAO EXISTE ONLINE -- precisa de outra ancora")
    d["valor_parado"] = (d["estoque"] * d["custo_real"]).round(2)
    return d.sort_values("valor_parado", ascending=False)[
        ["situacao", "ean", "descricao", "tentativas", "falhas", "estoque",
         "custo_real", "preco_praticado", "valor_parado"]]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--planilha", default=str(PLANILHA_PADRAO))
    ap.add_argument("--saida", default=None)
    args = ap.parse_args()

    planilha = Path(args.planilha)
    saida = Path(args.saida) if args.saida else planilha.with_name("ACOES DE CADASTRO.xlsx")

    df = pd.read_excel(planilha, sheet_name="Estoque precificado", dtype={"ean": str})

    import calcular_preco_sugerido as motor
    ref = motor.carregar_referencia()
    pmc = {k: v["pmc"] for k, v in ref.items() if v.get("pmc")}
    conhecidos = set(ref)
    c = pd.read_csv(APP / "precos.csv", encoding="utf-8-sig", dtype=str,
                    low_memory=False, usecols=["ean"])
    conhecidos |= set(c["ean"].map(norm))

    pmc_fora = acima_do_pmc(df, pmc)
    eans = recuperar_eans(df, conhecidos)
    mercado = sem_mercado(df, APP / "precos.csv")

    with pd.ExcelWriter(saida, engine="openpyxl") as xl:
        pmc_fora.to_excel(xl, sheet_name="1 - Baixar (acima do PMC)", index=False)
        eans.to_excel(xl, sheet_name="2 - Corrigir EAN", index=False)
        mercado.to_excel(xl, sheet_name="3 - Sem preco de mercado", index=False)

    print(f"1. Acima do PMC: {len(pmc_fora)} itens, "
          f"reducao media de {pmc_fora['excesso_pct'].mean():.1%}")
    print(f"2. EAN invalido: {len(eans)} itens")
    print(eans["confianca"].value_counts().to_string())
    print(f"3. Sem preco de mercado: {len(mercado)} itens")
    print(mercado.groupby("situacao")["valor_parado"].agg(["size", "sum"]).to_string())
    print(f"\nGravado: {saida}")


if __name__ == "__main__":
    main()
