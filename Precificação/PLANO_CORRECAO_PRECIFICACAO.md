# Plano de Correção — Motor de Precificação

**Caso motivador**: Alprazolam Gen 2mg — custo R$ 35,35, preço sugerido R$ 38,49 (margem bruta 8,9%).
**Data**: 2026-08-08

---

## Diagnóstico (3 causas raiz)

| # | Problema | Causa no código | Impacto |
|---|----------|-----------------|---------|
| 1 | **Margem muito apertada** | `piso()` usa `contribuicao_minima_reais = 0,60` (R$ 0,60 acima do custo). O piso percentual (`divisor_piso_contribuicao`) só cobre custos **variáveis** (cartão + despesa variável + imposto), não despesa fixa. Resultado: piso de R$ 35,95 para custo de R$ 35,35 — margem de 1,7%. | Preço final pode ficar perigosamente próximo do custo sem que o motor reaja. |
| 2 | **Preços online tratados como preço de balcão** | `_fator_fisico` aplica um fator único por segmento Brick ou natureza fiscal, igual para todos os sites. Não existe correção por **site** para converter preço online → preço estimado de balcão. O gap online-balcao da Nissei é conhecidamente maior que o dos demais, mas o motor não sabe disso. | Preço sugerido é artificialmente puxado para baixo por sites com gap online-balcao grande. |
| 3 | **Peso geográfico inexistente** | `selecionar_vizinhanca` é **binária**: ou o site entra no alvo, ou não. Raia (mais próxima) e Nissei (mais distante) têm peso idêntico. A decisão de não usar peso por site foi documentada (instabilidade da mediana ponderada com n baixo), mas o efeito colateral é tratar concorrentes distantes com a mesma relevância de quem está do lado. | Preço de referência dilui a importância dos concorrentes que realmente disputam o cliente. |

---

## Plano de alteração

### Alteração 1 — Piso de margem bruta mínima

**Arquivo**: `engine/economico.py` — função `piso()` (linhas 169–171)
**Arquivo**: `config/parametros.toml` — seção `[premissas]`

**O que muda**:
Acrescentar um terceiro componente ao piso: `piso_margem = custo / (1 - margem_bruta_minima_pct)`. O piso final continua sendo `max(piso_simples, piso_contribuicao, piso_margem)`.

```python
# economico.py, função piso (após linha 171)
def piso(custo: float, params: dict[str, Any], natureza: str) -> float:
    piso_simples = custo / divisor_piso_contribuicao(params, natureza)
    piso_contribuicao = custo + params["premissas"]["contribuicao_minima_reais"]
    piso_margem = custo / (1 - params["premissas"].get("margem_bruta_minima_pct", 0.0))
    return max(piso_simples, piso_contribuicao, piso_margem)
```

**Config nova em `parametros.toml`**:
```toml
# NOVO: piso adicional de margem bruta mínima sobre o custo.
# Ex: 0.25 = o preço nunca fica abaixo de custo / (1 - 0.25) = custo / 0.75.
# Para custo de R$ 35,35 → piso de R$ 47,13.
# Zere para desabilitar (0.0).
margem_bruta_minima_pct = 0.25
```

**Impacto no caso**: Com margem mínima de 25%, o piso sobe de R$ 35,95 para R$ 47,13. O preço sugerido nunca mais sai a R$ 38,49 — no mínimo R$ 44,19 (grade mais próxima: R$ 44,49).

---

### Alteração 2 — Fator de correção online→balcão por site

**Arquivo**: `engine/mercado.py` — nova função + modificação em `calcular_mercado()`
**Arquivo**: `config/parametros.toml` — nova seção `[mercado.fator_canal_por_site]`

**O que muda**:
Cada observação de preço recebe um multiplicador por site **antes** de entrar nas 4 camadas de filtro. O fator converte o preço online coletado em estimativa de preço de balcão daquele concorrente.

**Nova função em `mercado.py`** (após `_e_promocional`, linha 82):
```python
def _aplicar_fator_canal(
    obs: list[Observacao], params: dict[str, Any]
) -> list[Observacao]:
    """Aplica fator de correção online→balcão por site a cada observação."""
    cfg = params["mercado"].get("fator_canal_por_site")
    if not cfg or not cfg.get("ativo", False):
        return obs
    default = cfg.get("default", 1.0)
    resultado = []
    for o in obs:
        fator = cfg.get(o.site, default)
        if fator != 1.0 and o.preco is not None:
            resultado.append(Observacao(
                site=o.site,
                preco=round(o.preco * fator, 2),
                status=o.status,
                data_hora=o.data_hora,
                observacoes=o.observacoes,
            ))
        else:
            resultado.append(o)
    return resultado
```

**Modificação em `calcular_mercado()`** (linha 318, antes da camada 1):
```python
# NOVO: aplica fator de canal online→balcão antes de qualquer filtro
observacoes = _aplicar_fator_canal(observacoes, params)

# Camadas 1-2 primeiro (natureza + frescor), sem depender do Brick.
descartadas: list[Descarte] = []
pre_ancora, novas = _camada_1_natureza(observacoes)
```

**Config nova em `parametros.toml`**:
```toml
# NOVO: fator de correção online→balcão por site.
# Cada site tem um multiplicador que converte o preço coletado no site (online)
# para estimativa de preço de balcão daquela farmácia.
# Base empírica: balcão é consistentemente mais caro que o site, com intensidade
# variável por rede (ex: Nissei tem gap maior que Raia).
[mercado.fator_canal_por_site]
ativo = true
drogaraia = 1.10
farmasp = 1.10
saopaulo = 1.10
saojoao = 1.10
nissei = 1.18
default = 1.10
```

**Impacto no caso**: Se a Nissei online está a R$ 32,00, o motor hoje usa R$ 32,00 como preço de referência. Com fator 1.18, passa a usar R$ 37,76 como estimativa de balcão da Nissei — mais próximo da realidade do que o cliente encontraria na loja física.

---

### Alteração 3 — Peso geográfico (média das medianas por site)

**Arquivo**: `engine/mercado.py` — nova função + modificação em `calcular_mercado()`
**Arquivo**: `config/parametros.toml` — nova seção `[mercado.peso_geografico]`

**Por que não usar peso na mediana ponderada direto**:
A docstring de `_mediana_ponderada` (linhas 156–163) já documenta o problema: com peso misto e n pequeno, a mediana ponderada é um **degrau** — para `[10,12,20,22]`, descontar uma observação devolve 20 ou 12 conforme QUAL foi descontada, nunca 16. Isso tornaria o preço instável a cada falha de coleta.

**Abordagem alternativa — média das medianas por site**:
1. Agrupa observações por site normalizado (usando `apelidos_site` para unificar farmasp/saopaulo)
2. Calcula a **mediana** de cada site (cada concorrente contribui com UM preço representativo)
3. Calcula a **média ponderada** das medianas por site usando os pesos geográficos

Isso é matematicamente estável (cada concorrente contribui igualmente, independentemente de quantas observações tem) e evita o problema do degrau.

**Nova função em `mercado.py`** (após `selecionar_vizinhanca`, linha 231):
```python
def _mediana_geografica(
    observacoes: list[Observacao],
    params: dict[str, Any],
    apelidos_site: dict[str, str] | None = None,
) -> float | None:
    """Média ponderada das medianas por site, usando pesos geográficos.

    Cada concorrente contribui com UM preço (sua mediana), evitando que
    sites com mais observações dominem o resultado. Os pesos representam
    a relevância geográfica/proximidade daquele concorrente.
    """
    cfg = params["mercado"].get("peso_geografico")
    if not cfg or not cfg.get("ativo", False):
        return _mediana_ponderada(observacoes, params)

    apelidos = apelidos_site or {}
    # Agrupa por site normalizado
    precos_por_site: dict[str, list[float]] = {}
    for o in observacoes:
        if o.preco is None:
            continue
        site_norm = apelidos.get(o.site, o.site)
        precos_por_site.setdefault(site_norm, []).append(o.preco)

    if not precos_por_site:
        return None

    # Mediana por site, ponderada por peso geográfico
    soma_ponderada = 0.0
    soma_pesos = 0.0
    for site, precos in precos_por_site.items():
        peso = cfg.get(site, 1.0)
        mediana_site = median(precos)
        soma_ponderada += mediana_site * peso
        soma_pesos += peso

    return soma_ponderada / soma_pesos if soma_pesos > 0 else None
```

**Modificação em `calcular_mercado()`** (linha 349, onde `_mediana_ponderada` é chamada para o alvo):
```python
# ANTES:
mediana_bruta = _mediana_ponderada(observacoes_alvo, params)

# DEPOIS:
apelidos = {k: v for k, v in (params["mercado"].get("vizinhanca", {}).get("apelidos_site") or {}).items()}
mediana_bruta = _mediana_geografica(observacoes_alvo, params, apelidos)
```

**Preços alvo**: `precos_alvo` no `ResultadoMercado` continua sendo os preços originais (sem peso). O peso geográfico afeta apenas a mediana que vira `mercado_web` e `valor_referencia`.

**Config nova em `parametros.toml`**:
```toml
# NOVO: peso geográfico por concorrente na média das medianas.
# Peso maior = concorrente mais relevante (mais próximo, mesma calçada).
# Sites não listados recebem peso 1.0.
# Só se aplica com vizinhança local ativa (>= n_min_local lojas distintas).
[mercado.peso_geografico]
ativo = true
drogaraia = 4.0     # mais próxima — mesmo quarteirão
farmasp = 3.5       # muito próxima (farmasp/saopaulo = mesma loja)
saopaulo = 3.5      # idem
saojoao = 1.5       # distância média
nissei = 1.0        # mais distante
```

**Impacto no caso**: Hoje a mediana trata Nissei (R$ 32 online → R$ 37,76 com fator canal) e Raia (R$ 40 online → R$ 44 com fator canal) com o mesmo peso. Com peso geográfico 4:1, o preço de referência pende fortemente para Raia/São Paulo — que são os concorrentes que realmente disputam o cliente que entra na loja.

---

### Alteração 4 — Testes

**Arquivos**: `tests/test_mercado.py`, `tests/test_economico.py`

#### 4a. `test_mercado.py` — testes novos

```python
# Teste: fator de canal por site
def test_fator_canal_aplica_correcao_por_site():
    """Nissei com fator 1.18 deve ter preço majorado; Raia com 1.10 também."""
    ...

def test_fator_canal_site_sem_fator_usa_default():
    """Site não listado usa o default (1.10)."""
    ...

def test_fator_canal_inativo_nao_altera():
    """Com ativo=false, preços não são alterados."""
    ...

# Teste: mediana geográfica
def test_mediana_geografica_ponderada():
    """Dois sites: um com peso 4, outro peso 1 → média ponderada das medianas."""
    ...

def test_mediana_geografica_site_com_apelido():
    """farmasp e saopaulo agrupados como mesma loja antes da mediana."""
    ...

def test_mediana_geografica_inativa_cai_na_mediana_simples():
    """Com ativo=false, devolve mediana simples (comportamento antigo)."""
    ...
```

#### 4b. `test_economico.py` — testes novos

```python
# Teste: piso com margem bruta mínima
def test_piso_respeita_margem_bruta_minima():
    """Custo 35.35, margem 25% → piso >= 47.13."""
    ...

def test_piso_margem_zero_nao_altera():
    """margem_bruta_minima_pct = 0 → comportamento idêntico ao anterior."""
    ...

def test_piso_prevalece_maior_dos_tres():
    """max(piso_simples, piso_contribuicao, piso_margem) — o maior vence."""
    ...
```

---

## Ordem de implementação

| Etapa | Arquivo | O quê |
|-------|---------|-------|
| 1 | `config/parametros.toml` | Adicionar `margem_bruta_minima_pct`, `[mercado.fator_canal_por_site]`, `[mercado.peso_geografico]` |
| 2 | `engine/economico.py` | Modificar `piso()` — incluir `piso_margem` |
| 3 | `engine/mercado.py` | Adicionar `_aplicar_fator_canal()`, `_mediana_geografica()`, modificar `calcular_mercado()` |
| 4 | `tests/test_economico.py` | Adicionar testes de piso com margem |
| 5 | `tests/test_mercado.py` | Adicionar testes de fator canal + mediana geográfica |
| 6 | — | Rodar `pytest precificador/tests/` e validar |

---

## Resultado esperado para o caso Alprazolam Gen 2mg

| Componente | Antes | Depois |
|------------|-------|--------|
| Custo | R$ 35,35 | R$ 35,35 |
| Piso | R$ 35,95 (contribuição mínima R$ 0,60) | **R$ 47,13** (margem bruta mínima 25%) |
| Preço online Nissei | R$ 32,00 (usado como se fosse balcão) | R$ 37,76 (com fator canal 1.18) |
| Preço online Raia | R$ 40,00 (mesmo peso que Nissei) | R$ 44,00 (com fator canal 1.10, peso 4×) |
| Preço sugerido | R$ 38,49 | **R$ 44,49 a R$ 47,90** (grade + competitivo) |
| Margem bruta | 8,9% | **25,9% a 35,5%** |

---

## Riscos e mitigação

| Risco | Mitigação |
|-------|-----------|
| **Fator canal superestima balcão**: se o gap real for menor que o configurado, o preço fica acima do mercado | Os fatores (`1.10`, `1.18`) são calibrações iniciais. Recalibrar após 30 dias com coleta real de balcão (cliente oculto ou auditoria própria) |
| **Peso geográfico distorce com poucos concorrentes**: se só 1–2 sites têm preço, o peso não importa | `_mediana_geografica` só se aplica com ≥ `n_min_local` (3 lojas distintas). Abaixo disso, cai na mediana simples |
| **Margem mínima de 25% exclui itens mais baratos que o mercado**: se todo mundo vende a R$ 40 e o piso é R$ 47, o item some da competição | O status `PISO_ACIMA_DO_MERCADO` sinaliza isso. Ajustar `margem_bruta_minima_pct` por categoria futuramente (ex: genéricos 20%, éticos 25%) |
| **Regressão**: comportamento de itens sem os 3 concorrentes locais não deve mudar | Todos os novos caminhos têm guarda: `ativo = true/false`, `n_min_local`, fallback para comportamento antigo |
