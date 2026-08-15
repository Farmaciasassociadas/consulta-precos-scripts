"""Avisa quando a reconciliacao do sync desfizer o que foi gravado nas bases do app.

Aconteceu em 15/08/2026: 2.897 classificacoes gravadas em 14/08 viraram 215
depois do sync com o SRVBIG-LJ1, e so foi notado por acaso dois dias depois. A
causa era edicao nao commitada, mas o efeito -- dado sumindo em silencio -- pode
voltar por outros caminhos (merge driver, git checkout, o outro PC gravando por
cima da mesma chave).

Uso:
    python vigia_sync.py --marcar    # grava a expectativa atual como referencia
    python vigia_sync.py             # confere; sai 1 se algo regrediu
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

APP = Path(r"C:\Users\docze\ConsultaPrecosEAN")
REFERENCIA = Path(__file__).resolve().parent / "dados" / "vigia_sync_referencia.json"


def _normalizar(valor: str) -> str:
    digitos = "".join(c for c in str(valor).split(";", 1)[0] if c.isdigit())
    return digitos.lstrip("0") or digitos


def medir() -> dict[str, int]:
    """Numeros que so devem subir. Cada um morreu de um jeito diferente ja."""
    m: dict[str, int] = {}

    with open(APP / "categorias_produtos.csv", encoding="utf-8-sig", newline="") as f:
        linhas = list(csv.DictReader(f))
    m["categorias_total"] = len(linhas)
    m["categorias_auditadas"] = sum(1 for r in linhas
                                    if (r.get("origem") or "").startswith("estoque_erp_"))
    m["categorias_manuais"] = sum(1 for r in linhas
                                  if (r.get("origem") or "") == "manual_minipreco")

    eans = [l for l in (APP / "eans.txt").read_text(encoding="utf-8",
                                                    errors="replace").splitlines() if l.strip()]
    contagem = collections.Counter(_normalizar(l) for l in eans)
    m["eans_linhas"] = len(eans)
    m["eans_com_preco"] = sum(1 for l in eans if ";" in l)
    # Unico que deve DESCER: entra negado para a mesma regra "so sobe" valer.
    m["eans_sem_duplicata"] = -sum(1 for v in contagem.values() if v > 1)

    for nome, arquivo in (("negativos", "eans_negativos.csv"),
                          ("embalagens", "embalagens_produtos.csv"),
                          ("custos", "custo_produtos.csv")):
        with open(APP / arquivo, encoding="utf-8-sig", newline="") as f:
            m[nome] = sum(1 for _ in csv.DictReader(f))

    marcas = [l.strip() for l in (APP / "marcas_proprias.txt").read_text(encoding="utf-8")
              .splitlines() if l.strip() and not l.startswith("#")]
    m["marcas_proprias"] = len(marcas)
    return m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--marcar", action="store_true", help="grava o estado atual como referencia")
    args = ap.parse_args()

    atual = medir()
    if args.marcar or not REFERENCIA.exists():
        REFERENCIA.parent.mkdir(parents=True, exist_ok=True)
        REFERENCIA.write_text(json.dumps(
            {"gravado_em": datetime.now().isoformat(timespec="seconds"), "valores": atual},
            indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"Referencia gravada em {REFERENCIA}")
        for k, v in atual.items():
            print(f"  {k:24s} {v}")
        return

    referencia = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    esperado = referencia["valores"]
    regressoes = [(k, esperado[k], atual.get(k, 0))
                  for k in esperado if atual.get(k, 0) < esperado[k]]

    print(f"Referencia de {referencia['gravado_em']}")
    for k in esperado:
        agora, antes = atual.get(k, 0), esperado[k]
        sinal = "!!" if agora < antes else ("  " if agora == antes else "+ ")
        print(f" {sinal} {k:24s} {antes:6d} -> {agora:6d}")
    if not regressoes:
        print("\nOK: nada regrediu.")
        return
    print(f"\nREGRESSAO em {len(regressoes)} indicador(es) -- o sync provavelmente "
          f"desfez alguma gravacao.\nRecuperar com os backups *_pre_estoque_erp* e "
          f"COMMITAR logo em seguida (sem commit o proximo sync desfaz de novo).")
    sys.exit(1)


if __name__ == "__main__":
    main()
