# Plano de implementação — Sistema de Preço Sugerido v2

Data: 02/08/2026
Base: `METODOLOGIA_PRECO_SUGERIDO.txt` + `ESTUDO_PRECIFICACAO_DROGARIA.md`
Escopo desta revisão: integrar **Brick** como fonte de mercado, redesenhar a
**exclusão de outliers** e corrigir a **alíquota do Simples por segregação de receita**.

---

## Parte 1 — O que os dados mostraram

Medições feitas sobre os arquivos reais (não estimativas).

### 1.1 Brick contra a coleta web

`Preço de mercado (Brick)` = **VUM = Real CPP ÷ Unidades**. É o preço médio
*realizado* (transacionado) em farmácias físicas da região, por EAN — não é
preço anunciado.

Cobertura:

| | EANs |
|---|---:|
| Brick com preço de mercado | 2.187 |
| Coleta web com ≥1 preço OK | 1.984 |
| Intersecção | 1.689 |
| **Só Brick, sem nenhuma coleta web** | **498** |
| Só web, sem Brick | 295 |

Razão `Brick ÷ mediana_web`, em 1.523 EANs com ≥3 sites:

| p05 | p25 | **mediana** | p75 | p95 |
|---:|---:|---:|---:|---:|
| 0,704 | 0,841 | **0,914** | 0,995 | 1,135 |

Por segmento Brick:

| Segmento | n | p25 | mediana | p75 |
|---|---:|---:|---:|---:|
| NMED | 810 | 0,849 | 0,907 | 0,983 |
| GEN | 349 | 0,816 | 0,919 | 1,025 |
| RX | 227 | 0,894 | 0,936 | 0,989 |
| SIM | 137 | 0,687 | 0,783 | 0,970 |

Por curva: A 0,929 · B 0,907 · C 0,881.

**Consequência para o modelo: o `fator físico` de 1,00–1,10 está na direção
errada.** O mercado físico regional *realiza* ~9% **abaixo** da mediana web
anunciada. Etiquetar em `mediana_web × 1,05` posiciona o produto ~15% acima do
que a região efetivamente pratica.

Ressalva honesta: parte desse gap é desconto concedido no ato de venda (VUM é
realizado; web é anunciado), não "loja física é mais barata". Mas para decisão
de etiqueta o efeito prático é o mesmo — e como etiqueta ≥ preço realizado, o
teto plausível da etiqueta física fica entre **0,91 e 1,00 × mediana web**, não
acima de 1,00.

### 1.2 Nossa posição atual

`Nosso preço de venda ÷ Brick`, 2.086 EANs:

| p25 | mediana | p75 | p95 |
|---:|---:|---:|---:|
| 1,099 | **1,212** | 1,387 | 2,465 |

Estamos ~21% acima do preço realizado da região na mediana, e um quarto do mix
está 39% ou mais acima. **Este é o achado mais acionável do estudo todo** e
sozinho justifica o sistema.

### 1.3 Sanidade do Brick

- Brick **acima** do PMC-PR: **0 EANs** — o dado é internamente coerente.
- Brick **abaixo do nosso custo**: **45 EANs** — fila de investigação de
  custo/embalagem, não de preço.

### 1.4 Flag fiscal disponível na NF

O relatório de entradas **não tem NCM**, mas tem `Valor do ICMS ST`, que é
flag empírico direto de substituição tributária:

| Grupo pai (taxonomia antiga) | linhas | % com ICMS-ST |
|---|---:|---:|
| GENÉRICO | 299 | 96,7% |
| SIMILAR | 192 | 91,7% |
| REFERÊNCIA | 89 | 87,6% |
| LIBERADO | 287 | 28,9% |
| PERFUMARIA | 958 | 20,7% |

Medicamento é ST quase sempre; perfumaria quase nunca. Isso bate com o escopo
de ST do Paraná e permite classificar sem depender de cadastro externo.

---

## Parte 2 — Tributação: o que a pesquisa concluiu

### 2.1 Regra

- **Anexo I (comércio), faixas 1ª a 5ª — partilha:** ICMS **34,00%**,
  COFINS **12,74%**, PIS/Pasep **2,76%**. → PIS+COFINS = **15,50%**.
- **Monofásico (Lei 10.147/2000):** indústria/importador recolhem PIS/COFINS
  por toda a cadeia; na **revenda a alíquota é zero**. Abrange medicamentos
  (posições 30.03/30.04) e perfumaria/higiene (NCM 3303–3307, 3401.11.90,
  3401.20.10, 9603.21.00). **Não** abrange fralda (9619), leite, bomboniere,
  bebida, acessórios.
- **ICMS-ST:** imposto já recolhido a montante; a receita correspondente sai da
  base de ICMS do DAS.
- A farmácia **deve segregar** essas receitas no PGDAS-D. A literatura do setor
  é enfática em que a não segregação é generalizada e gera pagamento a maior,
  recuperável em 5 anos.

### 2.2 Efeito numérico

Alíquota efetiva do DAS por natureza do item:

| Natureza | Parcela removida | Multiplicador |
|---|---:|---:|
| ST **e** monofásico (medicamento) | 34,00% + 15,50% = **49,50%** | **× 0,505** |
| Só monofásico (perfumaria/higiene sem ST) | 15,50% | × 0,845 |
| Nenhum (varejo, leite, fralda, bomboniere) | — | × 1,000 |

Os 5,98% do modelo atual correspondem à **faixa 3** com RBT12 de ~R$ 395 mil
— `(395.000 × 0,095 − 13.860) ÷ 395.000 = 5,99%`. Confere com o porte da
operação, então serve de base.

Piso resultante (`custo ÷ divisor`, mantendo cartão 2,50% e despesa fixa 17,50%):

| Natureza | Simples efetivo | Divisor do piso | Markup mínimo |
|---|---:|---:|---:|
| Medicamento (ST+mono) | 3,02% | **0,7698** | **29,9%** |
| Perfumaria/higiene (só mono) | 5,05% | **0,7495** | **33,4%** |
| Varejo comum | 5,98% | 0,7402 | 35,1% |

O piso de medicamento cai **3,8 pontos percentuais** de markup — exatamente na
categoria onde a competição é mais dura e onde o piso hoje bloqueia recomendação.

### 2.3 Como validar sem contador

O **extrato do PGDAS-D**, baixável por você mesmo no Portal do Simples
Nacional, mostra a alíquota efetiva e as receitas por segregação. Duas
leituras possíveis:

- **Se já há segregação:** os 5,98% são a média ponderada; use os
  multiplicadores acima sobre a alíquota *nominal* da faixa.
- **Se não há segregação:** você está pagando a mais hoje, e a correção vale
  mais do que qualquer ajuste de preço deste projeto.

Não sou contador; trate os números acima como modelo a conferir, não como
parecer. Mas a partilha do Anexo I e o regime monofásico são regra escrita,
não interpretação.

### 2.4 Reforma tributária

O relatório de NF já traz colunas `Valor IBS`, `Valor CBS`, `Valor IS`. 2026 é
ano-teste. A partir de 2027 a partilha muda. **Todas as alíquotas ficam em
arquivo de configuração versionado, nunca no código.**

---

## Parte 3 — Metodologia revisada

### 3.1 Referência de mercado com Brick

Brick vira **âncora**; a web forma a **dispersão**. Peso variável conforme a
qualidade da evidência web, em vez de fixo:

```
mercado_web   = mediana(precos_web_validos) × fator_fisico[categoria]
mercado_brick = VUM_brick × (1 + spread_etiqueta)      # spread inicial: 3%
R = w_b × mercado_brick + (1 - w_b) × mercado_web
```

| Situação da coleta web | `w_b` (peso do Brick) |
|---|---:|
| sem Brick | 0,00 |
| sem web (498 EANs hoje) | 1,00 |
| n_web ≤ 2 | 0,70 |
| n_web 3–4 | 0,45 |
| n_web ≥ 5 e CV ≤ 0,15 | **0,30** |
| n_web ≥ 5 e CV > 0,25 | 0,50 |

Isso entrega os 20–30% que você intuiu no caso em que a web é boa, e dá mais
peso ao Brick justamente quando a web é fraca — que é o comportamento correto.
E resolve os 498 EANs sem cobertura web nenhuma, que hoje caem em proteção de
margem por falta de dado.

**`fator_fisico` deixa de ser palpite.** Recalibrado por categoria a partir da
razão medida em 1.523 EANs (0,88–0,94 conforme segmento), com o valor antigo
1,00–1,10 aposentado.

**Brick como trava de validação:**

| Condição | Status |
|---|---|
| `\|mercado_web ÷ mercado_brick − 1\| > 0,25` | `DIVERGENCIA_BRICK_WEB` — não precifica automático |
| Brick < custo validado | `REVISAO_MANUAL_CUSTO_OU_EMBALAGEM` |
| Brick > PMC-PR | `REVISAO_MANUAL_TETO_CMED` |

A divergência Brick×web é o melhor detector automático de erro de apresentação
(caixa tratada como unidade, EAN trocado) que o sistema pode ter — muito melhor
que comparar descrições.

### 3.2 Exclusão de outliers — 4 camadas em ordem

Substitui o `1,5 × IQR`, que com n=4 não filtra praticamente nada.

**Camada 1 — natureza (a que mais importa).** Descartar preço de clube, app,
assinatura, leve-mais-pague-menos e promoção. Enquanto a Fase 0b não
estruturar o campo, heurística sobre `observacoes` (o São João já grava
`Promoção: ...`; 7.327 linhas do CSV contêm marcação).

**Camada 2 — frescor.** Descartar observação com mais de 45 dias. Sobrando
menos de 2, rebaixar confiança.

**Camada 3 — âncora (robusta a n pequeno).** Descartar preço fora de
`[0,60 ; 1,60] × âncora`, com âncora = Brick quando existir, senão mediana das
observações. **É esta camada que mata a promoção pontual:** um preço 40% abaixo
do realizado regional não é preço de mercado, é queima de estoque. Funciona com
n=2, ao contrário de qualquer teste estatístico.

**Camada 4 — MAD, só com n ≥ 5.** Descartar `|p − mediana| > 3 × MAD`, com
`MAD = 1,4826 × mediana(|p − mediana|)`. MAD tem ponto de ruptura de 50%:
resiste a metade dos pontos contaminados. O IQR com n=4 não resiste a nenhum.
Com n ≤ 4, pular.

**Regra preservada:** preço abaixo do custo **não** é outlier — não se descarta
para inflar a mediana. Dispara investigação. Agora com desempate: se o Brick
também está abaixo do custo, o problema é custo/embalagem; se só a web está,
é promoção do concorrente.

Toda exclusão é registrada com camada e motivo. Auditabilidade é o ponto
central da metodologia e não pode ser perdida aqui.

### 3.3 Demais correções (do diagnóstico anterior, mantidas)

1. Piso duplo: `max(custo ÷ divisor , custo + contribuição mínima em R$/un)`.
2. Custo de **reposição** (último) como principal, média como dispersão;
   `CUSTO_DEFASADO` se última compra > 90 dias.
3. Trava de variação por rodada (±15% sobre o preço praticado hoje).
4. Relatório dedicado "itens hoje abaixo do piso".
5. Estoque parado + Curva C ⇒ não aumentar preço.
6. `grid_price` passa a receber **teto** além do piso (bug atual: pode estourar
   o PMC no arredondamento).
7. Simulação de impacto agregado antes de aplicar qualquer rodada.

---

## Parte 4 — Implementação

Pacote `C:\Claude\Precificação\precificador\`, SQLite como base, separado do
app de coleta (o app é produtor de dados; misturar arrisca o coletor).

### Fase 0 — Parâmetros (0,5 dia)
`config/parametros.toml` versionado: alíquotas, partilha do Anexo I,
multiplicadores de segregação, cartão, despesa fixa, contribuição mínima,
spread de etiqueta, bandas de outlier, pesos `w_b`, trava de variação.
Nada de constante no código.

### Fase 1 — Ingestão (2 dias)
Carregadores idempotentes → SQLite:
`produto` · `custo_nf` (+ flag ST de `Valor do ICMS ST`) · `preco_concorrente`
· `preco_brick` (VUM, curva, posição, segmento) · `estoque` (+ **preço de venda
atual**) · `pmc_cmed_pr` · `politica_categoria`.
EAN normalizado como texto em toda parte. Cada carga registra origem e data.

### Fase 2 — Motor de mercado (2 dias, TDD)
`outliers.py` (4 camadas) · `brick.py` (peso, blend, travas) · `mercado.py`
(mediana, CV, n, confiança). Testes com casos reais extraídos do próprio CSV.

### Fase 3 — Motor econômico (2 dias, TDD)
`fiscal.py` (segregação → divisor por item) · `piso.py` (piso duplo) ·
`tier.py` · `alvo.py` · `travas.py` (CMED, variação, abaixo do custo) ·
`grade.py` (piso **e** teto). Funções puras, sem I/O — é onde mora o risco
financeiro, então é a parte que exige teste de verdade.

### Fase 4 — Rodada (1,5 dia)
Executa, grava `rodada` + `recomendacao`, faz diff com a rodada anterior
(preço, tier, status) e calcula impacto agregado em R$ ponderado por estoque.

### Fase 5 — Entregas (1,5 dia)
Excel de decisão no formato atual (Recomendados / Revisão / Medicamentos /
Resumo / Diff) + painel HTML com os cortes acionáveis: *abaixo do piso hoje*,
*Curva A acima do mercado*, *maior ganho de margem*, *divergência Brick×web*.

### Fase 0b — Promoção estruturada (paralelo, 1–2 dias)
Colunas `preco_regular` / `preco_promo` / `tipo_promo` no `precos.csv`, com
fallback para linhas antigas. Começar por São João (já extrai Teasers), depois
Pague Menos e Preço Popular. Subir `@version` e espelhar nas duas pastas de
userscript, conforme regra do repositório.

### Fase 6 — Calibração (30–60 dias depois)
`fator_fisico` e `spread_etiqueta` reajustados com observação local; alíquota
confirmada pelo extrato PGDAS-D; alvos por categoria revistos contra venda,
giro e ruptura reais.

**Ordem:** 0 → 1 → 2 → 3 → 4 → 5 gera valor com os dados já em disco.
0b corre em paralelo e melhora a qualidade das medianas quando ficar pronto.

---

## Parte 5 — Pendências de decisão

1. **Lista de EANs de marca própria** — pendência aberta desde o estudo de
   25/07; sem ela a exclusão é por suposição.
2. **Linhas 18 e 19 da taxonomia** (`GENERICO` duplicado, `SIMILAR` sem pai).
3. **Extrato PGDAS-D** — confirmar se já há segregação de receita.
4. **NCM no relatório de NF** — pedir a coluna ao ERP fecha a classificação
   monofásica de forma definitiva, em vez de inferir por categoria.

## Fontes

- [Anexo I — alíquotas e partilha do Simples Nacional (COAF)](https://www.coafdigital.com.br/tabelas_aliquotas_e_partilha_do_simples_nacional_6373.html)
- [Anexo I Simples Nacional — tabela de partilha (Contabilizei)](https://www.contabilizei.com.br/contabilidade-online/anexo-1-simples-nacional/)
- [Tributação de farmácias optantes pelo Simples Nacional (e-Simples Auditoria)](https://blog.esimplesauditoria.com.br/tributacao-de-farmacias-optantes-pelo-simples-nacional-voce-entende-bem/)
- [Regime monofásico PIS/COFINS — Lei 10.147/2000 (Portal Tributário)](https://www.portaltributario.com.br/tributario/regime-monofasico-pis-cofins.htm)
- [PIS e COFINS — medicamentos, higiene pessoal e cosméticos (Portal Tributário)](https://www.portaltributario.com.br/guia/pis_medicamentos.html)
- [Produtos monofásicos e ST: como excluir no Simples (Contábeis)](https://www.contabeis.com.br/noticias/74725/produtos-com-tributacao-monofasica-e-st-como-excluir-no-simples/)
- [Segregação de receitas no Simples Nacional (e-Auditoria)](https://www.e-auditoria.com.br/blog/segregacao-de-receitas-simples-nacional/)
