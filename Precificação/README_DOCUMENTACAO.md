# Documentação do Precificador v2

**Data:** 04/08/2026  
**Versão:** v2.1  
**Escopo:** Sistema completo de precificação com 3 fontes de dados (Brick + Web + NF)

---

## 📚 Guias Disponíveis

### Para Começar Rápido ⚡
1. **[QUICK_START.md](QUICK_START.md)** (5 min)
   - Setup mínimo (Python + venv)
   - Verificar dados existem
   - Rodar primeira precificação
   - Troubleshooting básico

### Para Entender a Arquitetura 🏗️
2. **[ARQUITETURA_PRECIFICADOR.md](ARQUITETURA_PRECIFICADOR.md)** (15 min)
   - Visão geral do sistema
   - Componentes (Ingest, Mercado, Econômico, Exportação)
   - Fluxo de dados
   - Schema SQLite
   - Limitações conhecidas

### Para Desenvolver 🛠️
3. **[GUIA_DESENVOLVEDOR.md](GUIA_DESENVOLVEDOR.md)** (30 min)
   - Setup completo com dependências
   - Estrutura de diretórios
   - Ciclo de desenvolvimento (teste → implementação → commit)
   - Padrões de código (type hints, dataclasses)
   - Debugging técnicas
   - Checklist pré-commit

### Para Testar ✅
4. **[GUIA_TESTES.md](GUIA_TESTES.md)** (20 min)
   - Estrutura de testes (pytest)
   - Rodando testes (todos, um específico, com cobertura)
   - Anatomia AAA (Arrange-Act-Assert)
   - Testes por camada (Mercado, Econômico)
   - Fixtures reutilizáveis
   - Sanidade contra banco real (727 EANs)
   - Checklist antes de PR

### Para Entender os Dados 📊
5. **[DICIONARIO_DADOS.md](DICIONARIO_DADOS.md)** (30 min)
   - **Tabelas SQLite** (produto, custo_nf, brick_vum, pmc_pr, observacao_preco_web, resultado_preco, etc)
   - **Estruturas Python** (Observacao, ResultadoMercado, ResultadoEconomico)
   - **Arquivos externos** (xlsx, csv — quais colunas, onde estão)
   - **Queries SQL úteis** (validações, agregações)
   - **Glossário** (VUM, ST, PMC-PR, Markup, CV, σ, Blend, Frescor, Outlier, Confiança)

### Especificação de Negócio 📋
6. **[PLANO_SISTEMA_PRECIFICACAO.md](PLANO_SISTEMA_PRECIFICACAO.md)** (foi criado anteriormente)
   - Baseado em dados reais de 727 EANs
   - Análise comparativa Brick vs Web
   - Regras fiscais (ST, Simples, Monofásico)
   - Justificativa de cada decisão de design

---

## 🎯 Roteiros por Função

### Não-Técnico (Gerente / Fiscal)
1. Ler: [QUICK_START.md](QUICK_START.md) — entender como rodar
2. Ler: [PLANO_SISTEMA_PRECIFICACAO.md](PLANO_SISTEMA_PRECIFICACAO.md) — entender lógica de negócio
3. Consultar: [DICIONARIO_DADOS.md](DICIONARIO_DADOS.md) seção "Glossário" se tiver dúvida sobre termo

### Desenvolvedor Novo
1. Ler: [QUICK_START.md](QUICK_START.md) — rodar e ver funcionar (5 min)
2. Ler: [ARQUITETURA_PRECIFICADOR.md](ARQUITETURA_PRECIFICADOR.md) — entender componentes (15 min)
3. Ler: [GUIA_DESENVOLVEDOR.md](GUIA_DESENVOLVEDOR.md) — setup completo (30 min)
4. Rodar: `pytest tests/ -v` — ver testes passarem (2 min)
5. Editar: Um teste em [GUIA_TESTES.md](GUIA_TESTES.md) — fazer seu primeiro commit (20 min)

### Desenvolvedor Modificando Lógica
1. Consultar: [DICIONARIO_DADOS.md](DICIONARIO_DADOS.md) — entender campos
2. Ler: [PLANO_SISTEMA_PRECIFICACAO.md](PLANO_SISTEMA_PRECIFICACAO.md) — justificativa da regra
3. Editar função em `precificador/engine/*.py`
4. Adicionar teste em `precificador/tests/*.py` (ver [GUIA_TESTES.md](GUIA_TESTES.md))
5. Rodar: `pytest tests/ --cov=precificador` — verificar cobertura
6. Commit com mensagem descritiva

### Adicionando Nova Fonte de Dados
1. Ler: [DICIONARIO_DADOS.md](DICIONARIO_DADOS.md) seção "Tabelas SQLite"
2. Editar: `precificador/db.py` — criar tabela
3. Editar: `precificador/ingest.py` — criar `carregar_nova_fonte()`
4. Testar: Rodar ingest isoladamente
5. Validar: Consultar `carga_log` para confirmar

---

## 📁 Estrutura de Arquivos (Completa)

```
Precificação/
├── README_DOCUMENTACAO.md          👈 VOCÊ ESTÁ AQUI
├── QUICK_START.md
├── ARQUITETURA_PRECIFICADOR.md
├── GUIA_DESENVOLVEDOR.md
├── GUIA_TESTES.md
├── DICIONARIO_DADOS.md
├── PLANO_SISTEMA_PRECIFICACAO.md
├── ESTUDO_PRECIFICACAO_DROGARIA.md
├── METODOLOGIA_PRECO_SUGERIDO.txt
│
├── precificador/
│   ├── __init__.py
│   ├── config/
│   │   └── parametros.toml              # Configuração (dias, σ, aliquotas)
│   │
│   ├── engine/
│   │   ├── mercado.py                  # Motor filtro 4-camadas + blend
│   │   ├── economico.py                # Motor markup + fiscal
│   │   └── parametros.py               # Loader config
│   │
│   ├── db.py                           # Schema SQLite
│   ├── ingest.py                       # Carregadores (idempotentes)
│   ├── rodada_v2.py                    # Orquestrador
│   ├── exportar_excel.py               # Exportação resultado
│   ├── precificador.db                 # SQLite runtime
│   │
│   └── tests/
│       ├── test_mercado.py             # 20 testes
│       └── test_economico.py           # 16 testes
│
├── [Fontes de Dados .xlsx/.csv]
│   ├── Relatório notas fiscais 24-07_com_custo_unitario.xlsx
│   ├── estoque_pmc_brick.xlsx
│   ├── ean_descricao_fabricante_pmc_pr.xlsx
│   ├── POLITICA_MARKUP_POR_CATEGORIA.csv
│   └── [mais arquivos xlsx de saída]
│
└── [Outputs]
    └── ESTOQUE_DROGARIA_PRECIFICADO.xlsx  ← Resultado final
```

---

## 🚀 Checklist de Onboarding

### Dia 1: Setup (1 hora)
- [ ] Clone repo (`git clone ...`)
- [ ] Ler [QUICK_START.md](QUICK_START.md)
- [ ] Rodar `python rodada_v2.py` (gera Excel)
- [ ] Abrir `ESTOQUE_DROGARIA_PRECIFICADO.xlsx`, conferir preços fazem sentido

### Dia 2: Conceitos (2 horas)
- [ ] Ler [ARQUITETURA_PRECIFICADOR.md](ARQUITETURA_PRECIFICADOR.md)
- [ ] Ler [PLANO_SISTEMA_PRECIFICACAO.md](PLANO_SISTEMA_PRECIFICACAO.md)
- [ ] Consultar [DICIONARIO_DADOS.md](DICIONARIO_DADOS.md) para termos desconhecidos

### Dia 3-4: Desenvolvimento (8 horas)
- [ ] Ler [GUIA_DESENVOLVEDOR.md](GUIA_DESENVOLVEDOR.md)
- [ ] Rodar `pytest tests/ -v` (36 testes devem passar)
- [ ] Modificar um teste em [GUIA_TESTES.md](GUIA_TESTES.md) e fazer passar
- [ ] Adicionar novo teste para feature que quer implementar
- [ ] Implementar a feature até teste passar
- [ ] Rodar `pytest --cov=precificador` — cobertura >= 80%
- [ ] Fazer commit com mensagem descritiva

---

## 🔍 Troubleshooting Rápido

| Problema | Solução |
|---|---|
| "File not found: Relatório notas..." | Verificar path em `ingest.py:20` |
| "pytest: command not found" | `pip install pytest` |
| "sqlite3.Error: disk I/O error" | `rm precificador.db` + recarregar |
| "AssertionError: assert 1 == 2" | Rodar teste com `-vvs`: `pytest test_x.py::test_y -vvs` |
| Testes falhando após mudar config | Deletar `precificador.db` antes de rodar testes |
| Preços parecem altos/baixos? | Verificar markup policy em `POLITICA_MARKUP_POR_CATEGORIA.csv` |

---

## 📞 Contato / Suporte

**Perguntas sobre:**
- **Setup/execução?** → [QUICK_START.md](QUICK_START.md)
- **Arquitetura/componentes?** → [ARQUITETURA_PRECIFICADOR.md](ARQUITETURA_PRECIFICADOR.md)
- **Como modificar código?** → [GUIA_DESENVOLVEDOR.md](GUIA_DESENVOLVEDOR.md)
- **Como testar?** → [GUIA_TESTES.md](GUIA_TESTES.md)
- **O que cada campo significa?** → [DICIONARIO_DADOS.md](DICIONARIO_DADOS.md)
- **Por que essa regra de negócio?** → [PLANO_SISTEMA_PRECIFICACAO.md](PLANO_SISTEMA_PRECIFICACAO.md)

---

## 📊 Estatísticas da Documentação

| Documento | Linhas | Tempo de Leitura |
|---|---:|---:|
| QUICK_START.md | 130 | 5 min |
| ARQUITETURA_PRECIFICADOR.md | 260 | 15 min |
| GUIA_DESENVOLVEDOR.md | 330 | 30 min |
| GUIA_TESTES.md | 420 | 20 min |
| DICIONARIO_DADOS.md | 580 | 30 min |
| **TOTAL** | **1.720** | **1h 40 min** |

+ Documentos anteriores: `PLANO_SISTEMA_PRECIFICACAO.md`, `ESTUDO_PRECIFICACAO_DROGARIA.md`, `METODOLOGIA_PRECO_SUGERIDO.txt`

---

## ✅ Cobertura de Tópicos

- ✅ Setup local (QUICK_START, GUIA_DESENVOLVEDOR)
- ✅ Arquitetura geral (ARQUITETURA_PRECIFICADOR)
- ✅ Cada componente (ingest, mercado, economico)
- ✅ Ciclo de dev (teste, implementação, commit)
- ✅ Testes (pytest, anatomia AAA, fixtures, cobertura)
- ✅ Dados (schema, campos, validações)
- ✅ Lógica de negócio (PLANO, ESTUDO, METODOLOGIA)
- ✅ Troubleshooting
- ✅ Roteiros por função

---

## 🎓 Versão

**Criada:** 04/08/2026  
**Precificador:** v2.1  
**Testes:** 36 (pytests)  
**Cobertura:** ~80%  
**EANs testados:** 727 (banco real)

---

**Última atualização:** 04/08/2026
