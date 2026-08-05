# Arquitetura do Precificador v2

Data: 04/08/2026  
Sistema: Motor de precificação econômico com sugestão de preço baseada em mercado regional + fiscal

## 1. Visão Geral

O **precificador** é um sistema Python que calcula preços sugeridos para uma farmácia drogista usando três fontes de dados:

1. **Brick** — preços praticados em farmácias físicas (VUM = Custo Real ÷ Unidades)
2. **Web** — preços coletados de concorrentes online
3. **Custo** — custo de aquisição via NF, com classificação fiscal (ST/Simples/Monofásico)

Usa dois **motores de cálculo**:
- **Mercado** — filtra outliers e calcula preço de referência (mediana Brick+Web)
- **Econômico** — calcula markup mínimo respeitando tributação, monta grid de ofertas

Resultado: uma **sugestão de preço** que respeita o mercado regional e cobrir custos + impostos.

---

## 2. Fluxo de Dados

```
Fontes → Ingest → SQLite → Mercado → Econômico → Excel/Exportação
```

### 2.1 Fontes Externas

| Arquivo | Origem | Conteúdo |
|---|---|---|
| `Relatório notas fiscais 24-07_com_custo_unitario.xlsx` | SAP/NFe | Custo unitário real, ICMS-ST flag, taxonomia NF |
| `estoque_pmc_brick.xlsx` | Brick API | VUM (preço médio praticado), segmentação |
| `ean_descricao_fabricante_pmc_pr.xlsx` | Brick API | Descrição canônica, PMC-PR (teto regulatório) |
| `precos.csv` | ConsultaPrecosEAN (web scraping) | Preços coletados de 8+ farmácias online, status OK/NAO_ENCONTRADO, data/hora, observações |
| `eans_negativos.csv` | App coleta | Marca própria (198 EANs) |
| `Pedro 2.xlsx` | Manual (Análise Categorias) | Subcategoria real de perfumaria (957 EANs) |
| `POLITICA_MARKUP_POR_CATEGORIA.csv` | Config | Markup mín/alvo/máx por grupo_pai (ex: SIMILAR, GENERICO, PERFUMARIA) |

### 2.2 SQLite — Schema

Tabelas (em `precificador.db`):

| Tabela | Função |
|---|---|
| `produto` | EAN → descricao, grupo taxonomia, marca_propria, subcategoria |
| `custo_nf` | EAN → quantidade, custo_unitario, valor_total, tem_icms_st (flag fiscal) |
| `brick_vum` | EAN → preco_mercado_brick, segmento_brick |
| `pmc_pr` | EAN → pmc_pr (teto regulatório Paraná) |
| `observacao_preco_web` | site, ean, preco, status, data_hora, observacoes (de precos.csv) |
| `markup_politica` | grupo_pai → markup_min, markup_alvo, markup_max |
| `resultado_preco` | EAN → preco_sugerido, peso_mercado, confianç fiscal, histórico |
| `carga_log` | data_hora → fonte, num_linhas, status (auditoria de cargas) |

---

## 3. Componentes Principais

### 3.1 `ingest.py` — Carregamento Idempotente

**Responsabilidade:** Ler fontes externas, normalizar, carregar SQLite idempotentemente (recarregar uma fonte apaga/recria sua tabela).

**Funções principais:**
- `carregar_custos_nf()` — Ler NF xlsx → tabela `custo_nf`
- `carregar_brick_vum()` — Ler Brick xlsx → tabela `brick_vum`
- `carregar_pmc_pr()` — Ler PMC-PR xlsx → tabela `pmc_pr`
- `carregar_precos_web()` — Ler precos.csv → tabela `observacao_preco_web`
- `carregar_eans_negativos()` — Ler eans_negativos.csv → marca `marca_propria=1`
- `carregar_politica_markup()` — Ler política csv → tabela `markup_politica`
- `main()` — Executar todas em ordem, registrar `carga_log`

**Nota:** Todas as funções são idempotentes (seguro chamar novamente com novos dados).

### 3.2 `engine/mercado.py` — Motor de Mercado

**Responsabilidade:** Filtrar outliers, calcular mediana web, blender Brick/Web.

**Lógica de Filtro (4 camadas):**

1. **Natureza** — Remove preços sem status=OK, preço nulo, status=NAO_ENCONTRADO, promoções com "clube/leve/assinante"
2. **Frescor** — Remove observações com >30 dias (configurável em `parametros.toml`)
3. **Distância** — Remove preços >3σ da mediana (outliers estatísticos)
4. **Concordância** — Avalia divergência Brick vs Web:
   - Se Brick existe: calcula razão Brick÷mediana_web
   - Se razão anômala (ex: 2.5x): marca `divergencia_brick_web=True`, reduz confiança

**Saída (`ResultadoMercado`):**
- `mediana`: Mediana dos preços filtrados (web)
- `n`: Quantidade de observações mantidas
- `cv`: Coeficiente de variação (dispersão)
- `confianca`: "ALTA" / "MEDIA" / "BAIXA" (em função de n e cv)
- `peso_brick`: Fator [0.0-1.0] — peso dado a Brick na blendagem
- `valor_referencia`: Blend ponderado Brick + Web
- `divergencia_brick_web`: Flag se há conflito Brick vs Web

**Regra de Blendagem:**
```
se Brick existe:
  peso_brick = min(0.5, max(0.1, confiança_web))
  valor_referencia = Brick × peso_brick + Web × (1 - peso_brick)
senao:
  valor_referencia = Web
```

---

### 3.3 `engine/economico.py` — Motor Econômico

**Responsabilidade:** Calcular preço mínimo (custo + impostos), montar grid de ofertas (alvo, travas, tier).

**Fluxo por EAN:**

1. **Classificação Fiscal**
   - Se `tem_icms_st=1`: Substituição Tributária (medicamento típico)
   - Se `marcapropria=1`: Segmentação automática
   - Padrão: Simples Nacional

2. **Cálculo Base**
   ```
   custo = custo_nf ÷ quantidade (unitário da NF)
   aliquota_pis_cofins = 15.50% (Simples ou partilha ICMS-ST)
   aliquota_icms_propria = 0% (ST) ou 18% (Simples próprio)
   
   custo_fiscal = custo × (1 + aliquota_pis_cofins + aliquota_icms_propria)
   ```

3. **Markup Mínimo (Piso)**
   ```
   markup_min_politica = POLITICA_MARKUP[grupo_pai].markup_min
   preco_minimo = custo_fiscal × (1 + markup_min_politica)
   ```

4. **Travas Regulatórias**
   - `pmc_pr`: Teto legal (PMC-PR Anvisa)
   - `brick_alerta`: Se sugestão > Brick + 25%, marca possível desvio

5. **Grid de Ofertas**
   ```
   if confiança_mercado == "ALTA" e n >= 3:
     preco_alvo = referencia_mercado
   else:
     preco_alvo = custo_fiscal × (1 + markup_alvo)
   
   preco_final = max(preco_minimo, preco_alvo)
   preco_final = min(preco_final, pmc_pr)
   ```

**Saída (`ResultadoEconomico`):**
- `preco_minimo`: Piso (custo + impostos + markup mín)
- `preco_alvo`: Alvo de mercado (blend ou markup alvo)
- `preco_sugerido`: Final (respeita piso e teto)
- `markup_realizado`: % calculado
- `confianca_fiscal`: "OK" / "DUPLA_ALIQUOTA" / "ALERTA"

---

### 3.4 `rodada_v2.py` — Orquestrador

**Responsabilidade:** Carregar dados, chamar motores para cada EAN, exportar resultado.

**Fluxo:**
1. Ingerir todas as fontes (`ingest.main()`)
2. Para cada EAN com custo_nf:
   - Buscar mercado (Brick + Web) → `ResultadoMercado`
   - Chamar motor econômico → `ResultadoEconomico`
   - Inserir em `resultado_preco`
3. Exportar para Excel (`exportar_excel.py`)

---

## 4. Uso

### 4.1 Importar e Usar Programaticamente

```python
from precificador import rodada_v2

# Carregar dados e executar precificação completa
resultado_ean = rodada_v2.precificar_ean(
    ean="7891234567890",
    parametros=parametros.carregar(),
)

print(f"Preço sugerido: R$ {resultado_ean.preco_sugerido:.2f}")
print(f"Confiança: {resultado_ean.confianca_fiscal}")
```

### 4.2 Via Linha de Comando

```bash
cd Precificação/precificador
python rodada_v2.py
```

Resultado: `ESTOQUE_DROGARIA_PRECIFICADO.xlsx` com todos os EANs e sugestões.

---

## 5. Configuração

Arquivo: `config/parametros.toml`

```toml
[mercado]
dias_max_frescor = 30
sigma_outlier = 3.0
peso_brick_min = 0.1
peso_brick_max = 0.5

[economico]
aliquota_pis_cofins_padrao = 0.1550
aliquota_icms_simples = 0.18
aliquota_icms_st = 0.00
markup_alvo_padrao = 0.35

[travas]
margem_alerta_brick = 0.25
```

---

## 6. Testes

**Cobertura:** 36 testes (pytest)  
**Rodada:** `pytest precificador/tests/`

Testes cobrem:
- Filtro de outliers (4 camadas)
- Cálculo de blend Brick/Web
- Markup econômico por tributação
- Casos fronteira (poucos sites, promoção, marcas próprias)
- Sanidade contra banco real (727 EANs)

---

## 7. Limitações e Próximos Passos

### Conhecidas
- Brick só tem cobertura para NMED/GEN/RX (~90% SKU); perfumaria depende 100% web
- Web tem gaps (295 EANs só em Brick, 498 sem coleta)
- Subcategoria perfumaria ainda manual (957 reclassificados, 203 por nome)

### Planejado
- ML de classificação automática (subcategoria/marca a partir de descrição)
- Integração de histórico de vendas (elasticidade por tier)
- Dashboard de auditoria (por quê cada EAN tem esse preço?)
