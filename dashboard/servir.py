"""Servidor local do painel, sem cache.

Existe porque `python -m http.server` nao manda cabecalho de cache nenhum, e o
Chrome entao decide por conta propria guardar o arquivo. Na pratica: corrigi um
bug, recarreguei, e continuei vendo o erro antigo -- duas vezes, ate' perceber
que estava depurando uma versao que nao existia mais no disco.

Em desenvolvimento, cache e' so' armadilha: o servidor manda no-store e o
navegador busca sempre.

    python dashboard/servir.py [porta]
"""
import os
import sys
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

PASTA = Path(__file__).resolve().parent
PORTA_PADRAO = 5173


class SemCache(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, formato, *args):
        # O padrao imprime uma linha por arquivo; so' interessa o que deu errado.
        if args and str(args[1]).startswith(("4", "5")):
            super().log_message(formato, *args)


def main() -> int:
    # Argumento manda; depois PORT, que e como o preview do Claude Code
    # aponta uma porta livre quando a 5173 ja esta ocupada por outra sessao.
    porta = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT") or PORTA_PADRAO)
    servidor = HTTPServer(("127.0.0.1", porta),
                          partial(SemCache, directory=str(PASTA)))
    print(f"Painel em http://localhost:{porta}/index.html  (sem cache)")
    print("Ctrl+C para parar.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nParado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
