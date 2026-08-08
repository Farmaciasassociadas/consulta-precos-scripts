# Regras da raiz — leia antes de qualquer coisa

Estas regras existem por um motivo medido: sessões deste projeto já morreram
com `prompt is too long: 562072 tokens > 200000 maximum`. Do lado do usuário
isso aparece como **"a internet do Claude Code caiu"** — não é rede, é o
pedido sendo recusado por tamanho. As regras equivalentes já existiam em
`ConsultaPrecosEAN/CLAUDE.md`, mas só carregavam **depois** de o agente tocar
naquela pasta, isto é, depois de já ter lido o log e estourado o contexto.
Por isso elas estão aqui, na raiz.

## 1. Nunca ler arquivo de dados por inteiro

Custo real se lidos inteiros:

| arquivo | tamanho | tokens |
|---|---:|---:|
| `ConsultaPrecosEAN/precos.csv` | 3,9 MB | **~994 mil** |
| `ConsultaPrecosEAN/log_assistente.txt` | 699 KB | ~179 mil |
| `ConsultaPrecosEAN/dicionario_termos.json` | 258 KB | ~66 mil |
| os 8 `*.user.js` juntos | 320 KB | ~82 mil |

O teto é 200 mil. **Um `Read` em `precos.csv` estoura sozinho.**

Em vez disso: `Grep` com `head_limit`, `Read` com `offset`/`limit`, ou um
script Python pontual que **agrega antes de imprimir** (contagens, percentis,
tabelas) — nunca o conteúdo cru.

## 2. Pedido de "ver o log" → `analisar_logs.py`, nunca `Read`

```bash
python analisar_logs.py --dia DD/MM/AAAA   # o dia inteiro
python analisar_logs.py --ultimas N        # as ultimas N buscas
```

Roda em `C:\Users\docze\ConsultaPrecosEAN`, 100% local, zero tokens de IA.
Vale para qualquer forma do pedido ("olha o log", "como foi a coleta", "por
que deu erro"), não só perguntas explícitas de desempenho.

## 3. Onde o código realmente mora

O app **não** fica em `C:\Claude` — fica em `C:\Users\docze\ConsultaPrecosEAN`
(dados vivos, `log_assistente.txt`, `precos.csv`, perfil do Chrome).

Os userscripts existem em **duas** cópias, e a que vale é a pública:

- `C:\Claude\repo_scripts` — **fonte da verdade em produção.** É o clone do
  repo público (`origin` = `github.com/Farmaciasassociadas/consulta-precos-scripts`).
  O `@updateURL` dos scripts aponta para
  `raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/…`,
  e é daí que o Violentmonkey baixa. **Correção que não chega aqui não roda.**
  Repo público: nunca colocar preço, EAN ou dado de negócio.
  (A pasta `C:\Claude\consulta-precos-scripts` está **vazia** e não é usada —
  o nome parecido já causou edição no lugar errado.)
- `C:\Users\docze\ConsultaPrecosEAN\*.user.js` — cópia versionada no repo
  privado, sincronizada com o 2º PC (SRVBIG-LJ1) pelo `iniciar.py`. Manter
  idêntica à pública.

Ao corrigir um userscript: editar, **subir a `@version`** (sem isso o
Violentmonkey não baixa a atualização), espelhar nas duas pastas e publicar
na pública.

## 4. Nunca fazer merge textual dos arquivos de dados

`precos.csv`, `log_assistente.txt`, `dicionario_termos.json` e
`aprendizado_nomes.csv` são reconciliados **por chave** pelo `iniciar.py` na
abertura do app, nunca por merge de texto do git. Os dois PCs commitam dados
no mesmo `main`. Se um push de código for rejeitado por divergência de dados,
publique só o código (ex.: `git worktree` a partir de `origin/main` +
`cherry-pick`) e deixe os dados para o sync do app.

## 5. Nunca resetar para `origin/main` — confira a branch antes

Aconteceu em 07/08/2026: uma sessão rodou `git reset --hard origin/main`
estando em `redesign-ui`. Isso **descartou a ponta da branch** — três commits
de código (redesign do painel do MiniPreço, piso competitivo, codemaps) mais
dois de precificação de outra sessão. Do lado do usuário apareceu como
"sumiu o preço sugerido do painel": o app voltou a uma versão antiga.

Este repo trabalha em **`redesign-ui`**, não em `main`. Além disso, **várias
sessões mexem nele ao mesmo tempo** — a ponta da branch pode conter trabalho
que não é seu.

Antes de qualquer operação destrutiva de git:

```bash
git branch --show-current      # confirme onde você está
git log --oneline -5           # veja o que vai perder
```

Para desfazer, resete para a **própria** branch, nunca para `main`:

```bash
git reset --hard origin/$(git branch --show-current)
```

Se o objetivo era só descartar mudanças de um arquivo, use
`git checkout -- <arquivo>` em vez de resetar a branch inteira.

**Commite e dê push cedo.** Foi o `push` que salvou o trabalho nesse
incidente: os commits sobreviveram em `origin/redesign-ui` e a recuperação
foi um reset de volta. Trabalho não commitado teria sumido — como sumiu mais
cedo no mesmo dia, quando o sync do `iniciar.py` sobrescreveu edições que
ainda estavam só no working tree.

Se algo já se perdeu: `git reflog` guarda tudo por 90 dias, e
`git branch <nome> <sha>` resgata o commit antes de qualquer outra manobra.

## 6. Nunca buscar dentro das pastas de runtime/backup

`chrome_perfil_robo/`, `backups_locais/`, `__pycache__/`, `terceiro_pc/` e
`.graphify/` não têm código relevante — uma busca recursiva solta cai em
centenas de arquivos binários/LevelDB. Escopar sempre.

## 7. Motor de precificação: fonte da verdade é o app

O motor (engine/mercado.py, engine/economico.py, engine/chamariz.py e
parametros.toml) existe em **duas** cópias, e a que vale é a do app:

- `C:\Users\docze\ConsultaPrecosEAN\precificacao` — **fonte da verdade.**
  É a versão mais atualizada (vizinhança local, piso competitivo, banda de
  balcão, status honestos). **Editar o motor aqui, nunca em `C:\Claude`.**
- `Precificação\precificador` — cópia batch/SQLite para a rodada por Excel.
  Manter idêntica rodando `python Precificação\sincronizar_motor.py` (ou
  `--check` para só verificar).

O `rodada_v2.py` (orquestrador SQLite) é específico deste repo e pode ser
editado aqui, desde que mantenha a mesma semântica do app — os trechos
marcados com `Paridade com o app` são o espelho de `calcular_preco_sugerido.py`.
