# Os apps — leia isto antes de editar qualquer coisa

Desde **25/09/2026** só existem **dois** apps vivos. Todo o resto foi
aposentado: **não buscar, não editar e não usar como referência** — nem para
"ver como era feito". Se o pedido não deixar claro qual é o alvo, pergunte.

| Nome | Pasta (única fonte) | O que é | Como roda |
|------|---------------------|---------|-----------|
| **Farma Preço** (antigo "MiniPreço 2", MP2) | `C:\MiniPreco2` | **O app de produção de preço.** Coleta sem navegador, motor de precificação, painel no navegador servido para a loja. Supabase, schema `mp2`. Repo **privado**. Tem o próprio `CLAUDE.md`. | `python painel/servir.py` |
| **AssociChat** | `C:\Claude\chat-interno` | Chat interno das Farmácias Associadas. Electron + TypeScript + Supabase, ícone na bandeja. Nada a ver com preço. | `npm run dev` |

Desambiguação: "preço", "coleta", "Brick", "motor", "painel", "MP2", "mp2",
"Farma Preço", "etiqueta" → **Farma Preço**. "chat", "Electron", "bandeja" →
**AssociChat**.

## Aposentados — não mexer

| O quê | Onde | Situação |
|---|---|---|
| Robô de coleta (Consulta Preços EAN) | `C:\Users\docze\ConsultaPrecosEAN` | Coleta parada desde 03/09/2026. A pasta **ainda existe** só porque o servidor da loja pode ler a credencial do banco de lá (`nuvem_config.json`) quando falta o `.env` do MP2 — resolver isso antes de apagar. |
| MiniPreço desktop (balcão) | mesmo repo, `minipreco.py` | Sem uso. Substituído pelo painel do Farma Preço. |
| Userscripts / Violentmonkey | `C:\Claude\repo_scripts` e `*.user.js` do robô | Só serviam ao robô. |
| Cópia de lote (precificador SQLite, rodadas por Excel) | era `C:\Claude\Precificação` | Última rodada 13/08/2026. Backup em `DROGARIA\Claude\Obsoleto\Precificacao_lote_aposentado_2026-09-25.zip`. |
| Schema `precificacao` (Supabase) | banco | Não recebe mais nada. **Não apagar ainda:** o `mp2` usa `precificacao.normalizar_gtin`. |
| Dashboard | era `C:\Claude\dashboard` | Apagado em 07/09/2026. |

O motor de precificação agora tem **uma** fonte da verdade:
`C:\MiniPreco2\motor` (`engine/` + `dados/parametros.toml`). O
`motor/sincronizar.py` comparava com o app aposentado e não vale mais.

## Brick (todo mês)

Planilha `BRICK 1855 - PRODUTOS - MATxx_2026.xlsx` (o PDF que vem junto é só
resumo). Guardar em `DROGARIA\Claude\Brick\` no Drive e rodar, no MP2:

```bash
python motor/atualizar_brick.py "<planilha>" --dry-run
python motor/atualizar_brick.py "<planilha>"
```

# Regras da raiz

## 1. Nunca ler arquivo de dados por inteiro

Sessões já morreram com `prompt is too long` (do lado do usuário parece "a
internet do Claude Code caiu"). Um `Read` de arquivo de dados grande estoura o
contexto sozinho. Use `Grep` com `head_limit`, `Read` com `offset`/`limit`, ou
um script que **agrega antes de imprimir** — nunca o conteúdo cru.

## 2. `C:\Claude` empurra para repositório PÚBLICO

`origin` = `github.com/Farmaciasassociadas/consulta-precos-scripts`, público.
Nunca commitar aqui preço, EAN, custo, margem ou qualquer dado de negócio.
Dado de negócio fica no repo privado do MP2 ou no Drive (`DROGARIA\Claude`).

## 3. Git: confira a branch antes de qualquer operação destrutiva

Várias sessões mexem nos repos ao mesmo tempo. Antes de resetar:

```bash
git branch --show-current
git log --oneline -5
```

Para desfazer, resete para a **própria** branch, nunca para `main`. Para
descartar um arquivo, `git checkout -- <arquivo>`. Commite e dê push cedo;
se algo se perdeu, `git reflog` guarda tudo por 90 dias.

## 4. Nunca buscar dentro das pastas de runtime/backup

`chrome_perfil_robo/`, `backups_locais/`, `__pycache__/`, `terceiro_pc/`,
`node_modules/` e `.graphify/` não têm código relevante. Escopar sempre.
