# Guia do Desenvolvedor — Precificador v2

## 1. Setup Local

### Requisitos
- Python 3.10+
- `pip` ou `poetry`
- SQLite3 (geralmente incluído)

### Instalação

```bash
cd Precificação/precificador
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

pip install -r requirements.txt
```

### Verificação
```bash
python -c "import sqlite3; print('SQLite OK')"
pytest --version
```

---

## 2. Estrutura de Diretórios

```
Precificação/
├── precificador/
│   ├── __init__.py
│   ├── config/
│   │   └── parametros.toml        # Configuração do sistema
│   ├── engine/
│   │   ├── mercado.py             # Motor de filtro de outliers + blend
│   │   ├── economico.py           # Motor de cálculo de markup
│   │   └── parametros.py          # Loader de config
│   ├── db.py                      # Schema SQLite + funções de BD
│   ├── ingest.py                  # Carregadores de fontes externas
│   ├── rodada_v2.py               # Orquestrador principal
│   ├── exportar_excel.py          # Exportação de resultado
│   ├── precificador.db            # SQLite (runtime)
│   └── tests/
│       ├── test_mercado.py        # Testes do motor de mercado
│       └── test_economico.py      # Testes do motor econômico
├── ESTUDO_PRECIFICACAO_DROGARIA.md
├── PLANO_SISTEMA_PRECIFICACAO.md
├── ARQUITETURA_PRECIFICADOR.md
└── [fontes de dados .xlsx/.csv]
```

---

## 3. Ciclo de Desenvolvimento

### 3.1 Adicionar Teste

Padrão: Arrange-Act-Assert

```python
# precificador/tests/test_mercado.py
def test_filtro_descarta_preco_muito_antigo():
    """Verifica se observações com >30 dias são descartadas."""
    HOJE = date(2026, 8, 4)
    lista = [
        Observacao(site="teste", preco=20.0, status="OK", 
                   data_hora=HOJE - timedelta(days=35)),
        Observacao(site="teste", preco=20.0, status="OK",
                   data_hora=HOJE),
    ]
    
    resultado = mercado.filtrar_outliers(lista, PARAMS, HOJE)
    
    # Assert
    assert len(resultado.mantidas) == 1
    assert resultado.mantidas[0].data_hora == HOJE
```

Rodar:
```bash
pytest precificador/tests/test_mercado.py::test_filtro_descarta_preco_muito_antigo -v
```

### 3.2 Executar Todos os Testes

```bash
pytest precificador/tests/ -v --cov=precificador
```

Esperado: 36 testes passando, ~80% cobertura.

### 3.3 Modificar Motor de Cálculo

Exemplo: aumentar markup alvo para perfumaria.

1. **Editar config:**
   ```toml
   # config/parametros.toml
   [economico]
   markup_alvo_perfumaria = 0.45  # novo
   ```

2. **Atualizar loader:**
   ```python
   # engine/parametros.py
   @dataclass
   class Parametros:
       # ...
       markup_alvo_perfumaria: float = 0.45
   ```

3. **Usar no motor:**
   ```python
   # engine/economico.py
   if produto.grupo_pai == "PERFUMARIA":
       markup = parametros.markup_alvo_perfumaria
   ```

4. **Adicionar teste:**
   ```python
   def test_perfumaria_usa_markup_alvo_45pct():
       resultado = economico.calcular_preco(
           ean="test_perfumaria",
           custo=10.0,
           param=PARAMS,
       )
       assert resultado.markup_realizado >= 0.45
   ```

5. **Rodar testes:**
   ```bash
   pytest precificador/tests/ -v
   ```

6. **Commit:**
   ```bash
   git add -A
   git commit -m "feat(economico): markup 45% para perfumaria"
   ```

---

## 4. Dados e Importação

### 4.1 Preparar Nova Rodada

Quando há novos dados (ex: NF mais recente, atualização Brick):

```bash
cd Precificação/precificador

# 1. Substituir arquivo de origem (ex: Relatório notas fiscais)
# 2. Apagar BD antigo (será recriado)
rm precificador.db

# 3. Carregar tudo (idempotente)
python -c "from ingest import main; main()"

# 4. Executar precificação
python rodada_v2.py
```

Resultado: `ESTOQUE_DROGARIA_PRECIFICADO.xlsx`

### 4.2 Debugar Carga de Um EAN

```python
# Interativo (python -i ou iPython)
import sqlite3
from engine import mercado, economico, parametros as pmod

conn = sqlite3.connect("precificador.db")
PARAMS = pmod.carregar()

# Buscar observações de web para um EAN
EAN = "7891234567890"
cursor = conn.execute(
    "SELECT site, preco, status, data_hora, observacoes FROM observacao_preco_web WHERE ean = ?",
    (EAN,)
)
observacoes = [mercado.Observacao(*row) for row in cursor.fetchall()]

# Filtrar outliers
resultado_filtro = mercado.filtrar_outliers(observacoes, PARAMS, date.today())
print(f"Mantidas: {len(resultado_filtro.mantidas)}")
print(f"Descartadas: {len(resultado_filtro.descartadas)}")
for desc in resultado_filtro.descartadas[:3]:
    print(f"  - {desc.observacao.preco} ({desc.camada}: {desc.motivo})")
```

---

## 5. Code Style

### Padrão

- **Type hints** em todas as assinaturas (PEP 484)
- **Dataclasses** para estruturas de dados (imutáveis com `frozen=True`)
- **Docstrings** apenas em funções complexas (1 linha em geral)
- **Nomes descritivos** — `preco_minimo` não `pm`

```python
from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class ResultadoPreco:
    ean: str
    preco_sugerido: float
    confianca: str
    markup_realizado: float
```

### Formatação

```bash
# Auto-format (black)
black precificador/ --line-length=100

# Verificar tipos
mypy precificador/
```

### Imports

Agrupar em 3 blocos (stdlib, third-party, local):
```python
import sqlite3
from pathlib import Path

from openpyxl import load_workbook

from . import db
```

---

## 6. Debugging

### Via Print (rápido)

```python
def filtrar_outliers(lista: list[Observacao], params: Parametros, hoje: date):
    print(f"DEBUG: recebidas {len(lista)} observacoes")
    mantidas, descartadas = _camada_1_natureza(lista)
    print(f"DEBUG: pos camada 1: {len(mantidas)} mantidas, {len(descartadas)} descartadas")
    return ResultadoFiltro(tuple(mantidas), tuple(descartadas))
```

Rodar: `python rodada_v2.py 2>&1 | grep DEBUG`

### Via Teste Isolado

```bash
pytest precificador/tests/test_mercado.py::test_camada_1_descarta_status_nao_ok_e_preco_ausente -vvs
```

Flag `-s` mostra prints, `-vvs` máximo verboso.

### Via Debugger (pdb)

```python
def economico_calcular_preco(...):
    import pdb; pdb.set_trace()  # Para aqui
    preco = custo * markup
    return preco
```

Rodar teste e debug interativamente.

---

## 7. Commits e PRs

### Mensagem de Commit

Formato: `<tipo>(<escopo>): <descrição>`

```
feat(economico): suportar aliquota dupla para ICMS-ST
fix(mercado): falso positivo em promo "de R$ X por R$ Y"
test(economico): cobertura para grid de ofertas
refactor(ingest): extrair normalizacao de EAN
```

### Checklist Antes do Commit

- [ ] Testes passam: `pytest precificador/tests/ -v`
- [ ] Cobertura >= 80%: `pytest --cov=precificador`
- [ ] Formato: `black precificador/`
- [ ] Tipos: `mypy precificador/`
- [ ] Sem hardcoded paths (usar `Path()` relativo)
- [ ] Docstring em funções públicas

---

## 8. Troubleshooting

### Erro: "No module named openpyxl"
```bash
pip install openpyxl
```

### Erro: "precificador.db: disk I/O error"
```bash
# BD corrompida, apagar e recarregar
rm precificador.db
python -c "from ingest import main; main()"
```

### Erro: "File not found: CUSTO_NF_XLSX"
- Verificar se arquivo existe em `Relatório notas fiscais 24-07_com_custo_unitario.xlsx`
- Editar path em `ingest.py` se necessário

### Testes falhando: "assert len(resultado.mantidas) == 1"
- Rodar com flag `-vvs` para ver output
- Adicionar print na função testada
- Verificar se `parametros.toml` foi modificado

---

## 9. Release Checklist

Antes de publicar nova versão (ex: v2.1):

- [ ] Todos testes passam e cobertura OK
- [ ] ARQUITETURA_PRECIFICADOR.md atualizado
- [ ] PLANO_SISTEMA_PRECIFICACAO.md sincronizado
- [ ] CHANGELOG.md com novidades
- [ ] Version bump em `__init__.py`
- [ ] Gerar ESTOQUE_DROGARIA_PRECIFICADO.xlsx limpo
- [ ] PR com descrição detalhada
- [ ] Code review aprovado
- [ ] Merge e tag git

---

## 10. Referências

- `PLANO_SISTEMA_PRECIFICACAO.md` — Especificação de negócio
- `ARQUITETURA_PRECIFICADOR.md` — Visão de componentes
- `engine/mercado.py` — Código do motor de filtro
- `engine/economico.py` — Código do motor de markup
- Testes: `precificador/tests/` — Exemplos de uso
