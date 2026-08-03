"""Schema e conexão do banco de precificação (SQLite)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "precificador.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS produto (
    ean TEXT PRIMARY KEY,
    descricao TEXT,
    grupo_pai_nf TEXT,
    grupo_filho_nf TEXT,
    classificacao_politica TEXT
);

CREATE TABLE IF NOT EXISTS custo_nf (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ean TEXT NOT NULL,
    quantidade REAL NOT NULL,
    custo_unitario REAL NOT NULL,
    valor_total REAL NOT NULL,
    tem_icms_st INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_custo_nf_ean ON custo_nf(ean);

CREATE TABLE IF NOT EXISTS preco_concorrente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ean TEXT NOT NULL,
    site TEXT NOT NULL,
    data_hora TEXT,
    status TEXT NOT NULL,
    preco REAL,
    observacoes TEXT
);
CREATE INDEX IF NOT EXISTS idx_preco_concorrente_ean ON preco_concorrente(ean);

CREATE TABLE IF NOT EXISTS preco_brick (
    ean TEXT PRIMARY KEY,
    vum REAL,
    curva_abc TEXT,
    posicao_mais_vendidos TEXT,
    segmento TEXT,
    pmc_maximo REAL
);

CREATE TABLE IF NOT EXISTS estoque (
    ean TEXT PRIMARY KEY,
    estoque_atual REAL,
    custo_unitario REAL,
    preco_venda_atual REAL,
    valor_total_custo REAL,
    valor_total_venda REAL
);

CREATE TABLE IF NOT EXISTS pmc_cmed_pr (
    ean TEXT PRIMARY KEY,
    descricao TEXT,
    fabricante TEXT,
    pmc REAL
);

CREATE TABLE IF NOT EXISTS subcategoria_classificada (
    ean TEXT PRIMARY KEY,
    classificacao_exata TEXT NOT NULL,
    fonte TEXT
);

CREATE TABLE IF NOT EXISTS politica_categoria (
    classificacao_exata TEXT PRIMARY KEY,
    papel TEXT,
    lucro_liquido_alvo_pct REAL,
    fator_fisico_antigo REAL,
    status_observacao TEXT
);

CREATE TABLE IF NOT EXISTS rodada (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    criada_em TEXT NOT NULL DEFAULT (datetime('now')),
    observacao TEXT
);

CREATE TABLE IF NOT EXISTS recomendacao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rodada_id INTEGER NOT NULL REFERENCES rodada(id),
    ean TEXT NOT NULL,
    descricao TEXT,
    categoria_provisoria TEXT,
    natureza_fiscal TEXT,
    tier TEXT,
    status TEXT NOT NULL,
    custo REAL,
    n_compras_nf INTEGER,
    mercado_referencia REAL,
    n_concorrentes INTEGER,
    cv REAL,
    peso_brick REAL,
    vum_brick REAL,
    piso REAL,
    alvo REAL,
    teto_cmed REAL,
    preco_atual REAL,
    preco_sugerido REAL,
    justificativa TEXT
);
CREATE INDEX IF NOT EXISTS idx_recomendacao_rodada ON recomendacao(rodada_id);
CREATE INDEX IF NOT EXISTS idx_recomendacao_ean ON recomendacao(ean);

CREATE TABLE IF NOT EXISTS carga_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fonte TEXT NOT NULL,
    arquivo TEXT NOT NULL,
    linhas_carregadas INTEGER NOT NULL,
    carregado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    try:
        conn.execute("ALTER TABLE produto ADD COLUMN marca_propria INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # coluna ja existe (rodadas anteriores)
    conn.commit()


def registrar_carga(conn: sqlite3.Connection, fonte: str, arquivo: str, linhas: int) -> None:
    conn.execute(
        "INSERT INTO carga_log (fonte, arquivo, linhas_carregadas) VALUES (?, ?, ?)",
        (fonte, arquivo, linhas),
    )
    conn.commit()
