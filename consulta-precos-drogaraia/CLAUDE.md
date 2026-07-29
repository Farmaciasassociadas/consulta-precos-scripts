# Contexto obrigatório antes de programar

Antes de implementar qualquer mudança neste repositório (ou no repo irmão
`consulta-precos-scripts`), leia primeiro:

1. **`.graphify/GRAPH_REPORT.md`** — resumo do grafo de código (god nodes,
   comunidades, conexões) gerado pelo graphify. Para detalhes de arestas
   específicas, consulte `.graphify/graph.json` (nós/edges brutos).
2. **`docs/architecture.json`** — especificação (legível, texto) do diagrama
   de arquitetura gerado pelo archify, cobrindo os dois repositórios
   (`consulta-precos-drogaraia` + `consulta-precos-scripts`): coleta em
   campo, ponte navegador→desktop (protocolo clipboard/`document.title`) e
   dicionário/IA. Prefira ler este JSON a abrir o `docs/architecture.html`
   (o HTML é renderizado/pesado; o JSON tem a mesma informação em texto).
3. Se o código mudar de forma que invalide o diagrama ou o grafo
   (novos componentes, novo protocolo de comunicação, nova farmácia),
   regenere com as skills `archify` e `graphify` e atualize
   `docs/architecture.json`/`.html`.

Este repo é privado e contém o app desktop (`assistente_eans.py`) e o
protótipo web (`web/`). O repo `consulta-precos-scripts` é público e
distribui só os userscripts (Violentmonkey) + `dicionario_termos.json`,
sem dados de negócio.
