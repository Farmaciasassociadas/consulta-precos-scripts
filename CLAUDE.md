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

- `C:\Claude\consulta-precos-scripts` — **fonte da verdade em produção.** O
  `@updateURL` dos scripts aponta para
  `raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/…`,
  e é daí que o Violentmonkey baixa. **Correção que não chega aqui não roda.**
  Repo público: nunca colocar preço, EAN ou dado de negócio.
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

## 5. Nunca buscar dentro das pastas de runtime/backup

`chrome_perfil_robo/`, `backups_locais/`, `__pycache__/`, `terceiro_pc/` e
`.graphify/` não têm código relevante — uma busca recursiva solta cai em
centenas de arquivos binários/LevelDB. Escopar sempre.
