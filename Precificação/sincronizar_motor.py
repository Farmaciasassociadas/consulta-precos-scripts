"""Sincroniza o motor de precificacao do APP (fonte da verdade) para este projeto.

O motor de precificacao mais atualizado vive DENTRO do app desktop em
C:\\Users\\docze\\ConsultaPrecosEAN\\precificacao (branch redesign-ui). Este
projeto (Precificacao/) e a versao batch/SQLite que gera a rodada por Excel --
ele NAO tem logica propria: sempre copie do app para ca.

Uso:
    python sincronizar_motor.py          # copia e verifica
    python sincronizar_motor.py --check  # so verifica, nao copia

Arquivos sincronizados (copia 1:1, hash verificado):
    engine/mercado.py  engine/economico.py  engine/chamariz.py
    config/parametros.toml

O rodada_v2.py e o orquestrador SQLite deste projeto e fica de fora da copia,
mas deve manter a mesma semantica do app (calcular_preco_sugerido.py): os
comentarios "Paridade com o app" marcam os pontos que espelham o app.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
from pathlib import Path

APP = Path(os.environ.get(
    "CONSULTA_PRECOS_DIR", str(Path.home() / "ConsultaPrecosEAN"))) / "precificacao"
AQUI = Path(__file__).resolve().parent / "precificador"

PARES = [
    (APP / "engine" / "mercado.py", AQUI / "engine" / "mercado.py"),
    (APP / "engine" / "economico.py", AQUI / "engine" / "economico.py"),
    (APP / "engine" / "chamariz.py", AQUI / "engine" / "chamariz.py"),
    (APP / "dados" / "parametros.toml", AQUI / "config" / "parametros.toml"),
]


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    so_checar = "--check" in sys.argv
    ok = True
    for origem, destino in PARES:
        if not origem.exists():
            print(f"ERRO: fonte nao encontrada: {origem}")
            ok = False
            continue
        if not destino.exists() or sha256(origem) != sha256(destino):
            if so_checar:
                print(f"DIVERGENTE: {destino.name}")
                ok = False
            else:
                shutil.copy2(origem, destino)
                print(f"sincronizado: {destino.name}")
        else:
            print(f"igual: {destino.name}")
    if so_checar:
        if ok:
            print("Motor sincronizado com o app (fonte da verdade).")
        else:
            print("Motor DIVERGENTE -- rode sem --check para sincronizar.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
