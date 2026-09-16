# Plano: novas fontes de preço no MP2 + ponte MP2 → MiniPreço Desktop

Documento único, para ser executado **numa janela de contexto separada** desta
em que foi escrito. Por isso é redundante de propósito: repete fatos que já
foram investigados, cita arquivo:linha sempre que possível, e não assume que
quem for executar lembra de uma conversa anterior.

Gerado em 27/08/2026. Duas frentes de trabalho, **independentes uma da outra**
(tocam arquivos quase disjuntos, podem ser feitas em qualquer ordem ou em
paralelo por sessões diferentes):

- **Frente A** — novas fontes de preço pro MP2 + duas correções no motor de
  precificação. Baseada em `C:\Claude\planos\PROMPT_novas_fontes_precos.md`
  (leia o original — aqui ele foi reorganizado em fases executáveis, não
  substituído).
- **Frente B** — o MP2 passa a poder pedir pro MiniPreço de balcão (rodando
  numa VM dedicada) coletar as farmácias que ele mesmo não consegue coletar
  sozinho. Desenhada numa sessão inteira de perguntas e respostas com o dono
  do projeto; as decisões já tomadas estão na tabela da seção 6 e **não devem
  ser re-perguntadas**.

---

## 0. Como usar este documento

1. Cada fase tem: objetivo, arquivos tocados (com âncora de linha), a mudança
   em si (código quando já existe pronto, descrição precisa quando não),
   como testar, e o que "pronto" significa.
2. **Releia o arquivo antes de editar.** As âncoras de linha foram conferidas
   em 27/08/2026 lendo os arquivos de verdade, mas o repositório muda — trate
   número de linha como "procure por aqui perto", não como coordenada exata.
3. Cada fase é de um repositório específico. Antes de mexer, confirme a
   branch daquele repo (`git branch --show-current`) — são três repositórios
   git **separados** (`C:\MiniPreco2`, `C:\Users\docze\ConsultaPrecosEAN`,
   `C:\Claude`), cada um com seu próprio estado. Não presuma que a branch de
   um é a mesma dos outros.
4. Onde este plano diz "decisão pendente do usuário", **não decida sozinho** —
   pare, pergunte, documente a resposta antes de prosseguir.
5. Onde este plano diz "verificar antes de implementar", é porque a
   investigação parou no limite do que dava para confirmar sem tocar em
   produção (banco de dados, Chrome de verdade, etc.) — não é preguiça, é
   fronteira real do que uma leitura de código resolve sozinha.

---

## 1. Contexto e mapa de repositórios

Do `C:\Claude\CLAUDE.md` (raiz), resumido:

| Pasta | O que é | Branch/estado a conferir |
|---|---|---|
| `C:\Users\docze\ConsultaPrecosEAN` | **Fonte da verdade** do robô de coleta (#1) e do MiniPreço desktop (#2, `minipreco.py`, mesma classe `AssistenteEAN`). Repo privado. Tem `precos.csv`, `log_assistente.txt`, perfil do Chrome. | confira antes de editar |
| `C:\Users\docze\ConsultaPrecosEAN\precificacao` | **Fonte da verdade** do motor de precificação (`engine/mercado.py`, `engine/economico.py`, `dados/parametros.toml`). | mesmo repo acima |
| `C:\MiniPreco2` | MP2 — campo de testes da próxima geração. Coleta sem navegador (`coletor/farmacias.py`) + coleta com navegador só pra Raia/Panvel (`local/coletar_local.py`) + painel (`painel/`) + motor próprio em SQLite/Postgres schema `mp2`. Repo separado de propósito (tem chave de serviço). **Não é produção hoje**, mas o usuário confirmou que **vai virar** o painel principal (ver seção 7, item 3). | confira antes de editar |
| `C:\Claude\Precificação\precificador` | Cópia batch/SQLite do motor, sincronizada com `python Precificação\sincronizar_motor.py`. Não editar o motor aqui. | branch deste repo (`C:\Claude`) |
| `C:\Claude\dashboard` | Painel de produção atual (lê schema `precificacao`). Fora do escopo deste plano, mas mencionado porque é o "outro" painel — não confundir os dois. | — |

Regra de ouro repetida em cinco lugares do CLAUDE.md: **nunca fazer merge
textual dos arquivos de dados** (`precos.csv`, `log_assistente.txt`, etc.) —
eles são reconciliados por chave pelo `iniciar.py`, não pelo git. E **nunca
resetar pra `origin/main`** sem antes rodar `git branch --show-current` e
`git log --oneline -5` — houve um incidente real de perda de commits em
07/08/2026 por isso.

---

## 2. Vocabulário e invariantes que atravessam as duas frentes

- **GTIN/EAN**: 13 dígitos com zero à esquerda é a chave canônica
  (`MiniPreco2/motor/calcular.py:114-126`, função `_gtin`). GTIN-14 com
  indicador `0` colapsa pra unidade; indicador 1-8 é caixa (chave diferente).
- **Farmácia = `chave` textual (slug)**: `drogariasp`, `paguemenos`,
  `saojoao`, `precopopular`, `farmasp`, `nissei`, `drogaraia`, `panvel` são as
  8 que o robô cobre (`ConsultaPrecosEAN\config_app.py:74`, lista `SITES`).
  O MP2 cobre as mesmas 6 primeiras via API + as 2 últimas via
  `coletar_local.py` (Playwright). **As 14 lojas novas da Frente A usam slugs
  novos que o robô NUNCA vai conhecer** — isso importa pra Frente B, ver
  seção 5.
- **Vocabulário de status**, igual nos dois lados (robô e MP2):
  `OK`, `MARKETPLACE`, `INDISPONIVEL`, `NAO_ENCONTRADO`, `ERRO_404`,
  `TIMEOUT`, e só no coletor com navegador, `DIVERGENTE`.
- **Schema é escolha deliberada, não acidente**: `mp2.observacao_farmacia` e
  `precificacao.observacao_farmacia` são tabelas diferentes no MESMO projeto
  Supabase (`https://qzlabizghmjjoilgdvoy.supabase.co`). `MiniPreco2/motor/nuvem.py:108-109,115-116`
  **recusa em código** (`RuntimeError`) qualquer escrita com `schema="precificacao"`.
  Não remover essa trava.

---

## 3. FRENTE A — Novas fontes de preço + correções no motor

Fonte: `C:\Claude\planos\PROMPT_novas_fontes_precos.md` (leia o original antes
de começar — aqui só a ordem virou fases numeradas com critério de pronto).

### A0. Pré-requisito de leitura

Releia `PROMPT_novas_fontes_precos.md` inteiro antes de tocar em qualquer
arquivo — ele tem tabelas de medição (cobertura por loja, impacto no ranking)
que não foram reproduzidas aqui por extenso. Este plano só reorganiza a ordem
de execução dele em fases com critério de "pronto".

### A1. Fase 1 — `apelidos_site` (dedup de clones de rede)

**Por quê primeiro**: se uma loja clone (ex.: `drogasmil`/`tamoio`, 97%
idêntico ao centavo em 1.640 EANs) for ligada antes do alias existir, ela vota
dobrado desde o dia 1 — inclusive no `cluster_acima_brick`, que conta
**observações**, não lojas distintas (`n_min=2` em `evidencia = len(acima)`).

**Arquivo**: `ConsultaPrecosEAN\precificacao\dados\parametros.toml`, seção
`[mercado.vizinhanca.apelidos_site]` (já existe, tem `saopaulo = "farmasp"`
hoje — conferir a linha exata antes de editar).

**Mudança** (TOML puro, sem código):
```toml
[mercado.vizinhanca.apelidos_site]
saopaulo = "farmasp"
drogasmil = "tamoio"       # 97% identico ao centavo em 1.640 EANs
farmalife = "tamoio"       # 93%
extrafarma = "paguemenos"  # 53% identico, razao mediana 1,000 (mesmo grupo)
```

**Não aliasar** (decisão já tomada pelo `PROMPT_novas_fontes_precos.md`,
seção 3.3, com medição): `rosario`/`globo` (razão 0,993 e 0,971, identidade
<20% — vozes de preço separadas de verdade) nem `pacheco`/`drogariasp` nem
`catarinense`/`precopopular` (razão 1,000 mas identidade só 20-21% — mesmo
nível de preço, não mesmo catálogo; decidir depois, com os dois ligados e
medindo de novo).

**Pronto quando**: TOML válido, `python -c "import tomllib; tomllib.load(open('parametros.toml','rb'))"`
não estoura, e o teste da Fase 2 (abaixo) já conta lojas distintas
corretamente com os apelidos novos.

### A2. Fase 2 — colapso do bloco remoto em `selecionar_vizinhanca`

**Por quê antes de ligar as 14 lojas**: sem isso, ligar 14 remotas baratas a
mais faz o alvo cair **-11,3%** na mediana nos 1.133 EANs sem vizinhança
local (68% dos itens caindo mais de 5%). Com o colapso, o mesmo cenário vira
**+1,8%** (o efeito colateral bom: conserta um viés que já existe hoje com
4 remotas vs 1-2 locais).

**Arquivo**: `ConsultaPrecosEAN\precificacao\engine\mercado.py`, função
`selecionar_vizinhanca` (linha **332-369**, conferida em 27/08/2026 — código
atual reproduzido abaixo por completo pra não haver dúvida de onde entra o
patch):

```python
def selecionar_vizinhanca(
    mantidas: list[Observacao], params: dict[str, Any]
) -> tuple[list[Observacao], int, bool, list[Observacao]]:
    cfg = params["mercado"].get("vizinhanca")
    if not cfg or not cfg.get("ativo"):
        return mantidas, 0, False, []
    locais_cfg = set(cfg.get("sites_locais") or ())
    locais = [o for o in mantidas if o.site in locais_cfg]
    apelidos = {k: v for k, v in (cfg.get("apelidos_site") or {}).items()}
    lojas_distintas = {apelidos.get(o.site, o.site) for o in locais}
    if len(lojas_distintas) >= cfg.get("n_min_local", 3):
        return locais, len(lojas_distintas), True, locais
    return mantidas, len(lojas_distintas), False, locais    # <-- linha 369, é aqui que entra o patch
```

**Patch proposto** (do `PROMPT_novas_fontes_precos.md`, seção 3.2),
substituindo só a última linha (369):

```python
    # Sem vizinhanca local o alvo caia em TODOS os sites, e o ranking pegava o 2o
    # mais barato entre e-commerces que nao disputam este cliente. Medido em
    # 27/08/2026 no catalogo inteiro: alvo -11,3% na mediana, 68% dos itens caindo
    # mais de 5%. Colapsar os remotos num preco so' derruba isso para 9%.
    remotos = [o for o in mantidas if o.site not in locais_cfg]
    if locais and remotos:
        sintetica = Observacao("_remoto", median(o.preco for o in remotos), "OK", None)
        return locais + [sintetica], len(lojas_distintas), False, locais
    return mantidas, len(lojas_distintas), False, locais
```

**⚠️ Atenção — ambiguidade que o patch original não cobre, achada nesta
revisão**: a condição é `if locais and remotos`. Quando `locais` está
**vazio** (zero concorrente local, não só "abaixo do mínimo"), o patch cai no
`return mantidas, ...` de sempre — ou seja, **não colapsa**, e o alvo continua
caindo entre dezenas de remotos individuais exatamente como hoje. Antes de
fechar esta fase, decidir e testar explicitamente o caso "zero locais":
provavelmente a resposta certa é colapsar do mesmo jeito
(`return [sintetica], 0, False, []` quando `locais` é vazio mas `remotos`
não), mas **isso não estava no prompt original e precisa de medição própria**
antes de generalizar — não estender por analogia sem conferir o efeito no
`alvo_por_ranking` (uma lista com 1 item só não tem "2º colocado").

**Invariante que não pode quebrar** (do prompt original): `n`, `cv`,
`filtro.mantidas` e a divergência Brick/web continuam vendo **todas** as
observações — só o conjunto que vira alvo é colapsado. Não filtrar `mantidas`
em si.

**Teste** (`test_vizinhanca.py`, criar caso novo):
1. Caso do prompt original: dois locais a 20 e 22, dez remotos a 14 — alvo do
   ranking tem que sair do par local (20/22), não do bloco de 14. Conferir
   também que `n`, `cv` e `filtro.mantidas` continuam contando os 12.
2. Caso novo (achado nesta revisão): **zero** locais, dez remotos a 14 —
   decidir e testar explicitamente o que `alvo_por_ranking` faz com a lista
   colapsada de 1 item, antes de marcar esta fase como pronta.

**Pronto quando**: os dois testes acima passam, e uma rodada de comparação
antes/depois no catálogo inteiro (não amostra) mostra a mediana de impacto
perto de +1,8% (não -11,3%) nos itens sem vizinhança local.

### A3. Fase 3 — ligar as 14 lojas novas no `VTEX` do MP2

**Arquivo**: `MiniPreco2\coletor\farmacias.py`, dict `VTEX` (linha **57-62**,
conferido em 27/08/2026 — hoje só tem as 4 originais).

**Mudança**:
```python
VTEX = {
    "drogariasp": "https://www.drogariasaopaulo.com.br",
    "paguemenos": "https://www.paguemenos.com.br",
    "saojoao": "https://www.saojoaofarmacias.com.br",
    "precopopular": "https://www.precopopular.com.br",
    "pacheco":        "https://www.drogariaspacheco.com.br",
    "extrafarma":     "https://www.extrafarma.com.br",
    "catarinense":    "https://www.drogariacatarinense.com.br",
    "venancio":       "https://www.drogariavenancio.com.br",
    "drogal":         "https://www.drogal.com.br",
    "indiana":        "https://www.farmaciaindiana.com.br",
    "globo":          "https://www.drogariaglobo.com.br",
    "santalucia":     "https://www.santaluciadrogarias.com.br",
    "tamoio":         "https://www.drogariastamoio.com.br",
    "drogasmil":      "https://www.drogasmil.com.br",
    "farmalife":      "https://www.farmalife.com.br",
    "rosario":        "https://www.drogariarosario.com.br",
    "farmaconde":     "https://www.farmaconde.com.br",
    "anossadrogaria": "https://www.anossadrogaria.com.br",
}
```
`ADAPTADORES` (linha 206-208) é gerado a partir de `VTEX` automaticamente
(`{chave: ... for chave in VTEX}`) — não precisa mexer nele.

**NÃO adicionar** (decisão já fechada no prompt original, seção 1):
- `Onofre`, `Drogaria Araújo` — VTEX mas 403 (bot-detect); ficam pro coletor
  local (mesmo destino de Raia/Panvel).
- `Ultrafarma`, `Callfarma`, `Minas Brasil`, `Bifarma`, `Netfarma` —
  plataforma própria, 404 no endpoint VTEX; precisariam parser dedicado, fora
  de escopo.
- `Consulta Remédios` (`consultaremedios.com.br`) — responde ao adaptador
  VTEX, mas `sellerId=="1"` ali é o operador da plataforma
  ("Nexodata do Brasil S.A."), não uma farmácia. Ligar isso gravaria preço de
  agregador como se fosse preço de loja própria — exatamente o defeito que o
  próprio docstring de `farmacias.py:27-31` diz ser o único que o motor não
  detecta.

**⚠️ Achado nesta revisão, não estava no prompt original — impacto de
latência**: `MiniPreco2\coletor\coletar.py`, função `rodar()` (linha
**55-85**), faz um `for chave in escolhidas: coleta = farmacias.consultar(chave, ean)`
**serial** — cada farmácia é uma requisição HTTP síncrona, uma depois da
outra, sem paralelismo. Com 6 lojas isso já significa 6 round-trips por EAN;
com 20 (6 + 14 novas), o tempo de resposta de **cada clique** no botão
"Pesquisar" do painel (`servir.py:60`, que chama exatamente esta função antes
de responder) triplica. Isso interage direto com a Frente B — o desenho lá
assume que "mostrar resultado online na hora" é rápido. **Antes de fechar a
Fase 3, medir o tempo de resposta real do `/coletar` do painel com as 20
lojas ligadas**, e se ficar lento demais (a UX pretendida em Frente B depende
de resposta rápida), paralelizar o `for` de `rodar()` com
`concurrent.futures.ThreadPoolExecutor` (são requisições de rede independentes,
sem estado compartilhado entre farmácias — só cuidado com a variável
`contagem`, que precisa virar thread-safe ou ser somada depois de coletar
todos os resultados, não durante o loop).

**Teste**: rodar comparação antes/depois no **catálogo inteiro** (não
amostra), conferir números de cobertura batem aproximadamente com a tabela do
prompt original (extrafarma ~67%, pacheco ~66%, etc. — pode variar, os
números do prompt são de uma sondagem única de um dia).

**Pronto quando**: as 14 lojas aparecem em `ADAPTADORES`, o `demo()` de
`farmacias.py` continua passando (não muda, só testa os parsers existentes),
e a Fase 2 (colapso remoto) já está em produção **antes** deste passo ir ao
ar de verdade — senão o alvo cai -11% no meio tempo.

### A4. Fase 4 — default de rank pra item sem Curva ABC

Independente das fases 1-3, pode ir em paralelo.

**Achado** (prompt original, seção 4.3): 598 itens (16% do catálogo) não têm
Curva ABC. Sem curva, `alvo_por_ranking` cai no default do tier `PADRAO = 2`
— tratamento de Curva A/KVI. Os 311 desses com vizinhança local têm o
**maior ticket mediano do catálogo** (R$ 43,64), maior até que Curva A
(R$ 28,44). Ausência de curva não é evidência de alta visibilidade.

**Arquivo**: `ConsultaPrecosEAN\precificacao\dados\parametros.toml`, seção
`[ranking.rank_alvo_por_tier]` (confirmar chave exata no arquivo — o prompt
não deu o nome literal da entrada a adicionar, só a seção).

**Mudança**: adicionar entrada pro tier "ausente"/"sem curva" apontando pra
rank 3 (tratamento de B/C), não rank 2 (tratamento de A/KVI). **Antes de
editar, ler como o código resolve "sem curva" hoje** — precisa achar o ponto
exato onde cai no default do `PADRAO=2` pra saber se dá pra resolver só no
TOML ou se precisa de uma linha de código também (o prompt implica que é só
TOML, "uma linha", mas isso não foi verificado nesta revisão).

**Pronto quando**: item sem Curva ABC com vizinhança local usa rank 3, itens
com Curva A/KVI continuam em rank 2 (nada muda pra eles).

### A5. Fase 5 — CliqueFarma pra cadastro/classificação (não pra preço)

Independente do motor, pode ir em paralelo com tudo acima.

**Uso correto**: resolver EAN → `name`, `presentation`, `manufacturer`,
`kind_name` (Genérico/Ético), `classification` — só pra preencher itens sem
nome/eixo no `precos.csv`, **evitando gastar chamada de IA no classificador**.
Catálogo inteiro em ~7 min medido.

**Não usar pra preço**: 35% das ofertas têm mais de 30 dias (Drogal 99 dias,
Beleza na Web 99 dias), e as lojas com oferta são e-commerces pequenos
irrelevantes pro mercado de Maringá.

**Endpoint**:
```
GET https://feed-api.app.cliquefarma.com.br/product/<EAN>
    -> {sku, name, presentation, manufacturer, kind_name, classification,
        offers:[{pharma_name, price, availability, is_marketplace, updated_at}]}
```
`sku` bate com o EAN pedido (medido 58/58). `robots.txt` é `Allow: /`.

**Pronto quando**: existe um script/adaptador que consulta por EAN e só
extrai os campos de cadastro (nunca `offers[].price`), grava nos campos de
nome/eixo do `precos.csv` (ou tabela equivalente) só quando esses campos
estão vazios hoje.

### A6. Fase 6 — App Pharma (BLOQUEADA — decisão do usuário)

**Não implementar sem essa decisão.** `robots.txt` do App Pharma proíbe
`/public/*`, que é exatamente o caminho da API usada. É risco pro usuário
assumir (não técnico) — perguntar antes de escrever qualquer linha de código
desta fase.

Se aprovado: cobre o que sobra depois das 14 novas — Drogasil, Droga Raia e
Panvel (as três sem API aberta). Acurácia medida: São João 100%, Drogaria SP
96%, Preço Popular 84%, Pague Menos 67%; atraso mediano 1,6 dia.

```
GET https://back.apppharma.com.br/public/v2/produto?size=5&app=false&page=0&busca=<EAN>
    -> totalElements==1 e' casamento exato; 0 e' NAO_ENCONTRADO
GET https://back.apppharma.com.br/public/v2/produto/<produtoId>
GET https://back.apppharma.com.br/public/v2/produto/estabelecimento/<id>
GET https://back.apppharma.com.br/public/historico-precos/produto/<id>
```

### A7. Fase 7 — Mercado Livre como teto de realidade (BLOQUEADA — token)

**Não implementar até o usuário criar o app em developers.mercadolivre.com.br
e fornecer o token.** É cadastro em nome dele — não criar conta por ele.

**Onde encaixa, e só aí**: os 1.731 itens (46% do catálogo) sem PMC nem PMPF
— maior concentração em PERFUMARIA (94% sem teto) e VAREJO (90% sem teto).

**Tratamento, deliberadamente diferente das 14 farmácias**:
- Nunca entra no alvo (preço de ML tem frete embutido, kit, vendedor cinza).
- Status próprio, ex. `CANAL_MARKETPLACE` — **não reusar** `MARKETPLACE`
  (que já significa "vendedor terceiro dentro do site da farmácia").
- Papel único: teto de realidade — sugestão acima do praticado no ML levanta
  bandeira pra revisão humana, não bloqueia o preço (mesma filosofia da
  divergência Brick/web).

### A8. Nota de correção de comentário (baixo risco, fazer junto da Fase 4)

O comentário em `parametros.toml` dizendo "PMC só cobre 16,3% do catálogo"
está desatualizado — cobertura real medida é 51%. Corrigir o texto do
comentário (não muda comportamento).

---

## 4. FRENTE B — Ponte MP2 → MiniPreço Desktop

Contexto de negócio: o MP2 (painel rodando no PC "Pichau") vai poder pedir
pro MiniPreço de balcão — rodando numa VM isolada, também no PC Pichau —
coletar as farmácias que o MP2 não sabe coletar sozinho (Raia, Panvel) ou que
falharam na tentativa online (as outras 6, quando o status vier
`NAO_ENCONTRADO`/`ERRO_404`/`TIMEOUT`).

Esta frente foi desenhada numa sessão de perguntas e respostas completa
(23 decisões, tabela na seção 6). **Não reabrir essas decisões** — se algo
aqui parecer estranho, é porque foi escolhido deliberadamente com um trade-off
explícito, não esquecido.

### Por que uma VM, e por que no PC Pichau (não no PC do dono)

O robô/MiniPreço usa o clipboard do Windows como canal de dados:
`ConsultaPrecosEAN\_captura_mixin.py:788` faz `pyperclip.copy("")` a cada
ciclo de consulta (apaga o clipboard do sistema), e `:1988` lê o clipboard a
cada ~250ms durante a coleta. Isso é **incompatível** com alguém usando
Ctrl+C/Ctrl+V no mesmo Windows ao mesmo tempo — não é bug, é a arquitetura do
canal de fallback (o canal primário é o título da aba, `AEAN|`, mas o
fallback de clipboard roda sempre). Área de trabalho virtual do Windows não
resolve — clipboard é global entre áreas virtuais da mesma sessão. Só uma
VM com **clipboard compartilhado desligado** isola isso de verdade.

O PC Pichau foi escolhido porque é usado por outra coisa durante o dia
(decisão do usuário, Q15 = a) — a VM continua sendo necessária ali pelo
mesmo motivo.

### B0. Infraestrutura (sem código — preparação de máquina)

1. **VirtualBox** (gratuito) no PC Pichau — não Hyper-V (Windows 11 **Home**
   não tem Hyper-V).
2. Criar VM Windows, **modo de rede Bridged** (a VM precisa de IP próprio na
   LAN, alcançável pelo painel do MP2 rodando no host — modo NAT só permite
   tráfego de saída).
3. **Desligar compartilhamento de clipboard** entre host e guest (padrão sem
   Guest Additions já vem desligado — conferir explicitamente, não assumir).
4. **Auto-logon** no Windows guest (decisão Q20 = aceito, trade-off:
   senha fica no registro do Windows, ofuscada mas reversível por quem tiver
   acesso à máquina — aceitável porque é uma VM isolada numa rede fechada).
5. Instalar dentro da VM: Python + dependências do
   `ConsultaPrecosEAN\requirements` (conferir o arquivo exato do repo),
   Chrome + Violentmonkey com os 8 userscripts atualizados
   (`captura_preco.user.js` = Raia, + os 7 outros — conferir versão mínima
   exigida: a mensagem em `_captura_mixin.py:1424` menciona
   "v5.3/3.9/3.9/3.7/2.4 ou mais novos" pro **modo paralelo**, que Frente B
   vai depender — ver B2).
6. **Conta de serviço no Supabase** (decisão Q21 = conta dedicada, papel
   `coletor`): **verificar antes de criar uma nova** — o comentário em
   `ConsultaPrecosEAN\sessao.py:8-9` diz literalmente *"O token de máquina
   NÃO morreu: a coleta desassistida continua com ele, agora no papel
   `coletor`, que só escreve observação de preço."* Isso sugere que **já
   existe** um mecanismo de token de máquina com papel `coletor`, pensado
   exatamente pra coleta desassistida — o arquivo de credencial é
   `ConsultaPrecosEAN\nuvem_config.json` (mesmo nome de arquivo que
   `MiniPreco2\motor\nuvem.py:26` lê como fallback!). **Antes de criar uma
   conta nova do zero, confirmar**: (a) esse token de máquina já existe e
   está em uso por outro fluxo (`carregar_para_nuvem.py`?); (b) se sim, se ele
   já tem (ou pode ganhar) grant de escrita em `mp2.observacao_farmacia`
   também — nesse caso a Q21 já está satisfeita por infraestrutura existente,
   sem precisar de uma segunda conta. Ver B3 para o porquê disso importar.
7. Copiar `nuvem_config.json` (ou o token novo, se precisar mesmo criar um)
   pra dentro da VM, no mesmo caminho relativo que o robô espera.
8. **Login inicial manual, uma vez**, do MiniPreço dentro da VM com a conta
   de serviço — isso grava `%LOCALAPPDATA%\MiniPreco\sessao.json`
   (`ConsultaPrecosEAN\sessao.py:34-35`) com o refresh token. Depois disso,
   `Sessao.retomar()` (`sessao.py:136-147`) funciona sozinho em todo boot
   seguinte, **sem precisar digitar senha de novo** — o auto-logon do Windows
   (item 4) cuida de abrir a sessão do Windows, e a sessão do Supabase já
   fica gravada em disco esperando. Só quebra se o refresh token for revogado
   ou ficar 30 dias sem uso (`sessao.py:183` comentário) — improvável, já que
   a VM vai ser usada todo dia.
9. **Tarefa Agendada** no host Pichau: iniciar a VM no boot
   (`VBoxManage startvm <nome-vm> --type headless` ou `gui`, decidir se quer
   ver a tela da VM ou não — headless é suficiente, ninguém precisa olhar) +
   iniciar `python painel/servir.py` do MP2 (esse roda no **host**, não na
   VM — ver B4).
10. **Tarefa Agendada / pasta Startup** dentro do guest da VM: iniciar
    `python minipreco.py --servico` (flag nova, ver B1) depois do auto-logon.

### B1. Modo `--servico` no MiniPreço (janela escondida, bandeja)

**Decisão já tomada (Q1, Q10)**: não criar um app novo/"lite". Adicionar uma
flag no `minipreco.py` existente.

**Arquivo**: `ConsultaPrecosEAN\minipreco.py`, função `main()` (linha
**2790-2815**, reproduzida por completo abaixo — é curta):

```python
def main():
    LOG.info("[MINIPRECO] Sessão iniciada")
    from ui_login import PedirCredenciais, avisar_bloqueado
    acesso = acesso_mod.abrir(PedirCredenciais())
    if acesso.bloqueado:
        avisar_bloqueado(acesso)
    if acesso.degradado:
        LOG.warning("[MINIPRECO] Abrindo em modo degradado: %s", acesso.motivo)

    janela = ttkb.Window(themename=TEMAS_BOOTSTRAP.get(TEMA_ATUAL, "flatly")) if ttkb else tk.Tk()
    aplicativo = MiniPreco(janela, acesso=acesso)
    ...
    janela.mainloop()
```

**Mudança**: aceitar `--servico` via `argparse`/`sys.argv`. Quando presente:
- `PedirCredenciais()` **não pode abrir diálogo** (ninguém está sentado lá).
  Boa notícia, achada nesta revisão: `acesso_mod.abrir(pedir_credenciais, ...)`
  (`acesso.py:88-137`) já tenta `Sessao.retomar()` **antes** de chamar
  `pedir_credenciais` — só cai no diálogo se não houver sessão gravada válida
  (`acesso.py:113-127`). Com o login manual do item B0.8 já feito, na
  prática `pedir_credenciais` nunca vai ser chamado. Mesmo assim, passar
  **`lambda: None`** (não uma função que levanta exceção — `abrir()` não
  envolve a chamada a `pedir_credenciais()` em `try/except`, então uma
  exceção ali derruba o serviço inteiro). `lambda: None` é tratado
  explicitamente por `abrir()` como "Ninguém entrou" →
  `Acesso(degradado=True, motivo="Ninguém entrou.")` (`acesso.py:116-117`) —
  vira um estado de erro visível e logável (`acesso.degradado`), não um
  crash nem um travamento. Esse caminho já tem teste próprio em
  `acesso.py:202-203` (`abrir(lambda: None, ...)` → `degradado`), então é
  comportamento coberto, não uma suposição.
- Depois de criar `janela` e `aplicativo`, chamar `janela.withdraw()` em vez
  de deixar a janela visível.
- Adicionar um ícone de bandeja via **pystray** (dependência nova, única
  desta fase) com opções mínimas: "Abrir" (`janela.deiconify()`), "Sair"
  (`aplicativo.fechar_programa()`).
- Iniciar o listener HTTP da B2 nesse mesmo modo (só faz sentido com
  `--servico`, não no MiniPreço de balcão normal — reduz superfície de
  ataque).

**Pronto quando**: `python minipreco.py --servico` sobe sem abrir janela
visível, aparece ícone na bandeja, login acontece sozinho (sessão gravada),
e o app fica pronto pra receber pedidos (B2) enquanto roda a coleta contínua
normalmente se estiver configurada.

### B2. Endpoint HTTP + fura-fila sem abortar

**Decisões já tomadas**: Q17 (push direto), Q18 (assíncrono — responde 202 e
segue em background), Q19 (token fixo no header), Q22 (fura fila do site
específico, sem abortar navegação em curso).

**Novo módulo**, ex. `ConsultaPrecosEAN\servico_desktop.py`, iniciado só em
modo `--servico`. Reaproveitar o padrão de `http.server` que o próprio MP2 já
usa em `painel/servir.py` (consistência de estilo, zero dependência nova).

```python
# esboço, não código final -- a sessao que for implementar deve reler
# _captura_mixin.py e minipreco.py antes de fechar os detalhes
TOKEN = os.environ.get("TOKEN_SERVICO_DESKTOP")  # ou de um arquivo de config local

class Prioridade(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.headers.get("X-Token") != TOKEN:
            return self._responder(401, {"erro": "token invalido"})
        pedido = json.loads(self.rfile.read(...))
        gtin, farmacias = pedido["gtin"], pedido["farmacias"]
        self._responder(202, {"status": "recebido"})
        # NAO chamar atender_pedido_prioritario direto daqui -- ver aviso de
        # thread-safety logo abaixo.
        self.app.janela.after(0, lambda: self.app.atender_pedido_prioritario(gtin, farmacias))
```

**⚠️ Cuidado de thread-safety, achado nesta revisão — fácil de esquecer e
fácil de não perceber em teste manual**: `http.server` atende cada conexão
numa thread própria (é `ThreadingHTTPServer`, igual `servir.py:157` do MP2).
**Tkinter não é thread-safe** — nenhum código que toque estado do app
(`self._pq`, `self._pw`, `EANS`, qualquer widget) pode ser chamado direto da
thread da requisição HTTP. O jeito certo é sempre agendar o trabalho de
volta na thread principal do Tk com `self.janela.after(0, funcao)`, como no
esboço acima — nunca chamar `atender_pedido_prioritario`,
`_paralelo_enfileirar` ou `EANS.append` diretamente de dentro de `do_POST`.
Isso é o tipo de bug que passa limpo num teste manual (rápido, sem
concorrência real) e falha de forma intermitente em produção — exatamente o
perfil de erro mais caro de depurar depois.

**`atender_pedido_prioritario(gtin, farmacias)`** — a parte que precisa de
cuidado, porque **nenhum ponto de entrada existente serve pronto**:

- `consultar_item_unico`/`consultar_linha_inteira`/`buscar_ean_avulso`
  (`_captura_mixin.py:1449,1459,1504`) **recusam se `self.executando` for
  True** ("Pause a consulta em andamento...", linha 1450-1451 etc.) — exatamente
  o estado em que a VM vai estar na maioria do tempo (coleta contínua rodando).
  Não dá pra chamar essas funções direto.
- `_paralelo_enfileirar(itens, substituir=False)` (`_captura_mixin.py:1100-1107`)
  hoje só **acrescenta ao fim** da deque de cada site
  (`.append(it)`) e já deduplica contra o que estiver em qualquer fila
  (`ja = {(it[1], it[2]) ...}`). **Não existe hoje um jeito de inserir na
  frente** — isso precisa ser adicionado: um parâmetro novo
  (ex. `prioridade=False`) que, quando `True`, faz `.appendleft(it)` em vez
  de `.append(it)` na deque do site certo (`self._pq.setdefault(it[2], deque())`).
  `_paralelo_despachar(site)` (`_captura_mixin.py:1237-1259`) já faz
  `fila.popleft()` — ou seja, uma vez que o item está na ponta esquerda, ele
  é o **próximo a sair** daquele site assim que o worker daquele site ficar
  livre. Não precisa abortar navegação em curso: se o site já está com uma
  aba ocupada (`w["ocupado"]`), o item prioritário só espera aquele terminar
  — é exatamente o Q22=a.
- O GTIN pedido pelo MP2 **provavelmente não está** na lista local `EANS`
  do robô (são catálogos de apps diferentes). Antes de enfileirar, replicar o
  padrão de `buscar_ean_avulso` (`_captura_mixin.py:1504-1517`): se o EAN não
  está em `EANS`, adicionar (`EANS.append(ean)` + persistir) pra conseguir um
  índice válido — os itens da fila são tuplas `(indice, ean, site)`.
- **Ramo A — app ocioso** (`self.executando` é `False`): chamar o equivalente
  de `_iniciar_consulta_avulsa([(indice, gtin, site) for site in farmacias])`
  (`_captura_mixin.py:1433-1447`) — aqui não há problema de recusa porque não
  há nada rodando.
- **Ramo B — já executando** (contínuo ou avulso em andamento): chamar
  `self._paralelo_enfileirar(itens, prioridade=True)` diretamente — o tick
  loop que já está rodando (`_paralelo_tick`, agendado via `janela.after`)
  pega o item sozinho no próximo ciclo (a cada `PARALELO_TICK_MS`=400ms).
- Guardar as tuplas `(ean, site)` desta rodada prioritária num conjunto (ex.
  `self._pedidos_mp2: set[tuple[str,str]]`) — é como a B3 vai saber quais
  resultados precisam subir pro schema `mp2` além do fluxo normal.

**Sobre anti-bot — não inventar nada novo**: o robô já tem espaçamento por
site (`PARALELO_ESPACAMENTO_POR_SITE_S`, `config_app.py:160`), atraso
aleatorizado (`sortear_delay_ms`, `util_captura.py`), pausas longas
aleatórias (`PAUSA_LONGA_MIN_MS/MAX_MS`, sorteadas por
`sortear_proxima_pausa_longa`), limite de requisições por janela de 5,5min
(`LIMITE_REQUISICOES_PROTEGIDOS`, `_captura_mixin.py:1080-1086`) e
quarentena de site (`_paralelo_sites_desativados`). Um pedido prioritário
que **fura fila** não pula essas proteções — ele só muda a ORDEM de saída da
deque, continua passando pelo mesmo `_paralelo_despachar` com o mesmo
`_pode_requisitar(site)` checado no tick (linha 1222-1223). Não desligar
nem contornar nenhuma dessas checagens pra fazer o pedido prioritário "mais
rápido" — a lentidão delas é a proteção, não um obstáculo.

**Pronto quando**: com o app parado, um POST enfileira e coleta sozinho; com
o app em coleta contínua, um POST fura a fila do site certo sem abortar o
que está em voo, e a rodada contínua retoma sozinha depois (comportamento que
já existe, `terminar_rodada`/`_reiniciar_ciclo_continuo`, não precisa mexer).

### B3. Escrever o resultado em `mp2.observacao_farmacia` (nunca `precificacao`)

**Decisão já tomada (Q6 = b)**: resultado de pedido vindo do MP2 grava só em
`mp2`, nunca em `precificacao`. O upload normal do robô continua intocado
(`_io_mixin.py:101 _subir_coleta()`, que só grava `precificacao` e só roda se
`self.acesso` existir — **não mexer nisso**, é o caminho de produção normal).

**Abordagem recomendada** (achado nesta revisão, mais simples que criar
schema-override na `nuvem.py` do robô): **reusar `MiniPreco2\motor\nuvem.py`
como está.** Essa classe já:
- tem `schema="mp2"` como default (linha 54);
- **recusa** ativamente escrever em `precificacao` (linha 108-109, 115-116) —
  proteção de graça, impossível vazar por engano;
- lê credencial de `C:\Users\docze\ConsultaPrecosEAN\nuvem_config.json`
  como fallback (linha 26) — **o mesmo arquivo que o robô já tem** na VM
  (ver B0.7). Se esse token já tiver (ou ganhar) grant de INSERT em
  `mp2.observacao_farmacia`, não precisa nem copiar credencial nova — é
  literalmente importar o arquivo `nuvem.py` do MP2 (ou copiar a classe
  `Nuvem` pra dentro do módulo novo da B2) e chamar:
  ```python
  from nuvem_mp2 import Nuvem as NuvemMP2   # copiado/importado de MiniPreco2/motor/nuvem.py
  NuvemMP2().escrever("observacao_farmacia", linhas, "gtin,farmacia,quando")
  ```

**Verificar antes de confiar nisso** (não dá pra confirmar sem acesso ao
Supabase de produção):
1. O token de `nuvem_config.json` (papel `coletor`, hoje usado pro upload em
   `precificacao`) **tem grant de escrita em `mp2.observacao_farmacia`**?
   Ver `MiniPreco2\sql\0001_schema_mp2.sql:155-214` (RLS+grants) e
   `sql\0005_grant_escrita.sql`. Se não tiver, é preciso um `GRANT`/policy
   novo pra esse papel especificamente em `mp2` — **não** criar um segundo
   token só por causa disso, primeiro tentar estender o grant do que já
   existe.
2. Se por algum motivo essa reutilização não for viável (ex. RLS realmente
   segrega os dois schemas por design e ninguém quer abrir exceção), o plano
   B alternativo é: instanciar `Nuvem(schema="mp2")` da própria
   `MiniPreco2\motor\nuvem.py` com uma **segunda** credencial dedicada
   (aí sim, conta nova) — mas isso é o plano B, não o primeiro a tentar.

**Onde encaixar a chamada**: no handler de sentinela do robô,
`_paralelo_processar_sentinela` (`_captura_mixin.py:1314`, ponto exato não lido
nesta revisão — **ler a função inteira antes de editar**). Depois do
processamento normal (que já grava em `self.resultados`/`precos.csv` via o
fluxo existente), checar `if (ean, site) in self._pedidos_mp2:` e, se sim,
montar a linha `{"gtin": ean, "farmacia": site, "quando": ..., "preco": ...,
"status": ...}` e chamar `NuvemMP2().escrever(...)`, depois
`self._pedidos_mp2.discard((ean, site))`.

**Pronto quando**: uma coleta prioritária de teste aparece em
`mp2.observacao_farmacia` (consulta direta via `MiniPreco2\motor\nuvem.py`
ou painel) e **não** aparece uma segunda vez em `precificacao.observacao_farmacia`
por causa desse pedido específico (o upload normal continua acontecendo
independentemente, isso é esperado — só não pode duplicar SÓ por causa do
pedido do MP2).

### B4. Roteamento e cache de 6h (lado do MP2)

**Decisões já tomadas**: Q3 (sempre-desktop: `drogaraia`,`panvel`;
fallback-desktop: as outras 6 quando falharem), Q23 (cache de 6h antes de
acionar a VM), Q16 (mesmo com `coletar_local.py` existindo, Raia/Panvel vão
pro robô desktop — **não** chamar `coletar_local.rodar()` neste fluxo).

**Arquivo**: `MiniPreco2\painel\servir.py`, função `_coletar()` (linha
**54-90**, código atual reproduzido por completo, conferido em 27/08/2026):

```python
def _coletar(gtins, com_navegador=True, recalcular=True):
    import coletar
    from nuvem import Nuvem

    nuvem = Nuvem()
    linhas, contagem = coletar.rodar(gtins, eco=lambda t: print(t, flush=True))

    if com_navegador:
        try:
            import coletar_local
            extras, conta2 = coletar_local.rodar(gtins, eco=lambda t: print(t, flush=True))
            linhas += extras
            for chave, quantas in conta2.items():
                contagem[chave] = contagem.get(chave, 0) + quantas
        except ImportError:
            contagem["SEM_PLAYWRIGHT"] = 2 * len(gtins)

    gravadas = nuvem.escrever("observacao_farmacia", linhas, "gtin,farmacia,quando")

    recalculadas = 0
    if recalcular:
        import calcular
        from datetime import date
        dados = calcular.carregar_insumos(nuvem, somente=gtins)
        resultados, _ = calcular.calcular_todos(dados, date.today())
        recalculadas = calcular.gravar(nuvem, resultados, date.today())

    return {"gtins": len(gtins), "observacoes": gravadas,
            "recalculadas": recalculadas, "contagem": contagem}
```

Chamada hoje de dentro de `Painel.do_POST` (`servir.py:135-137`):
```python
resumo = _coletar(gtins,
                  com_navegador=pedido.get("com_navegador", True),
                  recalcular=pedido.get("recalcular", True))
```

**⚠️ Correção feita nesta revisão**: uma versão anterior deste plano sugeria
restringir a chamada online às 6 farmácias antigas via um parâmetro
`escolhidas`. Isso estava errado e foi removido — `coletar.rodar()`
(`coletar.py:63`) já usa `sorted(farmacias.ADAPTADORES)` como default
**sem** filtro nenhum vindo de `_coletar()` (que não passa `escolhidas`,
`servir.py:60`). Não mudar isso: depois da Frente A, essa chamada
naturalmente consulta as 20 lojas (6 antigas + 14 novas), e é assim que
deve continuar — as 14 novas **devem** ser consultadas online normalmente,
elas só não entram no cálculo de roteamento pro desktop (isso é decidido
depois, olhando o resultado, não restringindo a chamada).

**Mudança real**: a partir de agora, `_coletar()` deve:
1. Continuar chamando `coletar.rodar(gtins, ...)` sem nenhum filtro de
   `escolhidas` — isso já inclui as 20 lojas depois da Frente A, e o
   resultado dessas 20 continua alimentando o cálculo de preço normalmente.
   A única mudança de roteamento é: ao decidir o que precisa ir pro desktop
   (passo 3 abaixo), **olhar o status apenas das 6 farmácias legadas**
   (`drogariasp`, `paguemenos`, `saojoao`, `precopopular`, `farmasp`,
   `nissei`) — ignorar completamente o resultado das 14 novas pra essa
   decisão específica (elas continuam valendo pro preço, só não têm
   fallback de desktop possível — ver seção 5).
2. **Não chamar mais `coletar_local.rodar()`** (o bloco `if com_navegador:`
   de `servir.py:62-72`) — substituído pelo fluxo de push da B2/B3. Deixar o
   código de `coletar_local.py` no repo, intocado, só sem chamador ativo
   neste ponto (decisão Q16 — não deletar).
3. Depois de ter os resultados online, montar a lista do que precisa ir pro
   desktop: sempre `drogaraia`/`panvel` (não têm adaptador em `ADAPTADORES`
   — não confundir com "falharam", eles nunca foram tentados online porque
   não existe caminho online pra eles) + qualquer uma das 6 de API cujo
   `status` veio `NAO_ENCONTRADO`, `ERRO_404` ou `TIMEOUT` (não
   `MARKETPLACE`/`INDISPONIVEL` — essas são respostas válidas, retry não
   muda o resultado).
4. Pra cada `(gtin, farmacia)` dessa lista: checar
   `mp2.observacao_farmacia` por uma linha com `quando` dentro das últimas
   6 horas. Se existir, usar e não acionar a VM. Se não, incluir na chamada
   de push.
5. Fazer o POST pro endpoint da VM (B2), com o token (B2/B6), payload
   `{"gtins": [...], "farmacias": [...]}` (ou uma chamada por gtin — decidir
   no momento da implementação conforme o shape que ficar mais simples do
   lado do robô).
6. Responder ao painel/frontend imediatamente com o que já se sabe (online +
   cache), e uma lista do que ficou pendente aguardando o desktop.

**Configuração nova necessária**: IP/porta da VM e o token compartilhado —
colocar num arquivo de config do MP2 (seguir o padrão já usado, `.env` como
em `motor/nuvem.py:37`, ou um `config.py` próprio do painel).

**Pronto quando**: um clique no painel mostra resultado online na hora, não
aciona a VM pra EAN+farmácia com observação de menos de 6h, e aciona a VM só
pro que realmente precisa (sempre-desktop + fallback com status de falha).

### B5. Frontend assíncrono (index.html)

**Decisão já tomada (Q2 = b)**: mostra resultado online na hora, fica
aguardando o que depende do desktop.

**Arquivo**: `MiniPreco2\painel\index.html`, handler do botão (linha
**1601-1630**, `#btn-coletar`).

**Mudança**:
1. Ao receber a resposta do `/coletar` (B4), desenhar a tabela com o que já
   veio (comportamento atual, `recarregar()`).
2. Para os itens que a resposta marcou como "pendente desktop", mostrar um
   estado visual por linha (ex. "consultando no balcão…") e entrar num
   `setInterval` que reconsulta o preço daquele gtin+farmácia a cada poucos
   segundos (3-5s — não sobrecarregar o Supabase).
3. **Timeout de 15 minutos** (decisão Q5 = b): se a linha não aparecer
   dentro desse prazo, parar de tentar e mostrar "desktop offline" em vez de
   continuar girando pra sempre.
4. Parar o polling assim que todas as linhas pendentes resolverem (achado
   OU expiraram).

**Pronto quando**: visualmente, um clique mostra resultado online
instantâneo e as linhas pendentes preenchem sozinhas conforme chegam (ou
mostram "offline" depois de 15min sem a VM ligada).

### B6. Token de autenticação

**Decisão já tomada (Q19)**: token fixo simples, não OAuth. Gerar uma string
aleatória longa (ex. `secrets.token_urlsafe(32)` em Python), guardar em
variável de ambiente/arquivo de config **nos dois lados** (VM e host Pichau)
— nunca commitar no git de nenhum dos dois repos.

### B7. Testes de ponta a ponta

Antes de considerar Frente B pronta, validar manualmente (não é código, é
checklist operacional):

1. App ocioso na VM → POST no endpoint → item aparece na tabela e é
   coletado, resultado sobe em `mp2`, não em `precificacao` por causa deste
   pedido.
2. App em coleta contínua na VM → POST no endpoint → o item fura a fila do
   site certo sem abortar o que estava em andamento, resultado sobe em
   `mp2`, coleta contínua retoma sozinha depois.
3. Cache de 6h: pedir a mesma farmácia+gtin duas vezes em menos de 6h — a
   segunda não deve gerar tráfego pra VM.
4. VM desligada → painel mostra "desktop offline" depois de 15 minutos, sem
   travar a tela.
5. Reiniciar o PC Pichau → VM sobe sozinha, Windows guest loga sozinho
   (auto-logon), MiniPreço abre em modo `--servico` sozinho (bandeja,
   sessão do Supabase recuperada sem pedir senha), painel do MP2 no host
   também sobe sozinho — tudo sem intervenção manual.
6. Token errado no header → 401, nada é enfileirado.

---

## 5. Invariante entre as duas frentes (não misturar)

**As 14 farmácias novas da Frente A nunca entram no roteamento "vai pro
desktop" da Frente B.** O robô (`ConsultaPrecosEAN\config_app.py:74`) só
conhece as 8 farmácias originais — ele não tem userscript pra Pacheco,
Extrafarma, etc. Se uma dessas 14 falhar online no MP2
(`NAO_ENCONTRADO`/`ERRO_404`/`TIMEOUT`), **não existe fallback de desktop pra
ela** — ela simplesmente fica sem preço fresco daquela fonte, e isso é
esperado (são fontes de validação/remotas por design da Frente A, seção 3.5
do prompt original — nunca deveriam virar alvo mesmo). O conjunto
"fallback-desktop" da B4 é estritamente as 6 farmácias de API originais
(`drogariasp`, `paguemenos`, `saojoao`, `precopopular`, `farmasp`, `nissei`),
nunca as novas.

---

## 6. Decisões já tomadas (Frente B) — não reabrir

| # | Pergunta | Decisão |
|---|---|---|
| Q1 | App novo ou o MiniPreço existente? | MiniPreço existente, flag `--servico` |
| Q2 | Síncrono ou mostra parcial? | Mostra online na hora, aguarda desktop |
| Q3 | Roteamento fixo, fallback, ou os dois? | Os dois: sempre (raia/panvel) + fallback (as outras 6 se falharem) |
| Q4/Q17 | Push ou polling? | Push direto (mesma rede/prédio) |
| Q5 | PC desktop offline, o que acontece? | Expira em 15min, mostra "offline" |
| Q6 | Onde grava o resultado? | Só `mp2`, nunca `precificacao` |
| Q7 | Fura fila da coleta contínua? | Sim, interrompe e retoma depois |
| Q9/Q9-bis | MP2 vira produção agora? | Ambição de longo prazo, mas **fica em `mp2` por enquanto** — migração é projeto separado |
| Q10 | App "lite" separado? | Não — flag no MiniPreço existente |
| Q11 | Hospedagem: nuvem pública ou LAN? | LAN (rede local, mesmo prédio) |
| Q12/Q15 | VM onde, e por quê? | VM no PC Pichau (usado por outra coisa também, isolamento necessário) |
| Q13/Q14 | Uma rede só ou várias lojas? | Uma rede só, mesmo prédio |
| Q16 | Raia/Panvel via `coletar_local.py` ou via robô? | Via robô desktop (mesmo com `coletar_local.py` existindo) |
| Q18 | Push síncrono ou assíncrono? | Assíncrono: 202 + polling do painel |
| Q19 | Autenticação do endpoint? | Token fixo simples |
| Q20 | Auto-logon no Windows guest? | Aceito (VM isolada, risco baixo) |
| Q21 | Conta de serviço dedicada? | Sim — **mas verificar se a infraestrutura de token `coletor` já existente satisfaz isso antes de criar uma nova** (achado nesta revisão, ver B0.6) |
| Q22 | Interromper com abort ou fura-fila? | Fura fila (appendleft), sem abortar navegação em curso |
| Q23 | Janela de cache antes de recoletar? | 6 horas |

Números que não aparecem nesta tabela (Q0, Q8, a formulação original de Q4,
Q14) foram perguntas intermediárias da sessão de grilling, resolvidas ou
substituídas por uma decisão posterior listada acima — não é lacuna de
numeração, é histórico da conversa que gerou este plano.

---

## 7. Decisões que ainda dependem do usuário — não decidir sozinho

1. **App Pharma (Frente A6)**: `robots.txt` proíbe o caminho da API usada.
   Decisão de risco, não técnica.
2. **Mercado Livre (Frente A7)**: precisa de app registrado em
   developers.mercadolivre.com.br, cadastro em nome do usuário — pedir a ele,
   não criar conta por ele.
3. **Migração do MP2 pra schema `precificacao` / virar produção de fato**
   (mencionada na Q9): projeto separado, maior que este plano — o usuário
   confirmou que é a intenção de longo prazo, mas decidiu explicitamente que
   **não é agora** (Q9-bis = a).
4. **Conta de serviço da VM (B0.6)**: se a verificação mostrar que o token
   `coletor` existente NÃO pode ganhar grant em `mp2` por alguma razão de
   design, criar uma segunda conta é uma mudança de superfície de acesso ao
   banco — confirmar com o usuário antes, não decidir sozinho mesmo sendo
   "só mais um token".

---

## 8. Ordem de execução recomendada

As duas frentes podem rodar em paralelo (arquivos quase disjuntos — a única
sobreposição de diretório é `MiniPreco2\coletor\`, mas Frente A mexe em
`farmacias.py` e Frente B em `coletar.py`/`servir.py`, arquivos diferentes).

Dentro de cada frente, a ordem importa:

**Frente A**: A1 (apelidos) → A2 (colapso remoto, com o teste do caso
zero-locais) → A3 (ligar as 14 lojas, medindo latência do `/coletar` antes de
declarar pronto) → A4/A8 (podem ir em paralelo com A1-A3) → A5 (independente)
→ A6/A7 (bloqueadas, esperar decisão do usuário).

**Frente B**: B0 (infraestrutura, inclui a verificação de credencial do
item B0.6 — não confundir com a fase B6, que é o token do endpoint) → B1
(`--servico` + bandeja) → B2 (endpoint + fura-fila) → B3
(escrita em `mp2`, depende de B0.6 resolvido) → B4 (roteamento + cache,
lado MP2) → B5 (frontend) → B6 (token, pode ir em paralelo com B2-B4) → B7
(checklist de ponta a ponta, só depois de tudo).

Se as duas frentes forem feitas por sessões diferentes ao mesmo tempo,
avisar a outra sessão antes de mexer em `MiniPreco2\coletor\coletar.py` (B4
lê `farmacias.ADAPTADORES`, que A3 aumenta de 6 para 20 chaves — não deveria
quebrar nada, já que B4 filtra por nome de farmácia explícito, mas vale
rodar os testes de B7 de novo depois que A3 for mesclada).

---

## 9. Riscos e ressalvas honestas

Da Frente A (herdadas do `PROMPT_novas_fontes_precos.md`, seção 6):

- As simulações de impacto no ranking aplicaram `alvo_por_ranking` **direto
  sobre as observações frescas**, sem passar pelas 4 camadas de outlier, pela
  banda de âncora, pelo Brick nem pelo PMPF — as magnitudes medidas são
  **limite superior do dano**, o motor real filtraria parte.
- Os piores casos do cenário bom (até -73%) são **erro de apresentação
  pré-existente sendo exposto**, não dano novo (ex. Tadalafila 20mg C/4,
  EAN 7891317127800: coleta atual tem preços de R$ 166-204, as novas fontes
  mostram R$ 15-62 — o dado novo está revelando que os R$ 166/204 estavam
  errados).
- Cobertura e acurácia das lojas novas foram medidas **num único dia** — sem
  série histórica de frescor/taxa de falha ao longo do tempo.
- A coluna `nome` de cada coleta continua sendo a defesa contra comparar
  avulso com caixa — com 14 fontes novas isso fica **mais** provável, não
  menos.

Da Frente A, achado nesta revisão (não estava no prompt original):

- O colapso do bloco remoto (A2) tem uma lacuna não coberta pro caso de
  **zero** concorrentes locais — precisa de teste e decisão próprios antes
  de generalizar por analogia.
- Ligar 14 lojas a mais no `coletar.rodar()` serial (A3) triplica o tempo de
  resposta do clique "Pesquisar" do painel — medir antes de declarar pronto,
  paralelizar se necessário.

Da Frente B:

- O mecanismo de reutilização do token `coletor` pra escrever em `mp2`
  (B3) é a parte menos verificada deste plano — depende de grants de banco
  que não dá pra confirmar sem acessar o Supabase de produção. Tratar como
  hipótese a validar, não como fato.
- Auto-logon (Q20) é uma escolha deliberada de conveniência sobre segurança
  estrita — válida pelo contexto (VM isolada, rede fechada), mas documentar
  isso em algum lugar visível pra quem for fazer auditoria de segurança
  depois não souber por que a senha está no registro.
- A "coleta paralela" (que a B2 depende para o fura-fila funcionar bem) exige
  versão mínima dos userscripts do Violentmonkey — confirmar que a VM está
  com a versão certa antes de ir ao ar, senão o fura-fila cai pro modo serial
  (mais lento, mas não quebra).
