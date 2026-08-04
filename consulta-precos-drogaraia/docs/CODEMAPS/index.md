<!-- Generated: 2026-08-03 | Files scanned: ~6 | Token estimate: ~300 -->
# Codemaps — consulta-precos-drogaraia

Este repo é pequeno (protótipo web: 582 linhas ao todo). A arquitetura
completa (coleta em campo, ponte navegador→desktop, dicionário/IA,
cobrindo também o repo irmão `consulta-precos-scripts`) **já está
mapeada** em:

- [`../architecture.json`](../architecture.json) — spec legível do
  archify, texto (preferir a este a abrir o `.html`, que é pesado).
- [`../../.graphify/GRAPH_REPORT.md`](../../.graphify/GRAPH_REPORT.md) —
  resumo do grafo de código (god nodes, comunidades).

Não duplicar esse conteúdo aqui. Este diretório só cobre o que o
archify/graphify **não** cobrem: o protótipo web em detalhe de função.

Ver [frontend.md](frontend.md).

## Nota — código real do app desktop não está neste repo

O `CLAUDE.md` deste repo cita `assistente_eans.py` como fazendo parte
dele, mas o app desktop de verdade mora em
`C:\Users\docze\ConsultaPrecosEAN` (ver `CLAUDE.md` da raiz `C:\Claude`,
regra 3). Esta pasta só tem `web/` (protótipo), `docs/` (archify) e os
dois `.md` de contexto — nada de Python.
