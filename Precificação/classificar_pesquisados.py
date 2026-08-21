"""Classificacao dos 12 EANs que vieram de XML de NF-e sem Grupo/Grupo Pai.

O XML nao traz a categoria do ERP e o eixo nao pode ser adivinhado por marca.
Cada linha abaixo foi conferida em duas fontes: o segmento do Brick
(preco_brick.segmento: RX/GEN/SIM/NMED) e a bula/registro do produto.

Atencao ao que o Brick NAO diz: segmento 'RX' e' marca de prescricao, nao
medicamento de referencia. ABLOK, PANTOPAZ e DICLAC vem como RX e os tres sao
SIMILAR (referencias: Atenol, Pantozol, Voltaren). Mapear RX -> ETICOS teria
posto tres similares no lucro-alvo de etico.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB = Path(__file__).parent / "precificador" / "precificador.db"
FONTE = "pesquisa manual 20/08/2026 (Brick + bula)"

# ean: (classificacao_exata, por que)
CLASSIFICACAO = {
    "4015630064076": ("VAREJO > ACESSORIOS", "Brick NMED; tira de glicemia, nao e medicamento"),
    "7896637032223": ("VAREJO > SUPLEMENTOS", "Brick NMED; probiotico em capsula"),
    "7891317016623": ("SIMILAR > USO CONTINUO", "similar (Eurofarma/Myralis); ferro oral, antianemico sob prescricao"),
    "7896241225523": ("SIMILAR > USO CONTINUO", "similar, referencia Atenol; atenolol, anti-hipertensivo"),
    "7896004711874": ("GENERICO > RX", "Brick GEN (Germed); desonida, corticoide topico sob prescricao"),
    "7897595603128": ("SIMILAR > USO CONTINUO", "similar, referencia Pantozol; pantoprazol"),
    "7897595634917": ("GENERICO > USO CONTINUO", "Brick GEN; valsartana+anlodipino, anti-hipertensivo"),
    "7897595602022": ("SIMILAR > RX-SIMILAR", "similar (Sandoz); diclofenaco, anti-inflamatorio de uso pontual"),
    "7897595602503": ("SIMILAR > ANTIMICROBIANO", "Brick SIM; aciclovir, antiviral"),
    "7897595630773": ("SIMILAR > RX-SIMILAR", "similar, referencia Tandrilax; relaxante muscular + AINE"),
    "7897595630803": ("SIMILAR > RX-SIMILAR", "similar, referencia Tandrilax; relaxante muscular + AINE"),
    "7897595618733": ("SIMILAR > RX-SIMILAR", "Brick SIM; sildenafila"),
}


def main() -> None:
    conn = sqlite3.connect(DB)
    politica = {r[0] for r in conn.execute("SELECT classificacao_exata FROM politica_categoria")}
    desconhecidas = {c for c, _ in CLASSIFICACAO.values()} - politica
    if desconhecidas:
        raise SystemExit(f"Categoria sem politica: {sorted(desconhecidas)}")

    for ean, (exata, motivo) in CLASSIFICACAO.items():
        descricao = conn.execute("SELECT descricao FROM produto WHERE ean = ?", (ean,)).fetchone()
        if not descricao:
            raise SystemExit(f"{ean} nao esta em produto -- importe a nota antes.")
        pai, filho = (x.strip() for x in exata.split(">"))
        conn.execute("UPDATE produto SET grupo_pai_nf = ?, grupo_filho_nf = ? WHERE ean = ?",
                     (pai, filho, ean))
        conn.execute(
            "INSERT INTO subcategoria_classificada (ean, classificacao_exata, fonte) VALUES (?, ?, ?) "
            "ON CONFLICT(ean) DO UPDATE SET classificacao_exata = excluded.classificacao_exata, "
            "fonte = excluded.fonte", (ean, exata, FONTE))
        print(f"{ean}  {descricao[0][:38]:38s} -> {exata:28s} ({motivo})")
    conn.commit()
    print(f"\n{len(CLASSIFICACAO)} EANs classificados.")


if __name__ == "__main__":
    main()
