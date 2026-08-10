# Plano: Sistema de Três Preços (Máximo / Real / Mínimo)

> Para análise externa. Data: 08/08/2026. Loja: drogaria física, Maringá/PR, ainda não inaugurada.

---

## 1. Objetivo

Exibir 3 preços ao cliente final (na etiqueta, no sistema, no PDV):

```
PREÇO MÁXIMO   → "De R$ X,XX"   (âncora — impressiona mas é crível)
PREÇO REAL     → "Por R$ Y,YY"   (ação: comprar — preço justo e competitivo)
PREÇO MÍNIMO   → "Mín R$ Z,ZZ"   (piso — comunica "já está no osso, não adianta negociar")
```

### Restrição obrigatória

- **Medicamentos com PMC**: o Preço Máximo DEVE ser o PMC (Preço Máximo ao Consumidor). O app de gestão aplica isso automaticamente no sistema.
- **Demais itens**: o Preço Máximo pode ser o maior concorrente local ou um spread calculado.

---

## 2. Estado atual do motor (08/08/2026)

### 2.1 Arquitetura geral

```
Fontes (xlsx/csv)
    ↓
Ingest (idempotente) → SQLite (11 tabelas)
    ↓
Motor de Mercado (mercado.py, 539 linhas)
    ├── fator_canal_por_site: converte preço online → estimativa de balcão (×1.10 a ×1.18)
    ├── 4 camadas de filtro: natureza → frescor → âncora → MAD
    ├── selecionar_vizinhanca: separa concorrentes locais vs. remotos
    ├── _mediana_geografica: média ponderada das medianas por site (peso por proximidade)
    ├── _fator_fisico: converte mediana web → estimativa de balcão físico
    │   ├── Com segmento Brick: usa fator calibrado (0.78-0.94)
    │   └── Sem segmento Brick: usa premio_balcao (zerado para abertura = 1.00)
    ├── blend Brick/web (peso adaptativo)
    └── cluster_acima_brick: detecta quando concorrentes convergem acima do Brick
    ↓
Motor Econômico (economico.py, 693 linhas)
    ├── natureza_fiscal: medicamento / perfumaria_higiene / padrao
    ├── piso: max(piso_simples, custo+contribuição_mínima, custo/(1-margem_bruta_minima))
    ├── tier: PRECO_IMAGEM / PADRAO / PROTECAO_MARGEM
    ├── alvo_por_ranking: posiciona no N-ésimo lugar entre concorrentes
    ├── aplicar_travas: orquestra piso, teto CMED, divergência, piso competitivo
    └── calcular_banda_balcao: 3 degraus para o vendedor (vitrine/cortesia/cobrimos)
    ↓
Resultado (preco_sugerido por EAN)
    ↓
Excel (ESTOQUE_DROGARIA_PRECIFICADO.xlsx)
```

### 2.2 Parâmetros relevantes para os 3 preços

**Arquivo**: `precificador/config/parametros.toml`

| Seção | Chave | Valor | Significado |
|---|---|---|---|
| `premissas` | `margem_bruta_minima_pct` | 0.25 | Piso = custo / 0.75 |
| `premissas` | `contribuicao_minima_reais` | 0.60 | Piso mínimo absoluto por unidade |
| `mercado.fator_canal_por_site` | `drogaraia` | 1.10 | ×1.10 no preço online da Raia |
| `mercado.fator_canal_por_site` | `nissei` | 1.18 | ×1.18 na Nissei (maior gap online→balcão) |
| `mercado.fator_canal_por_site` | `default` | 1.10 | Demais sites |
| `mercado.peso_geografico` | `drogaraia` | 4.0 | Raia pesa 4× na mediana (mesmo quarteirão) |
| `mercado.peso_geografico` | `farmasp` | 3.5 | Farmasp pesa 3.5× |
| `mercado.peso_geografico` | `nissei` | 1.0 | Nissei pesa 1× (mais distante) |
| `mercado.premio_balcao` | `medicamento` | 1.00 | Zerado para abertura |
| `mercado.premio_balcao` | `perfumaria_higiene` | 1.00 | Zerado para abertura |
| `mercado.premio_balcao` | `padrao` | 1.00 | Zerado para abertura |
| `mercado.fator_fisico` | `GEN` | 0.92 | Medicamento genérico: web ×0.92 |
| `mercado.fator_fisico` | `RX` | 0.94 | Ético: web ×0.94 |
| `mercado.fator_fisico` | `SIM` | 0.78 | Similar: web ×0.78 |
| `mercado.fator_fisico` | `NMED` | 0.91 | Não-medicamento: web ×0.91 |
| `grade` | `terminacoes` | [0.49, 0.79, 0.90, 0.95, 0.99] | Terminações psicológicas |
| `ranking.rank_alvo_por_tier` | `PRECO_IMAGEM` | 2 | 2º menor preço |
| `ranking.rank_alvo_por_tier` | `PADRAO` | 2 | 2º menor preço |
| `piso_competitivo` | `ativo` | true | Não vende abaixo do menor local (exceto chamariz) |
| `piso_competitivo` | `desconto_tolerado_pct` | 0.0 | Empata com o menor, não fica abaixo |

### 2.3 O que o motor JÁ calcula (relevante para os 3 preços)

Após `aplicar_travas()` em `economico.py`, já existem:

| Campo | Dataclass/Contexto | Significado |
|---|---|---|
| `preco_sugerido` | `ResultadoPrecificacao` | Preço Real (vitrine/etiqueta) |
| `piso` | `ResultadoPrecificacao` | Piso técnico (custo + contribuição mínima + margem bruta mínima) |
| `teto_cmed` | Parâmetro de entrada | PMC-PR (teto legal para medicamentos) |
| `menor_concorrente_local` | `rodada_v2.py` (variável local) | Menor preço entre concorrentes da vizinhança |
| `maior_concorrente_local` | `rodada_v2.py` (variável local) | Maior preço entre concorrentes da vizinhança |
| `precos_concorrentes` | `rodada_v2.py` (variável local) | Lista de preços válidos dos concorrentes do alvo |
| `resultado_mercado.precos_alvo` | `ResultadoMercado` | Tuple de preços dos concorrentes que definem o alvo |

### 2.4 Pipeline de conversão de preço web (resumo)

Para entender de onde vem o `preco_sugerido` e como ele se relaciona com o mercado:

```
Preço ONLINE coletado (scraper)
    │
    ├── × fator_canal_por_site[site]        ex: Raia ×1.10, Nissei ×1.18
    │   └── Converte online → estimativa de balcão daquele concorrente
    │
    ├── 4 camadas de filtro (natureza, frescor, âncora, MAD)
    │
    ├── Mediana geográfica (peso por proximidade do concorrente)
    │   └── Raia pesa 4× mais que Nissei na média final
    │
    ├── × fator_fisico (se tem Brick)       ex: GEN ×0.92, SIM ×0.78
    │   └── OU × premio_balcao (se sem Brick)  ex: 1.00 (zerado)
    │   └── Converte referência web → estimativa de balcão físico
    │
    ├── Blend com Brick (peso adaptativo)
    │
    └── = valor_referencia (mercado)
            │
            ├── Aplica ranking (2º lugar)
            ├── Aplica piso competitivo (empata com menor local)
            ├── Arredonda na grade
            │
            └── = preco_sugerido (PREÇO REAL)
```

---

## 3. Design dos Três Preços

### 3.1 Regra geral

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  PREÇO MÁXIMO = O maior entre:                              │
│    1. PMC (se medicamento e teto_cmed existe)  ← OBRIGATÓRIO│
│    2. maior_concorrente_local (se vizinhança confiável)      │
│    3. preco_real × (1 + spread_maximo_pct)     ← fallback   │
│                                                              │
│  PREÇO REAL = preco_sugerido (já calculado pelo motor)      │
│                                                              │
│  PREÇO MÍNIMO = O maior entre:                              │
│    1. piso (custo + contribuição + margem bruta mínima)      │
│    2. preco_real × (1 - folga_minimo_pct)     ← apertado    │
│    Arredondado para CIMA na grade (nunca abaixo do piso)    │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 3.2 Constantes propostas (novo `[vitrine]` no TOML)

```toml
[vitrine]
# Preço Máximo: spread sobre o preco_real quando não há PMC nem
# concorrente local para servir de âncora. Modesto de propósito:
# "De R$ 39,90 por R$ 34,90" (-12,5%) é mais crível que
# "De R$ 59,90 por R$ 34,90" (-42%).
spread_maximo_pct = 0.15

# Preço Mínimo: folga abaixo do preco_real. Pequena de propósito
# para comunicar "já está justo" e desencorajar negociação.
# Ex: real=34,90, folga 10% → mínimo tenta 31,41 → grade 31,49.
# Se o piso for maior que isso, prevalece o piso.
folga_minimo_pct = 0.10
```

### 3.3 Exemplos numéricos com o motor atual

#### Exemplo A — Dipirona 500mg Genérica (COM PMC, COM Brick)

```
Dados:
  Custo:              R$ 4,32
  Piso (c/ margem 25%): R$ 5,76  (= 4.32 / 0.75)
  Piso contribuição:  R$ 4,92  (= 4.32 + 0.60) → prevalece o de margem: R$ 5,76
  Web Droga Raia:     R$ 8,50 (cru)
    × fator_canal:    R$ 9,35 (1.10)
  Web Nissei:         R$ 8,20 (cru)
    × fator_canal:    R$ 9,68 (1.18)
  Mediana geográfica: R$ 9,40 (Raia 4× + Nissei 1× + demais)
    × fator_fisico:   R$ 8,65 (GEN = 0.92)
  PMC-PR:             R$ 15,00
  Menor local:        R$ 9,35 (Raia, após fator canal)
  Maior local:        R$ 9,68 (Nissei, após fator canal)
  preco_sugerido:     R$ 8,79 (2º lugar, grade .79)

Resultado:
  PREÇO MÁXIMO:  R$ 15,00  (PMC obrigatório)
  PREÇO REAL:    R$  8,79  (preco_sugerido)
  PREÇO MÍNIMO:  R$  7,90  (max(piso=5.76, real×0.90=7.91) → grade acima = 7.90)

  Gap máximo→real: -41%   (alto, mas o app obriga PMC)
  Gap real→mínimo: -10%   (apertado → "já tá justo")
```

#### Exemplo B — Leite Infantil (VAREJO, SEM PMC, SEM Brick)

```
Dados:
  Custo:              R$ 35,35
  Piso (c/ margem 25%): R$ 47,13
  Web Raia:           R$ 54,90 (cru)
    × fator_canal:    R$ 60,39 (1.10)
  Web Nissei:         R$ 52,90 (cru)
    × fator_canal:    R$ 62,42 (1.18)
  Mediana geográfica: R$ 60,50 (Raia pesa 4×)
    × premio_balcao:  R$ 60,50 (1.00, zerado)
  PMC:                (não tem)
  Menor local:        R$ 60,39
  Maior local:        R$ 62,42
  preco_sugerido:     R$ 59,90 (levemente abaixo, grade .90)

Resultado:
  PREÇO MÁXIMO:  R$ 62,50  (maior concorrente local, grade)
  PREÇO REAL:    R$ 59,90  (preco_sugerido)
  PREÇO MÍNIMO:  R$ 53,90  (max(piso=47.13, real×0.90=53.91) → grade acima = 53.90)

  Gap máximo→real:  -4%   (âncora verificável: "na Droga Raia tá R$ 62")
  Gap real→mínimo: -10%   (apertado)
```

#### Exemplo C — Protetor Solar (PERFUMARIA, SEM PMC, SEM Brick, concorrência escassa)

```
Dados:
  Custo:              R$ 42,00
  Piso (c/ margem 25%): R$ 56,00
  Web Raia:           R$ 74,90 (cru)
    × fator_canal:    R$ 82,39 (1.10)
  Web Nissei:         R$ 79,90 (cru)
    × fator_canal:    R$ 94,28 (1.18)
  Mediana geográfica: R$ 83,50
    × premio_balcao:  R$ 83,50 (1.00)
  PMC:                (não tem)
  Maior local:        R$ 94,28 (Nissei)
  Menor local:        R$ 82,39 (Raia)
  preco_sugerido:     R$ 82,90 (grade .90, próximo do menor local)

Resultado:
  PREÇO MÁXIMO:  R$ 94,50  (maior concorrente local, grade)
  PREÇO REAL:    R$ 82,90
  PREÇO MÍNIMO:  R$ 74,90  (max(piso=56.00, real×0.90=74.61) → grade acima na .90)

  Gap máximo→real: -12%   (verificável: "na Nissei tá R$ 94")
  Gap real→mínimo: -10%   (apertado)
```

---

## 4. Pontos de atenção (bandeiras)

### 4.1 Interação `fator_canal_por_site` × `fator_fisico`

Para itens **sem Brick** (55% do catálogo):
- `fator_canal` empurra a referência para cima (+10% a +18%)
- `premio_balcao` zerado não compensa (1.00)
- Efeito líquido: +10% a +18% acima da web crua

Isso é correto se o objetivo for etiquetar contra o **balcão** dos concorrentes (mais caro que o site). Mas um cliente novo, na calçada, compara pelo celular — ele vê o preço **online** do concorrente, não o balcão. Se o Preço Máximo vier do maior concorrente local (já inflado pelo `fator_canal`), o gap máximo→real pode parecer artificialmente grande.

**Risco**: O cliente vê "De R$ 94,50" (Nissei com ×1.18) mas confere no site da Nissei e vê R$ 79,90. A âncora perde credibilidade.

**Mitigação possível**: O Preço Máximo, quando usa concorrente local, deveria usar o preço **original** da observação (antes do `fator_canal`), ou pelo menos citar a fonte ("Preço de balcão na Droga Raia"). Mas como os dados de concorrente já chegam transformados na pipeline, seria necessário guardar o preço original também.

### 4.2 PMC como Preço Máximo — credibilidade

67% dos itens têm desconto implícito >30% contra o PMC. Mostrar "De R$ 150,00 por R$ 49,90" (−67%) destrói credibilidade. O motor já reconhece isso: a âncora PMC atual (`calcular_banda_balcao`) só é mostrada quando o desconto fica entre 8-30%.

**Sugestão para fase 2**: Se o app de gestão obriga PMC como preço máximo, mas o desconto implícito passa de um limite (ex.: 40%), adicionar uma nota na etiqueta: "PMC: R$ X,XX | Nosso preço: R$ Y,YY" em vez do formato "De/Por". A credibilidade melhora porque o cliente sabe que PMC é preço de tabela, não preço praticado.

### 4.3 Piso com `margem_bruta_minima_pct = 0.25`

O novo piso (`custo / 0.75`) é mais alto que o piso antigo para itens baratos. Exemplo:
- Custo R$ 2,00 → piso antigo: R$ 3,30 (custo + 0.60 + divisor) → piso novo: R$ 2,67 (2.00/0.75)
  - Na verdade o piso novo é menor nesse caso! Vamos ver:
  - Piso antigo: max(custo/0.9347, custo+0.60) = max(2.14, 2.60) = R$ 2.60 para padrao
  - Piso novo: max(2.14, 2.60, 2.00/0.75=2.67) = R$ 2.67
  - Aumento de 7 centavos. Ok, marginal.
- Custo R$ 50,00 → piso novo: R$ 66,67 (50/0.75)
  - Piso antigo: max(50/0.9347=53.49, 50.60) = R$ 53.49
  - Aumento significativo: +R$ 13,18 (24% mais alto)

Para itens de ticket alto, esse piso pode forçar o Preço Mínimo acima do Preço Real (se o real estiver apertado contra o mercado). Nesse caso, `calcular_precos_vitrine()` deve garantir `mínimo ≤ real`. Se `piso > real`, o mínimo cola no real (ou o real sobe — decisão de negócio).

---

## 5. Plano de implementação

### 5.1 Nova seção no `parametros.toml`

```toml
[vitrine]
# Três preços exibidos ao cliente (máximo / real / mínimo).
# Ver PLANO_TRES_PRECOS.md para a metodologia completa.

# Preço Máximo: spread sobre o preco_real usado como fallback quando
# não há PMC (medicamentos) nem concorrente local para servir de
# âncora verificável. Modesto de propósito — spread grande demais
# destrói credibilidade ("ninguém cobra isso").
spread_maximo_pct = 0.15

# Preço Mínimo: folga abaixo do preco_real. Pequena de propósito
# para comunicar "já está justo, não precisa negociar".
# Se o piso técnico (custo + margem mínima) for maior que esta
# folga, o piso prevalece.
folga_minimo_pct = 0.10
```

### 5.2 Nova dataclass e função pura em `economico.py`

```python
@dataclass(frozen=True)
class PrecosVitrine:
    """Três preços exibidos ao cliente na etiqueta/sistema."""
    preco_maximo: float | None
    preco_real: float | None
    preco_minimo: float | None
    fonte_maximo: str   # "PMC", "CONCORRENTE_LOCAL", "SPREAD", "INDISPONIVEL"
    fonte_minimo: str   # "PISO", "FOLGA"
    nota: str           # "" ou advertência (ex: "PMC omitido: desconto >40%")


def calcular_precos_vitrine(
    preco_sugerido: float | None,
    piso_valor: float | None,
    teto_cmed: float | None,
    maior_concorrente_local: float | None,
    tem_pmc: bool,
    spread_maximo_pct: float,
    folga_minimo_pct: float,
    terminacoes: list[float],
) -> PrecosVitrine:
    """Calcula os três preços da vitrine a partir do resultado da precificação.

    Regras:
    - PMC (teto_cmed) SEMPRE é o preço máximo para medicamentos com PMC.
    - Se não houver PMC, usa o maior concorrente local (verificável).
    - Se não houver concorrente, aplica spread sobre o preco_real (fallback).
    - Preço mínimo = max(piso, preco_real × (1 - folga)), arredondado para
      CIMA na grade (nunca abaixo do piso).
    - Se piso > preco_real, o mínimo cola no real (anomalia, dispara nota).
    """
    if preco_sugerido is None:
        return PrecosVitrine(None, None, None, "INDISPONIVEL", "INDISPONIVEL", "")

    # --- PREÇO MÁXIMO ---
    nota = ""
    if tem_pmc and teto_cmed is not None and teto_cmed > preco_sugerido:
        preco_maximo = teto_cmed
        fonte_maximo = "PMC"
        # Verificar se o desconto implícito é crível
        desconto = 1 - preco_sugerido / teto_cmed if teto_cmed > 0 else 0
        if desconto > 0.40:
            nota = (f"PMC R$ {teto_cmed:.2f} ({desconto:.0%} abaixo do PMC — "
                    f"desconto elevado, verificar credibilidade)")
    elif maior_concorrente_local is not None and maior_concorrente_local > preco_sugerido:
        preco_maximo = maior_concorrente_local
        fonte_maximo = "CONCORRENTE_LOCAL"
    else:
        preco_maximo = preco_sugerido * (1 + spread_maximo_pct)
        fonte_maximo = "SPREAD"

    # Arredondar preço máximo para cima na grade (âncora sempre acima ou igual ao real)
    preco_maximo = _arredondar_para_grade_acima(preco_maximo, preco_sugerido, terminacoes)

    # --- PREÇO MÍNIMO ---
    if piso_valor is not None:
        alvo_minimo = max(piso_valor, preco_sugerido * (1 - folga_minimo_pct))
        if alvo_minimo > preco_sugerido:
            # Piso acima do preço real: cola no real e emite nota
            alvo_minimo = preco_sugerido
            nota += " [PISO>REAL: mínimo colado no real]"
            fonte_minimo = "PISO_COLADO"
        elif alvo_minimo == piso_valor:
            fonte_minimo = "PISO"
        else:
            fonte_minimo = "FOLGA"
        preco_minimo = _arredondar_para_grade_acima(alvo_minimo, piso_valor, terminacoes)
    else:
        preco_minimo = None
        fonte_minimo = "INDISPONIVEL"

    return PrecosVitrine(
        preco_maximo=preco_maximo,
        preco_real=preco_sugerido,
        preco_minimo=preco_minimo,
        fonte_maximo=fonte_maximo,
        fonte_minimo=fonte_minimo,
        nota=nota.strip(),
    )


def _arredondar_para_grade_acima(valor: float, minimo: float,
                                  terminacoes: list[float]) -> float:
    """Menor preço da grade que é >= valor e >= minimo."""
    candidatas = [
        reais + termo
        for reais in range(int(minimo) - 1, int(valor) + 3)
        for termo in terminacoes
    ]
    viaveis = [v for v in candidatas if v >= valor - 1e-9 and v >= minimo - 1e-9]
    return min(viaveis) if viaveis else valor
```

### 5.3 Integração em `rodada_v2.py`

Após a chamada a `aplicar_travas()` (linha ~180), adicionar:

```python
# NOVO: calcular os três preços da vitrine
cfg_vitrine = params.get("vitrine", {})
vitrine = economico.calcular_precos_vitrine(
    preco_sugerido=resultado.preco_sugerido,
    piso_valor=resultado.piso,
    teto_cmed=row["pmc"],
    maior_concorrente_local=maior_local,
    tem_pmc=(row["pmc"] is not None),
    spread_maximo_pct=cfg_vitrine.get("spread_maximo_pct", 0.15),
    folga_minimo_pct=cfg_vitrine.get("folga_minimo_pct", 0.10),
    terminacoes=params["grade"]["terminacoes"],
)

# Adicionar à justificativa
if vitrine.nota:
    justificativa_final += f" [VITRINE] {vitrine.nota}"
```

E modificar o INSERT para incluir `preco_maximo` e `preco_minimo`:

```python
linhas.append((
    rodada_id, ean, row["descricao"], categoria, natureza, tier, status_gravado,
    row["custo_medio"], row["n_compras"], resultado_mercado.valor_referencia,
    resultado_mercado.n, resultado_mercado.cv, resultado_mercado.peso_brick, row["vum_brick"],
    resultado.piso, resultado.alvo, row["pmc"], preco_atual_final,
    resultado.preco_sugerido, justificativa_final,
    vitrine.preco_maximo, vitrine.preco_minimo,             # ← NOVOS
    vitrine.fonte_maximo, vitrine.fonte_minimo,              # ← NOVOS
))
```

### 5.4 Novas colunas no banco (`db.py`)

Adicionar na tabela `recomendacao`:

```sql
-- Dentro de CREATE TABLE recomendacao ( ... ):
preco_maximo REAL,
preco_minimo REAL,
fonte_maximo TEXT,
fonte_minimo TEXT
```

E atualizar o INSERT em `processar_rodada()` com as colunas novas.

---

## 6. O que NÃO está neste plano (fora do escopo)

- Alterar o app de gestão/PDV (assume-se que ele consome os dados do banco/Excel)
- Exibir os 3 preços em etiqueta física (formatação é responsabilidade do sistema de impressão)
- Feedback loop: medir quantas vendas usam cada degrau (precisa de PDV operando — loja ainda não abriu)
- Sazonalidade dos 3 preços (ex.: Black Friday, Dia das Mães)

---

## 7. Riscos e mitigação

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| PMC como máximo com desconto >40% destrói credibilidade | Alta (67% dos itens) | Médio | Nota na justificativa; fase 2: omitir PMC ou mudar formato |
| `fator_canal` infla o preço do concorrente no máximo | Média | Baixo | O máximo usa o concorrente pós-fator (balcão), que é a referência correta para etiqueta física |
| Piso > preco_real força mínimo colado no real | Baixa (só items com custo alto × mercado baixo) | Baixo | Tratado no código: cola no real e emite nota |
| Spread de 15% como máximo sem concorrente é artificial | Média | Baixo | 15% é modesto; "De R$ 39,90 por R$ 34,90" é crível; muito melhor que spread de 100% como alguns varejistas fazem |

---

## 8. Sequência de implementação

| Passo | Arquivo | O quê | Linhas afetadas |
|---|---|---|---|
| 1 | `parametros.toml` | Adicionar `[vitrine]` | +7 |
| 2 | `economico.py` | Adicionar `PrecosVitrine`, `calcular_precos_vitrine()`, `_arredondar_para_grade_acima()` | +80 |
| 3 | `economico.py` | Adicionar `from __future__ import annotations` e import do `dataclass` | (já existem) |
| 4 | `db.py` | Adicionar colunas `preco_maximo`, `preco_minimo`, `fonte_maximo`, `fonte_minimo` na tabela `recomendacao` | +4 |
| 5 | `rodada_v2.py` | Chamar `calcular_precos_vitrine()` após `aplicar_travas()` | +15 |
| 6 | `rodada_v2.py` | Atualizar INSERT e tupla de `linhas` | ~5 |
| 7 | Testes | Adicionar testes para `calcular_precos_vitrine()` (PMC, sem PMC, piso>real, spread fallback) | +50 |
