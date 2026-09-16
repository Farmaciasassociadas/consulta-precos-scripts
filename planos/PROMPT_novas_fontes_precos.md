# Novas fontes de preço para o MP2 + como tratá-las no motor

Contexto para encaixar nas etapas do plano do MiniPreço 2. Tudo abaixo foi
**medido em 27/08/2026**, não é estimativa. Onde o número é frágil, está dito.

## Antes de tudo: qual repo recebe o quê

Isto atravessa dois repositórios, e confundi-los é o erro documentado no CLAUDE.md:

- **`C:\MiniPreco2\coletor\farmacias.py`** — os adaptadores de coleta. É aqui que
  entram as farmácias novas. Repo de testes, não é produção.
- **`C:\Users\docze\ConsultaPrecosEAN\precificacao\`** — o motor de precificação
  (`engine/mercado.py`, `engine/economico.py`, `dados/parametros.toml`). É a
  **fonte da verdade** do motor. As mudanças de motor da parte 3 são **daqui**,
  não do MP2. `C:\Claude\Precificação\precificador` é cópia batch; sincronizar
  com `python Precificação\sincronizar_motor.py`.

Se o plano do MP2 só cobre coleta, a parte 3 vira dependência externa: o MP2 pode
coletar as 14 lojas sem que o motor mude, **desde que ninguém as marque como
locais** — elas nascem remotas por default e o motor já as trata como validação.
O que não pode acontecer é ligar as 14 e deixar o alvo de preço cair nelas.

---

## 1. 14 farmácias novas que o adaptador VTEX atual já coleta

Sondei o endpoint que o `farmacias.py` já usa
(`/api/catalog_system/pub/products/search?fq=alternateIds_Ean:<EAN>`) contra ~40
e-commerces de farmácia brasileiros. Quatorze responderam. **Não precisa de
parser novo — é uma linha por loja no dict `VTEX`.** O `ler_vtex` já resolve
`sellerId=='1'` -> `OK`, terceiro -> `MARKETPLACE`, `IsAvailable=false` ->
`INDISPONIVEL`.

```python
VTEX = {
    # ... as 4 atuais (drogariasp, paguemenos, saojoao, precopopular) ...
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

Cobertura medida no **catálogo inteiro** (3.012 EANs por loja, 46.060
requisições, 12 min com 16 threads, **zero erro de rede**):

| loja | cobertura | OK | MKTP | INDISP |
|---|---:|---:|---:|---:|
| extrafarma | 67% | 2123 | 96 | 119 |
| pacheco | 66% | 2022 | 149 | 203 |
| catarinense | 62% | 2032 | 0 | 58 |
| venancio | 58% | 1889 | 15 | 99 |
| drogal | 57% | 1888 | 0 | 157 |
| indiana | 57% | 1891 | 0 | 172 |
| globo | 55% | 1812 | 0 | 4 |
| santalucia | 50% | 1643 | 0 | 167 |
| tamoio / drogasmil / farmalife / rosario | 50% | 1632 | 10 | 3 |
| farmaconde | 47% | 1552 | 0 | 0 |
| anossadrogaria | 33% | 1082 | 0 | 187 |

Custo operacional: ~46 mil requisições por rodada completa. Vale espaçar/agendar.

### Bloqueadas ou fora do padrão (não gastar tempo)

- **Onofre**, **Drogaria Araújo**: são VTEX mas devolvem **403** (bot-detect).
  Só via coletor local (Fase 3), como Droga Raia e Panvel.
- **Ultrafarma, Callfarma, Minas Brasil, Bifarma, Netfarma**: plataforma própria,
  404 no endpoint VTEX. Precisariam de parser dedicado.
- **Consulta Remédios** (`consultaremedios.com.br`): responde ao adaptador VTEX,
  mas **NÃO adicionar**. `sellerId == "1"` ali é *"Nexodata do Brasil S.A."*, a
  operadora da plataforma — não uma farmácia. O `ler_vtex` gravaria isso como
  `OK` ("preço da própria farmácia") quando é preço de agregador de loja
  desconhecida. É exatamente o defeito que o docstring do `farmacias.py` diz ser
  o único que o motor não consegue perceber.

---

## 2. Comparadores avaliados — o que fazer com cada um

| site | veredito | evidência |
|---|---|---|
| **App Pharma** (`apppharma.com.br`) | **Sim, mas só pelo que sobrar** | API REST pública sem token. Acurácia contra o site ao vivo: São João 100%, Drogaria SP 96%, Preço Popular 84%, Pague Menos 67%; desvio mediano 0,0%. Atraso mediano 1,6 dia. Depois de ligar as 14 acima, o que ele acrescenta é **Drogasil, Droga Raia e Panvel** — as três sem API aberta. |
| **CliqueFarma** (`cliquefarma.com.br`) | **Só para cadastro, não para preço** | Melhor casamento por EAN de todos (92% do catálogo, `sku` == EAN, 0,13 s/EAN, uma chamada). Mas as lojas com oferta são e-commerces pequenos irrelevantes para Maringá, e **35% das ofertas têm mais de 30 dias** (Drogal 99 d, Beleza na Web 99 d). Uso legítimo: resolver EAN -> `name`, `presentation`, `manufacturer`, `kind_name` (Genérico/Ético), `classification` para os itens sem nome/eixo no `precos.csv` — catálogo inteiro em ~7 min, sem gastar chamada de IA no classificador. |
| **Farmaindex** (`farmaindex.com`) | **Não** | 0% de acerto contra a Drogaria São Paulo ao vivo, com viés sistemático de **−19,8%**. Sem data por oferta. Só medicamento (5% de cobertura em perfumaria). |
| **Preço Remédio** (`precoremedio.com.br`) | **Não usar** | O `robots.txt` proíbe scraping explicitamente e declara Cloudflare WAF + edge function de bot-detect. |
| **FarmaCompare**, **Preço Medicamentos** | Baixa prioridade | O primeiro só redireciona para as mesmas lojas VTEX; o segundo é alto custo / doença rara, não é o mix. |

### Endpoints do App Pharma (se for implementado)

```
GET https://back.apppharma.com.br/public/v2/produto?size=5&app=false&page=0&busca=<EAN>
    -> totalElements==1 é casamento exato; 0 é NAO_ENCONTRADO (nunca devolve catálogo)
GET https://back.apppharma.com.br/public/v2/produto/<produtoId>            -> traz gtin p/ conferir
GET https://back.apppharma.com.br/public/v2/produto/estabelecimento/<id>   -> lojas + preço + link
GET https://back.apppharma.com.br/public/historico-precos/produto/<id>     -> histórico com dataLcto
```

`gtin` bateu com o EAN pedido em 40/40. ~2,1 s por EAN. **Ressalva:** o
`robots.txt` deles proíbe `/public/*`, que é o caminho da API. É decisão de risco
do usuário, não técnica — não decidir isso sozinho.

### Endpoints do CliqueFarma (para o uso de cadastro)

```
GET https://feed-api.app.cliquefarma.com.br/product/<EAN>
    -> {sku, name, presentation, manufacturer, kind_name, classification,
        offers:[{pharma_name, price, availability, is_marketplace, updated_at}]}
```

`sku` bateu com o EAN pedido em 58/58. `robots.txt` é `Allow: /`.

---

## 3. Como tratar as fontes novas no motor (a parte que importa)

### 3.1 O princípio: elas são REMOTAS, não concorrentes

Todas as 14 são e-commerce nacional — Pacheco e Venancio (RJ), Drogal e Farma
Conde (interior de SP), Indiana (MG), Catarinense (SC), Rosário (DF/GO),
Extrafarma (N/NE). **Nenhuma tem loja em Maringá.** O `[mercado.vizinhanca]` do
`parametros.toml` já diz o que fazer com isso: *"as demais NÃO existem na cidade
— servem para VALIDAR o preço, não para definir o alvo."*

**Nenhuma entra em `sites_locais`.** Elas nascem remotas por default.

Por que isso não é opinião — nível medido no catálogo inteiro,
`mediana(14 novas) / mediana(locais)`, mesmo EAN, n=2.686:

```
p25 0,821   |   mediana 0,919   |   p75 1,000
```

São **8% mais baratas** que os concorrentes locais, com cauda a −18%.

### 3.2 O buraco real: quando NÃO há vizinhança local

Quando `alvo_so_local` é falso (1.133 EANs, 38% dos que têm coleta fresca), o
`selecionar_vizinhanca` devolve `mantidas` inteiro e o alvo cai em **todos** os
sites. Aí `alvo_por_ranking` pega o 2º/3º mais barato — e com 14 remotas baratas
a mais, o 2º mais barato deixa de ser um local.

Impacto medido no alvo do ranking, catálogo inteiro:

| cenário | mediana | p10 | itens caindo >5% |
|---|---:|---:|---:|
| somando as 14 cruas | **−11,3%** | −30,0% | **474 de 693 (68%)** |
| com dedup de grupo econômico | −9,4% | −28,6% | 436 (63%) |
| **bloco remoto = 1 voto** | **+1,8%** | −4,1% | **48 de 537 (9%)** |

**Correção proposta**, em `engine/mercado.py`, `selecionar_vizinhanca`, no ramo
sem vizinhança local: o mercado remoto é **um** sinal ("o preço nacional
online"), não 19 votos.

```python
# Sem vizinhanca local o alvo caia em TODOS os sites, e o ranking pegava o 2o
# mais barato entre e-commerces que nao disputam este cliente. Medido em
# 27/08/2026 no catalogo inteiro: alvo -11,3% na mediana, 68% dos itens caindo
# mais de 5%. Colapsar os remotos num preco so' derruba isso para 9%.
# E' a mesma filosofia de _mediana_geografica: cada concorrente contribui com UM
# preco. Aqui o "concorrente" e' o canal e-commerce nacional inteiro.
remotos = [o for o in mantidas if o.site not in locais_cfg]
if locais and remotos:
    sintetica = Observacao("_remoto", median(o.preco for o in remotos), "OK", None)
    return locais + [sintetica], len(lojas_distintas), False, locais
```

**Invariante que não pode ser quebrado:** `n`, `cv`, `filtro.mantidas`, a
divergência Brick/web e as 4 camadas continuam vendo **todas** as observações.
Só o conjunto que vira ALVO é colapsado. É a separação que o comentário do
`calcular_mercado` já descreve ("os remotos seguem valendo como evidência de que
o preço está certo").

Efeito colateral bom: isso **conserta um defeito que já existe hoje**. Com 4
remotas contra 1-2 locais o ranking já cai nas remotas — por isso a mediana do
cenário bom é **+1,8%**, não 0%.

### 3.3 Deduplicar clones — obrigatório, não cosmético

Identidade de preço ao centavo, medida em milhares de EANs:

| par | n | idêntico | razão mediana | o que é |
|---|---:|---:|---:|---|
| drogasmil = tamoio | 1640 | **97%** | 1,000 | grupo d1000 |
| drogasmil = farmalife | 1640 | **93%** | 1,000 | grupo d1000 |
| farmalife = tamoio | 1642 | **90%** | 1,000 | grupo d1000 |
| extrafarma = paguemenos | 1986 | 53% | 1,000 | grupo Pague Menos |
| catarinense ~ precopopular | 1779 | 21% | 1,000 | mesmo nível |
| drogariasp ~ pacheco | 1676 | 20% | 1,000 | grupo DPSP |

```toml
[mercado.vizinhanca.apelidos_site]
saopaulo = "farmasp"
drogasmil = "tamoio"       # 97% identico ao centavo em 1.640 EANs
farmalife = "tamoio"       # 93%
extrafarma = "paguemenos"  # 53% identico, razao mediana 1,000 (mesmo grupo)
```

Sem isso há um modo de falha **novo e concreto**: o `cluster_acima_brick` no
caminho do Brick conta **observações**, não lojas distintas
(`evidencia = len(acima)`, `n_min = 2`). Dois clones da d1000 sozinhos devolvem
ao conjunto preços que a banda de âncora rejeitou — uma empresa virando "dois
testemunhos". A contagem por lojas distintas hoje só existe sob PMPF.

**Não aliasar** `rosario` e `globo`: são do mesmo grupo mas precificam diferente
(razão 0,993 e 0,971, identidade abaixo de 20%). São vozes separadas de verdade.
Também **não aliasar** `pacheco`/`drogariasp` nem `catarinense`/`precopopular`
numa primeira rodada: razão 1,000 mas identidade de só 20%/21% — é mesmo nível de
preço, não o mesmo catálogo. Decidir depois, com os dois ligados e medindo.

### 3.4 O ganho — é aqui que elas valem

Nos 1.133 itens sem vizinhança local:

```
evidência remota confiável (n>=4, CV<=0,20):   341 -> 499   (+46%)
camada MAD roda (n>=5):                        267 -> 768   (+188%)
EANs sem NENHUM preço fresco que passam a ter:  67
```

A camada MAD quase triplicando é o maior ganho, e é de **qualidade**, não de
nível: mais itens passam a ter filtro estatístico de outlier em vez de ficarem
sem proteção nenhuma.

### 3.5 O que NÃO mexer

- **`sites_locais`** — nenhuma das novas entra. É a decisão inteira.
- **Piso e teto competitivo** — já são estritamente locais
  (`teto_competitivo_local` filtra por `sites_locais`; `ancora_competitiva_local`
  só roda com `alvo_so_local`). Ficam intactos.
- **`premio_balcao` / fator Brick-web** — as novas são web como as outras, e o
  prêmio é aplicado uma vez sobre a referência consolidada. Empilhar
  multiplicador aqui é erro conhecido.
- **`peso_geografico`** — não listar as novas. Com 3.2 elas nem chegam lá como 14
  entradas.

---

## 4. Achados de lucratividade (independentes das fontes novas)

### 4.1 `alvo_por_ranking` não é invariante de escala

O rank é posição absoluta; o que ela significa depende do tamanho da lista.
Medido em 1.812 EANs com vizinhança local:

```
tamanho do alvo local:  3 lojas -> 797 EANs  |  4 lojas -> 1015 EANs  |  nunca mais que 4
```

| rank | preço / menor local | é o MAIS CARO em |
|---:|---:|---:|
| 2 | 1,061x | 0% dos itens |
| 3 | 1,190x | 44% |
| 4 | 1,267x | **100%** |

Com `rank_alvo = min(rank_alvo, len(ordenados))`, **rank 4 hoje não é "quarto
lugar", é "ser o mais caro do bairro, sempre"**.

Defeito que já está rodando: o mesmo `rank_alvo = 2` entrega **percentil 50%
quando a coleta pegou 3 locais e 38% quando pegou 4**. A posição competitiva
varia conforme a coleta do dia deu certo — isso é acaso, não decisão comercial.

### 4.2 O Desenho B, se um dia quiser o "4º lugar" de verdade

Alternativa ao 3.2: deixar todos os sites entrarem no alvo e trocar `rank_alvo`
por **percentil**. Medido em 1.720 EANs (lista completa mediana de 15 lojas após
dedup, p10 10, p90 17):

```
O preço de HOJE (rank 2 entre os locais) fica no percentil 38% da lista completa
                                                    (p25 20%  p75 57%)

Se o alvo passasse a ser a lista COMPLETA, mantendo rank absoluto:
  rank 2 -> -14,2%    rank 3 -> -8,9%    rank 4 -> -5,3%
  rank 6 -> -0,1%     rank 8 -> +3,8%
```

Ou seja: no Desenho B, **"4º lugar" sai 5,3% MAIS BARATO que hoje**, não mais
caro. Para manter o preço atual seria rank ~6; para ganhar margem, rank 8+.
É viável e é o único caminho em que o parâmetro vira um dial de margem legítimo,
mas ancora o preço no e-commerce nacional em vez da loja da esquina, e o spread
p25–p75 de 20–57% mostra que a posição de hoje não é consistente.

**Recomendação: Desenho A agora (3.2); Desenho B como decisão comercial separada,
depois, com o usuário.** Não misturar as duas coisas na mesma etapa.

### 4.3 Alavanca que não depende de site novo nenhum

**598 itens (16% do catálogo) estão sem Curva ABC.** Sem curva,
`alvo_por_ranking` cai no default do tier: `PADRAO = 2` — o mesmo tratamento de
Curva A/KVI. Destes, 311 têm vizinhança local e são os de **maior ticket mediano
do catálogo**:

| curva | n com vizinhança | rank 2 -> rank 3 | preço mediano |
|---|---:|---:|---|
| A | 942 | +11,4% | R$ 28,44 -> R$ 32,11 |
| **AUSENTE** | 311 | **+10,5%** | **R$ 43,64 -> R$ 48,95** |

Ausência de curva não é evidência de alta visibilidade. O default para item sem
curva deveria ser o de B/C (rank 3), não o de A. **Uma linha em
`[ranking.rank_alvo_por_tier]`**, sem tocar em nenhum item já decidido KVI.

### 4.4 46% do catálogo não tem teto nenhum

Cobertura das duas âncoras oficiais, por categoria:

| categoria | itens | com PMC | com PMPF | **sem teto nenhum** |
|---|---:|---:|---:|---:|
| PERFUMARIA | 1.414 | 4% | 6% | **94%** |
| VAREJO | 330 | 10% | 8% | **90%** |
| GENERICO | 503 | 98% | 93% | 1% |
| ETICOS | 671 | 77% | 82% | 13% |
| **TOTAL** | 3.737 | 51% | 47% | **46% (1.731 itens)** |

Nota: o comentário no `parametros.toml` que diz "PMC só cobre 16,3% do catálogo"
está **desatualizado** — a cobertura real hoje é 51%. Vale corrigir o comentário.

Nesses 1.731 itens a única defesa contra preço absurdo é o `excede_sanidade` e o
teto competitivo local — e 54% deles nem vizinhança local têm. É o buraco onde
nasceram o Paracetamol a R$ 313 e o Vick a R$ 587 documentados no TOML.

### 4.5 Mercado Livre — encaixa nesse buraco, e só nele

Para perfumaria e varejo o cliente não compara com a Drogasil, compara com o ML.
E é justamente o segmento sem PMC, sem PMPF e com a pior cobertura de coleta.

Tratamento, e é **diferente** das 14 farmácias:

- **Nunca no alvo.** Preço de ML tem frete embutido, kit, vendedor cinza,
  apresentação divergente — repetiria o erro do Brick com preço de caixa.
- **Status próprio** (ex.: `CANAL_MARKETPLACE`). Não reusar `MARKETPLACE`, que já
  significa "vendedor terceiro dentro do site da farmácia", coisa diferente.
- **Papel único: teto de realidade nos 1.731 itens sem teto.** Sugestão acima do
  praticado no ML não bloqueia o preço — levanta bandeira para revisão humana,
  como a divergência Brick/web já faz.

**Bloqueio:** a API do ML fechou para consulta anônima (403 em
`/sites/MLB/search`, confirmado). Precisa de app registrado em
developers.mercadolivre.com.br. É cadastro em nome do usuário — **não criar
conta, pedir a ele.** Com token, o adaptador é do tamanho dos outros.

---

## 5. Ordem sugerida e testes

1. **`apelidos_site` dos clones** (3.3). TOML puro, sem código. Tem de vir antes
   de qualquer loja nova ser ligada, senão o clone vota dobrado desde o dia um.
2. **Colapso do bloco remoto** (3.2). Uma função em `selecionar_vizinhanca`.
   Teste em `test_vizinhanca.py`: dois locais a 20 e 22, dez remotos a 14 — o
   alvo do ranking tem de sair do par local, não do bloco de 14. Conferir também
   que `n`, `cv` e `filtro.mantidas` continuam contando os 12.
3. **Ligar as 14 lojas no `VTEX`** do MP2 e rodar a comparação antes/depois no
   catálogo inteiro, não em amostra.
4. **Default de rank para item sem Curva ABC** (4.3). Independente, pode ir em
   paralelo.
5. **CliqueFarma para cadastro** (parte 2). Independente do motor.
6. **App Pharma** só pelo que sobrar (Drogasil, Raia, Panvel) — e só depois de
   decidir o `robots.txt` com o usuário.
7. **Mercado Livre** como teto de realidade, depois do token.

Desenho B (4.2) e o alias `pacheco`/`drogariasp` ficam fora desta leva: são
decisões comerciais, não técnicas.

---

## 6. Ressalvas honestas sobre os números acima

- As simulações de impacto no ranking aplicaram `alvo_por_ranking` **direto sobre
  as observações frescas**, sem passar pelas 4 camadas de outlier, pela banda de
  âncora, pelo Brick nem pelo PMPF. As magnitudes são portanto **limite superior
  do dano**; o motor real filtraria parte. A ordem entre os três cenários (68% x
  63% x 9%) é válida porque os três receberam o mesmo tratamento.
- Os piores casos do cenário bom (até −73%) são **erro de apresentação
  pré-existente sendo exposto**, não dano novo. Exemplo: Tadalafila 20mg C/4,
  EAN 7891317127800 — a coleta atual tem drogaraia R$ 36,38, nissei R$ 166,88 e
  paguemenos R$ 204,99, enquanto as novas mostram R$ 15 a R$ 62. O dado novo está
  revelando que os R$ 166/204 estão errados. É argumento a favor de a camada MAD
  passar a rodar (+188%), não contra as fontes novas.
- Cobertura e acurácia das lojas novas foram medidas **num único dia**. Frescor e
  taxa de falha ao longo do tempo ainda não têm série histórica.
- A coluna `nome` de cada coleta continua sendo a defesa contra comparar avulso
  com caixa. Com 14 fontes novas isso fica **mais** provável, não menos.
