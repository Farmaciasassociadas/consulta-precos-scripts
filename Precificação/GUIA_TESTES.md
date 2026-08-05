# Guia de Testes — Precificador v2

**Objetivo:** 80%+ cobertura. **Framework:** pytest. **Rodadas:** 36 testes.

---

## 1. Estrutura de Testes

```
precificador/tests/
├── __init__.py
├── test_mercado.py         # Motor de filtro + blend (20 testes)
└── test_economico.py       # Motor de markup (16 testes)
```

---

## 2. Rodando Testes

### Todos os Testes

```bash
cd Precificação/precificador
pytest tests/ -v
```

Esperado:
```
tests/test_mercado.py::test_camada_1_descarta_status_nao_ok_e_preco_ausente PASSED
tests/test_mercado.py::test_camada_1_descarta_preco_promocional PASSED
...
====== 36 passed in 2.45s ======
```

### Com Cobertura

```bash
pytest tests/ --cov=precificador --cov-report=term-missing
```

Mostra:
- % cobertura por módulo
- Linhas não testadas

### Um Teste Específico

```bash
pytest tests/test_mercado.py::test_camada_1_descarta_status_nao_ok_e_preco_ausente -v
```

### Verbose (com prints)

```bash
pytest tests/ -vvs
```

---

## 3. Anatomia de um Teste

Padrão **AAA** (Arrange-Act-Assert):

```python
from datetime import date, timedelta
from engine import mercado, parametros

def test_camada_1_descarta_preco_promocional():
    # ARRANGE: preparar dados
    lista = [
        mercado.Observacao(
            site="farmacia_x",
            preco=15.0,
            status="OK",
            data_hora=date(2026, 8, 4),
            observacoes="Promoção: leve 2 pague 1",
        ),
        mercado.Observacao(
            site="farmacia_y",
            preco=18.0,
            status="OK",
            data_hora=date(2026, 8, 4),
            observacoes=None,
        ),
    ]
    
    params = parametros.carregar()
    hoje = date(2026, 8, 4)
    
    # ACT: executar função
    resultado = mercado.filtrar_outliers(lista, params, hoje)
    
    # ASSERT: verificar resultado
    assert [o.preco for o in resultado.mantidas] == [18.0]
    assert len(resultado.descartadas) == 1
    assert resultado.descartadas[0].camada == "natureza"
    assert "leve" in resultado.descartadas[0].motivo.lower()
```

---

## 4. Testes do Motor de Mercado (`test_mercado.py`)

### Camada 1: Natureza

```python
def test_camada_1_descarta_status_nao_ok_e_preco_ausente():
    """Remove preços com status != OK ou preço nulo."""
    lista = [
        obs(10.0, status="NAO_ENCONTRADO"),
        obs(None, status="OK"),
        obs(20.0),  # OK, status padrão
    ]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert [o.preco for o in r.mantidas] == [20.0]
    assert len(r.descartadas) == 2
```

### Camada 2: Frescor

```python
def test_camada_2_descarta_observacao_muito_antiga():
    """Remove observações com >30 dias."""
    lista = [
        obs(15.0, dias_atras=35),  # descarta
        obs(18.0, dias_atras=5),   # mantém
    ]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    assert len(r.mantidas) == 1
    assert r.descartadas[0].camada == "frescor"
```

### Camada 3: Distância (Outliers)

```python
def test_camada_3_descarta_outlier_acima_3sigma():
    """Remove preços >3σ da mediana."""
    lista = [
        obs(10.0),
        obs(11.0),
        obs(12.0),
        obs(100.0),  # outlier
    ]
    r = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    # mantém os 3 próximos, descarta o 100
    precos = sorted(o.preco for o in r.mantidas)
    assert 100.0 not in precos
```

### Blendagem Brick/Web

```python
def test_blend_brick_web_com_confianca_alta():
    """Quando web tem n>=3 e CV baixo, blend dá 90% web + 10% Brick."""
    brick = 10.0
    lista_web = [9.5, 10.0, 10.5]  # mediana 10.0
    
    resultado_mercado = mercado.resultado_mercado_completo(
        observacoes=lista_web,
        brick=brick,
        parametros=PARAMS,
    )
    
    # Com confiança alta, peso_brick deve ser baixo
    assert resultado_mercado.peso_brick < 0.2
    assert abs(resultado_mercado.valor_referencia - 10.0) < 0.1
```

---

## 5. Testes do Motor Econômico (`test_economico.py`)

### Cálculo de Custo Fiscal

```python
def test_calcula_custo_com_st():
    """ST: custo × (1 + PIS_COFINS). ICMS próprio é 0%."""
    custo_nf = 10.0
    resultado = economico.calcular_preco(
        ean="teste",
        custo=custo_nf,
        tem_icms_st=True,
        marca_propria=False,
        parametros=PARAMS,
    )
    
    # ST: 10 × (1 + 15.5%) = 11.55
    expected_custo_fiscal = 10.0 * 1.1550
    assert abs(resultado.custo_fiscal - expected_custo_fiscal) < 0.01
```

### Markup Mínimo

```python
def test_markup_minimo_respeitado():
    """Preço final nunca fica abaixo de (custo_fiscal × (1 + markup_min))."""
    custo_nf = 10.0
    markup_min = 0.30
    
    resultado = economico.calcular_preco(
        ean="teste",
        custo=custo_nf,
        markup_min=markup_min,
        grupo_pai="GENERICO",
        parametros=PARAMS,
    )
    
    custo_fiscal = 10.0 * 1.1550
    preco_minimo_esperado = custo_fiscal * (1 + markup_min)
    
    assert resultado.preco_sugerido >= preco_minimo_esperado - 0.01
```

### Teto PMC-PR

```python
def test_preco_nao_ultrapassa_pmc_pr():
    """Se PMC-PR existe, preço sugerido não pode ser maior."""
    custo_nf = 10.0
    pmc_pr = 15.0
    
    resultado = economico.calcular_preco(
        ean="teste",
        custo=custo_nf,
        pmc_pr=pmc_pr,
        parametros=PARAMS,
    )
    
    assert resultado.preco_sugerido <= pmc_pr + 0.01
```

---

## 6. Fixtures Reutilizáveis

Para evitar repetição, criar fixtures em `conftest.py`:

```python
# precificador/tests/conftest.py
import pytest
from datetime import date
from engine import parametros, mercado

@pytest.fixture
def parametros_teste():
    """Parametros padrão para testes."""
    return parametros.carregar()

@pytest.fixture
def data_hoje():
    """Data de referência (não muda entre testes)."""
    return date(2026, 8, 4)

@pytest.fixture
def observacao_ok():
    """Observação padrão (OK, sem promoção)."""
    def _obs(preco=10.0, site="teste", dias_atras=0):
        from datetime import timedelta
        return mercado.Observacao(
            site=site,
            preco=preco,
            status="OK",
            data_hora=date(2026, 8, 4) - timedelta(days=dias_atras),
            observacoes=None,
        )
    return _obs
```

Usar nos testes:

```python
def test_exemplo(parametros_teste, data_hoje, observacao_ok):
    lista = [observacao_ok(10.0), observacao_ok(11.0)]
    r = mercado.filtrar_outliers(lista, parametros_teste, data_hoje)
    assert len(r.mantidas) == 2
```

---

## 7. Testes de Sanidade (Banco Real)

**Rodada 0 (Fase 1):** 727 EANs com custo e preço real da drogaria.

```python
def test_sanidade_banco_real():
    """Verifica se precificação funciona em 727 EANs reais."""
    import sqlite3
    conn = sqlite3.connect("precificador.db")
    
    # Carregar todos com custo
    cursor = conn.execute(
        "SELECT ean FROM custo_nf LIMIT 727"
    )
    eans = [row[0] for row in cursor.fetchall()]
    
    resultados = []
    for ean in eans:
        r = rodada_v2.precificar_ean(ean, PARAMS)
        assert r is not None
        assert r.preco_sugerido > 0
        resultados.append(r)
    
    # Stats
    precos = [r.preco_sugerido for r in resultados]
    markups = [r.markup_realizado for r in resultados]
    
    print(f"Precificados: {len(precos)}")
    print(f"Markup médio: {sum(markups)/len(markups):.1%}")
    
    # Verificar sanidade básica
    assert len(precos) == 727
    assert min(precos) > 0
    assert max(precos) < 1000  # nenhum preço absurdo
```

---

## 8. Adicionar Novo Teste

Checklist:

1. **Escrever teste RED** (falha inicialmente):
   ```python
   def test_meu_novo_caso():
       resultado = funcao_nova(parametro)
       assert resultado == esperado
   ```

2. **Rodar e confirmar falha:**
   ```bash
   pytest tests/test_mercado.py::test_meu_novo_caso -v
   # FAILED
   ```

3. **Implementar função:**
   ```python
   def funcao_nova(parametro):
       return parametro * 2
   ```

4. **Rodar novamente:**
   ```bash
   pytest tests/test_mercado.py::test_meu_novo_caso -v
   # PASSED
   ```

5. **Verificar cobertura:**
   ```bash
   pytest tests/ --cov=precificador
   ```

6. **Commit:**
   ```bash
   git add -A
   git commit -m "test(mercado): verificar caso novo"
   ```

---

## 9. Troubleshooting

### Erro: "AssertionError: assert 1 == 2"

```bash
# Rodar com output detalhado
pytest tests/test_mercado.py::test_falha -vvs
```

Ver o que foi retornado vs esperado.

### Erro: "TypeError: object is not callable"

Verificar se a função/fixture existe e foi importada corretamente.

### Testes passam, mas cobertura <80%

```bash
pytest --cov=precificador --cov-report=term-missing

# Procurar por linhas não cobertas:
# precificador/engine/economico.py:150
```

Adicionar teste que cubra linha 150.

---

## 10. CI/CD (Futuro)

Para integração contínua (GitHub Actions, etc):

```yaml
# .github/workflows/test.yml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - run: pip install -r requirements.txt
      - run: pytest Precificação/precificador/tests/ --cov
```

---

## 11. Checklist de Código

Antes de enviar PR, rodar:

```bash
# 1. Testes passam?
pytest tests/ -v

# 2. Cobertura OK?
pytest --cov=precificador --cov-report=term-missing

# 3. Sem erros de tipo?
mypy precificador/

# 4. Formatação OK?
black precificador/ --check

# 5. Sem linhas muito longas?
flake8 precificador/ --max-line-length=100
```

Se tudo OK: merge! 🎉
