# Quick Start — Precificador v2

Seu 15 minutos para executar a primeira precificação.

---

## 1. Setup (5 min)

```bash
# Abrir PowerShell/Terminal em C:\Claude\Precificação
cd Precificação\precificador

# Criar ambiente Python
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Instalar dependências
pip install openpyxl sqlite3
```

---

## 2. Verificar Dados

Os arquivos **devem** estar em `C:\Claude\Precificação/`:

- ✓ `Relatório notas fiscais 24-07_com_custo_unitario.xlsx` — Custo NF
- ✓ `outputs/consolidado_estoque/estoque_pmc_brick.xlsx` — Brick
- ✓ `outputs/eans_pmc/ean_descricao_fabricante_pmc_pr.xlsx` — PMC-PR
- ✓ `POLITICA_MARKUP_POR_CATEGORIA.csv` — Markup policy
- ✓ `C:\Users\docze\ConsultaPrecosEAN/precos.csv` — Web coleta

Se algum faltar: o script de ingest vai reportar e parar.

---

## 3. Executar (5 min)

```bash
# Ainda em C:\Claude\Precificação\precificador
python rodada_v2.py
```

Esperado:
```
Carregando custos_nf... 1.247 linhas
Carregando brick_vum... 2.187 linhas
...
Precificando 727 EANs...
Exportando para Excel...
✓ ESTOQUE_DROGARIA_PRECIFICADO.xlsx (727 linhas)
```

Resultado: **`ESTOQUE_DROGARIA_PRECIFICADO.xlsx`**

---

## 4. Ver Resultado

Abrir `ESTOQUE_DROGARIA_PRECIFICADO.xlsx`:

| EAN | Descrição | Brick | Mediana Web | Custo | Preco Sugerido | Markup % | Confiança |
|---|---|---|---|---|---|---|---|
| 7891234567890 | Dipirona 500mg | 8.50 | 9.20 | 4.32 | 9.80 | 127% | ALTA |
| ... | ... | ... | ... | ... | ... | ... | ... |

---

## 5. Troubleshooting

| Erro | Solução |
|---|---|
| `FileNotFoundError: Relatório notas fiscais...` | Verificar arquivo existe e path em `ingest.py` linha 20 |
| `sqlite3.Error: disk I/O error` | `rm precificador.db` e rodar novamente |
| `ImportError: No module named openpyxl` | `pip install openpyxl` |
| `Nenhum EAN com custo_nf` | Verificar se NF xlsx está OK (abre no Excel?) |

---

## 6. Próximos Passos

- [ ] Verificar se preços fazem sentido (comparar com Brick)
- [ ] Ajustar POLITICA_MARKUP_POR_CATEGORIA.csv se necessário
- [ ] Rodar testes: `pytest tests/ -v` (36 testes)
- [ ] Ler `ARQUITETURA_PRECIFICADOR.md` se precisa customizar

---

## 7. Customizações Comuns

### Aumentar Markup de Uma Categoria

Editar `POLITICA_MARKUP_POR_CATEGORIA.csv`:
```csv
grupo_pai,markup_min,markup_alvo,markup_max
PERFUMARIA,0.30,0.50,0.65  # aumentou alvo de 0.45 para 0.50
```

Rodar novamente:
```bash
rm precificador.db
python rodada_v2.py
```

### Mudar Período de Frescor de Preços Web

Editar `config/parametros.toml`:
```toml
[mercado]
dias_max_frescor = 60  # estava 30
```

Rodar novamente.

### Exportar para CSV ao Invés de Excel

No final de `rodada_v2.py`:
```python
# Ao invés de:
# exportar_excel.salvar(resultado, "ESTOQUE_DROGARIA_PRECIFICADO.xlsx")

# Usar:
import csv
with open("ESTOQUE_DROGARIA_PRECIFICADO.csv", "w", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=resultado[0].keys())
    writer.writeheader()
    writer.writerows(resultado)
```

---

## 8. Documentação Completa

- **Arquitetura:** `ARQUITETURA_PRECIFICADOR.md`
- **Especificação:** `PLANO_SISTEMA_PRECIFICACAO.md`
- **Desenvolvimento:** `GUIA_DESENVOLVEDOR.md`
- **Código:** `precificador/engine/mercado.py`, `economico.py`
- **Testes:** `precificador/tests/`

---

## 9. Contato / Debug

Se precisa de suporte:

1. Rodar `python rodada_v2.py 2>&1 | tee debug.log`
2. Ler `debug.log` procurando por "ERROR" ou "WARNING"
3. Consultar seção de troubleshooting acima
4. Ler `ARQUITETURA_PRECIFICADOR.md` seção 4 (Uso)
