# Dicionário de Dados — Precificador v2

Referência completa de campos, tabelas, tipos e significados.

---

## 1. Tabelas SQLite

### 1.1 `produto`

Registro de produto por EAN (chave primária).

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `ean` | TEXT | ✗ | Código EAN-13 (PK). Normalizado (apenas dígitos). |
| `descricao` | TEXT | ✓ | Nome do produto (ex: "Dipirona 500mg Genérico C/20") |
| `grupo_pai_nf` | TEXT | ✓ | Grupo da taxonomia NF (ex: "GENERICO", "SIMILAR", "REFERÊNCIA", "LIBERADO", "PERFUMARIA") |
| `grupo_filho_nf` | TEXT | ✓ | Subgrupo da NF (ex: "ANTI-INFLAMATÓRIO") |
| `marca_propria` | INTEGER | ✓ | Flag 0/1 — é marca exclusiva dos Associados (de `eans_negativos.csv`) |
| `subcategoria_real` | TEXT | ✓ | Subcategoria classificada manualmente (ex: "MAQUIAGEM", "HIGIENE", "PROTETOR_SOLAR") — só para perfumaria |

**Índices:**
- PK: `ean`

**Exemplo:**
```
ean=7891234567890
descricao=Dipirona 500mg Genérico C/20
grupo_pai_nf=GENERICO
marca_propria=0
```

---

### 1.2 `custo_nf`

Linhas de nota fiscal de entrada com custo realizado e flag fiscal.

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | ✗ | ID sequencial (auditoria) |
| `ean` | TEXT | ✗ | FK → `produto.ean` |
| `quantidade` | FLOAT | ✗ | Quantidade recebida (unidades) |
| `custo_unitario` | FLOAT | ✗ | Custo por unidade (R$). Calculado: valor_total ÷ quantidade |
| `valor_total` | FLOAT | ✗ | Valor total da linha (R$) |
| `tem_icms_st` | INTEGER | ✗ | Flag 0/1 — linha com ICMS-ST (Substituição Tributária) |

**Índices:**
- PK: `id`
- FK: `ean` → `produto.ean`

**Exemplo:**
```
ean=7891234567890
quantidade=100
custo_unitario=4.32
valor_total=432.00
tem_icms_st=1  -- Medicamento: quase sempre ST
```

---

### 1.3 `brick_vum`

Preço de mercado realizado via Brick (preço médio praticado em farmácias físicas).

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `ean` | TEXT | ✗ | FK → `produto.ean` (PK) |
| `preco_mercado_brick` | FLOAT | ✓ | VUM (Valor Unitário Médio) em R$. Preço realizado na região. |
| `segmento_brick` | TEXT | ✓ | Segmentação Brick (ex: "NMED", "GEN", "RX", "SIM") |
| `data_brick` | TEXT | ✓ | Data do dado Brick (YYYY-MM-DD) |

**Índices:**
- PK: `ean`
- FK: `ean` → `produto.ean`

**Exemplo:**
```
ean=7891234567890
preco_mercado_brick=8.50
segmento_brick=GEN
data_brick=2026-08-01
```

**Nota:** Preço Brick é ~9% abaixo da mediana web (regional realiza menos caro que anúncio web).

---

### 1.4 `pmc_pr`

Preço Máximo ao Consumidor (teto regulatório Anvisa) para o Paraná.

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `ean` | TEXT | ✗ | FK → `produto.ean` (PK) |
| `pmc_pr` | FLOAT | ✓ | PMC-PR em R$ (teto legal). Nunca vender acima disto. |
| `descricao_pmc` | TEXT | ✓ | Descrição canônica do fabricante |

**Índices:**
- PK: `ean`

**Exemplo:**
```
ean=7891234567890
pmc_pr=15.00
descricao_pmc=Dipirona 500mg Genérico
```

---

### 1.5 `observacao_preco_web`

Observações de preços coletadas via scraping (8+ farmácias online).

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | ✗ | ID sequencial |
| `ean` | TEXT | ✗ | FK → `produto.ean` |
| `site` | TEXT | ✗ | Farmácia (ex: "DROGARAIA", "NISSEI", "PANVEL", ...) |
| `preco` | FLOAT | ✓ | Preço coletado em R$ (NULL se não encontrado) |
| `status` | TEXT | ✗ | "OK" / "NAO_ENCONTRADO" / "DESCONTINUADO" |
| `data_hora` | TEXT | ✓ | Data/hora da coleta (DD/MM/YYYY HH:MM:SS). Usado para calcular "frescor". |
| `observacoes` | TEXT | ✓ | Texto livre (ex: "Promoção: leve 2 pague 1", "Assinante") |

**Índices:**
- PK: `id`
- FK: `ean` → `produto.ean`
- INDEX: `(ean, status)` — filtro comum

**Exemplo:**
```
ean=7891234567890
site=DROGARAIA
preco=9.20
status=OK
data_hora=04/08/2026 14:32:15
observacoes=Promoção: de R$ 11 por R$ 9,20
```

---

### 1.6 `markup_politica`

Política de markup por categoria (via csv de negócio).

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `grupo_pai` | TEXT | ✗ | Categoria (ex: "GENERICO", "SIMILAR", "REFERENCIA", "LIBERADO", "PERFUMARIA") (PK) |
| `markup_min` | FLOAT | ✗ | Markup mínimo (ex: 0.30 = 30%) — piso que nunca deve ser ultrapassado |
| `markup_alvo` | FLOAT | ✗ | Markup alvo (ex: 0.45 = 45%) — usado se confiança de mercado for baixa |
| `markup_max` | FLOAT | ✗ | Markup máximo (ex: 0.70 = 70%) — teto não obrigatório, mas indica risco de precificação alta |

**Índices:**
- PK: `grupo_pai`

**Exemplo:**
```
grupo_pai=GENERICO
markup_min=0.30
markup_alvo=0.40
markup_max=0.60

grupo_pai=PERFUMARIA
markup_min=0.35
markup_alvo=0.50
markup_max=0.75
```

---

### 1.7 `resultado_preco`

Saída da precificação — um registro por EAN com preço sugerido final.

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `ean` | TEXT | ✗ | FK → `produto.ean` (PK) |
| `preco_sugerido` | FLOAT | ✗ | Preço final recomendado (R$). Respeita piso (custo+impostos) e teto (PMC-PR). |
| `custo_unitario` | FLOAT | ✓ | Custo unitário da NF (R$) |
| `custo_fiscal` | FLOAT | ✓ | Custo + impostos (PIS/COFINS + ICMS próprio se aplicável) |
| `preco_minimo` | FLOAT | ✓ | Piso obrigatório (custo_fiscal × (1 + markup_min)) |
| `preco_alvo` | FLOAT | ✓ | Preço de mercado ou markup alvo |
| `markup_realizado` | FLOAT | ✓ | Markup final (%) = (preco_sugerido - custo_unitario) ÷ custo_unitario |
| `mediana_web` | FLOAT | ✓ | Mediana dos preços web filtrados (R$) |
| `n_observacoes_web` | INTEGER | ✓ | Quantidade de observações web usadas |
| `confianca_web` | TEXT | ✓ | "ALTA" / "MEDIA" / "BAIXA" — baseada em n e dispersão |
| `preco_brick` | FLOAT | ✓ | VUM Brick (R$) |
| `peso_brick` | FLOAT | ✓ | Peso dado a Brick na blendagem [0.0-1.0] |
| `valor_referencia` | FLOAT | ✓ | Blend ponderado (Brick × peso + Web × (1-peso)) |
| `divergencia_brick_web` | INTEGER | ✓ | Flag 0/1 — há conflito entre Brick e Web? |
| `tem_icms_st` | INTEGER | ✓ | Flag 0/1 — produto é ST (Substituição Tributária) |
| `pmc_pr` | FLOAT | ✓ | PMC-PR limite (R$) |
| `confianca_fiscal` | TEXT | ✓ | "OK" / "DUPLA_ALIQUOTA" / "ALERTA" |
| `data_rodada` | TEXT | ✗ | Data de execução (YYYY-MM-DD HH:MM:SS) |

**Índices:**
- PK: `ean`

**Exemplo:**
```
ean=7891234567890
preco_sugerido=9.80
custo_unitario=4.32
custo_fiscal=4.99 (4.32 × 1.155)
preco_minimo=6.49 (4.99 × 1.30)
preco_alvo=9.80
markup_realizado=1.27 (127%)
mediana_web=9.20
n_observacoes_web=5
confianca_web=ALTA
preco_brick=8.50
peso_brick=0.15
valor_referencia=9.28
divergencia_brick_web=0
tem_icms_st=1
pmc_pr=15.00
confianca_fiscal=OK
data_rodada=2026-08-04 15:30:22
```

---

### 1.8 `carga_log`

Auditoria de carregamentos (quais fontes foram carregadas, quando, com sucesso?).

| Campo | Tipo | Nulo? | Descrição |
|---|---|---|---|
| `id` | INTEGER | ✗ | ID sequencial |
| `fonte` | TEXT | ✗ | Nome da fonte (ex: "custo_nf", "brick_vum", "precos_web", ...) |
| `num_linhas` | INTEGER | ✗ | Quantidade de registros carregados |
| `data_hora` | TEXT | ✗ | Timestamp de execução (YYYY-MM-DD HH:MM:SS) |
| `status` | TEXT | ✗ | "OK" / "ERRO" |
| `mensagem` | TEXT | ✓ | Detalhes se erro (ex: "File not found: ...") |

**Índices:**
- PK: `id`
- INDEX: `(fonte, data_hora)`

**Exemplo:**
```
fonte=custo_nf
num_linhas=1247
data_hora=2026-08-04 15:10:00
status=OK
```

---

## 2. Estruturas de Dados (Python Dataclasses)

### 2.1 `mercado.Observacao`

Uma observação de preço web.

```python
@dataclass(frozen=True)
class Observacao:
    site: str                # "DROGARAIA", "NISSEI", ...
    preco: float | None      # R$, NULL se NAO_ENCONTRADO
    status: str              # "OK" ou "NAO_ENCONTRADO"
    data_hora: date | None   # Data da coleta
    observacoes: str | None  # Texto (ex: "Promoção", "Assinante")
```

### 2.2 `mercado.ResultadoMercado`

Saída do motor de mercado (filtro + blend).

```python
@dataclass(frozen=True)
class ResultadoMercado:
    mediana: float | None              # Mediana web filtrada
    n: int                             # Num observações mantidas
    cv: float | None                   # Coeficiente variação
    confianca: str                     # "ALTA", "MEDIA", "BAIXA"
    peso_brick: float                  # [0.0-1.0]
    valor_referencia: float | None     # Blend Brick + Web
    divergencia_brick_web: bool        # Conflito detectado?
    filtro: ResultadoFiltro            # Detalhes de descartes
```

### 2.3 `economico.ResultadoEconomico`

Saída do motor econômico (precificação).

```python
@dataclass(frozen=True)
class ResultadoEconomico:
    ean: str
    preco_sugerido: float
    custo_unitario: float
    custo_fiscal: float
    preco_minimo: float
    preco_alvo: float
    markup_realizado: float
    confianca_fiscal: str  # "OK", "DUPLA_ALIQUOTA", "ALERTA"
    divergencia_brick_web: bool
```

---

## 3. Arquivos Externos (Entrada)

### 3.1 `Relatório notas fiscais 24-07_com_custo_unitario.xlsx`

Planilha de entradas com custo unitário calculado.

| Coluna | Header | Significado |
|---|---|---|
| 10 | Coluna J | EAN (normalizar) |
| 11 | Coluna K | Descrição |
| 14 | Coluna N | Quantidade |
| 26 | Coluna Z | Custo Unitário |
| 27 | Coluna AA | Valor Total |
| 19 | Coluna S | Valor ICMS-ST (flag fiscal) |
| 28 | Coluna AB | Grupo Pai (Taxonomia) |
| 29 | Coluna AC | Grupo Filho |

**Nota:** Começa na linha 5 (headers linha 1-4).

### 3.2 `estoque_pmc_brick.xlsx`

Preços Brick (VUM) — consolidado.

| Coluna | Significado |
|---|---|
| A | EAN |
| B | Descrição |
| C | VUM (Valor Unitário Médio) |
| D | Segmento (NMED, GEN, RX, SIM, ...) |

### 3.3 `ean_descricao_fabricante_pmc_pr.xlsx`

PMC-PR (teto regulatório).

| Coluna | Significado |
|---|---|
| A | EAN |
| B | Descrição |
| C | PMC-PR (R$) |

### 3.4 `precos.csv`

Web scraping — observações de preço.

```csv
ean,site,preco,status,data_hora,observacoes
7891234567890,DROGARAIA,9.20,OK,04/08/2026 14:32:15,"Promoção: de R$ 11 por R$ 9,20"
7891234567890,NISSEI,10.50,OK,04/08/2026 15:00:00,
```

### 3.5 `eans_negativos.csv`

Marca própria Associados.

```csv
ean,descricao
7891234567891,Genérico Marca Própria
...
```

### 3.6 `POLITICA_MARKUP_POR_CATEGORIA.csv`

Política de markup por grupo.

```csv
grupo_pai,markup_min,markup_alvo,markup_max
GENERICO,0.30,0.40,0.60
SIMILAR,0.30,0.45,0.65
REFERENCIA,0.25,0.35,0.55
LIBERADO,0.35,0.50,0.75
PERFUMARIA,0.35,0.50,0.75
```

---

## 4. Arquivos de Saída

### 4.1 `ESTOQUE_DROGARIA_PRECIFICADO.xlsx`

Excel com recomendações finais — um EAN por linha.

| Coluna | Significado |
|---|---|
| A | EAN |
| B | Descrição |
| C | Grupo Pai (NF) |
| D | Brick |
| E | Mediana Web |
| F | Custo Unit |
| G | Preco Sugerido |
| H | Markup % |
| I | Confiança |
| J | PMC-PR |
| K | Peso Brick |
| L | N Observações Web |
| M | Data Coleta |

---

## 5. Glossário

| Termo | Significado |
|---|---|
| **VUM** | Valor Unitário Médio (preço realizado no Brick) |
| **ST** | Substituição Tributária (regime fiscal medicamentos) |
| **PMC-PR** | Preço Máximo Consumidor — Paraná (teto Anvisa) |
| **Markup** | (Preço - Custo) ÷ Custo (margem em %) |
| **CV** | Coeficiente de Variação (dispersão / média) |
| **σ** | Sigma (desvio padrão) — usado para outliers >3σ |
| **Blend** | Ponderação entre Brick + Web |
| **Frescor** | Limite de dias para observação ser considerada "atual" |
| **Outlier** | Preço muito distante da mediana (descartado) |
| **Confiança** | Qualidade da observação de preço (ALTA/MEDIA/BAIXA) |

---

## 6. Validações Típicas

### Query: Quantos EANs têm custo?
```sql
SELECT COUNT(DISTINCT ean) FROM custo_nf;
```

### Query: EANs sem preço de mercado?
```sql
SELECT COUNT(*) FROM custo_nf
WHERE ean NOT IN (
  SELECT DISTINCT ean FROM brick_vum WHERE preco_mercado_brick IS NOT NULL
  UNION
  SELECT DISTINCT ean FROM observacao_preco_web WHERE status = 'OK'
);
```

### Query: Markup realizado por grupo?
```sql
SELECT 
  p.grupo_pai_nf,
  AVG(r.markup_realizado) as markup_medio,
  MIN(r.markup_realizado) as markup_min,
  MAX(r.markup_realizado) as markup_max
FROM resultado_preco r
JOIN produto p ON r.ean = p.ean
GROUP BY p.grupo_pai_nf
ORDER BY markup_medio DESC;
```
