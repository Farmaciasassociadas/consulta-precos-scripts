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
4. **`docs/CODEMAPS/index.md`** — aponta pros dois acima e cobre o que
   eles não cobrem (detalhe de função do protótipo `web/`). Regenere com
   `/update-codemaps` se o protótipo mudar bastante.

Este repo é privado e contém só o protótipo web (`web/`) e a documentação
de arquitetura (`docs/`). O app desktop de produção (`assistente_eans.py`
e os mixins) **não** fica aqui — fica em `C:\Users\docze\ConsultaPrecosEAN`
(ver `docs/CODEMAPS/architecture.md` de lá). O repo `consulta-precos-scripts`
é público e distribui só os userscripts (Violentmonkey) +
`dicionario_termos.json`, sem dados de negócio.
