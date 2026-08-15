"""Leitura de apresentacao: conteudo declarado no ERP x conteudo visto na coleta.

Os nomes coletados abaixo sao literais do precos.csv (15/08/2026).
"""
from estoque_tratado_classificar import _conteudo_declarado, conteudo_coletado


def test_abreviacoes_do_erp():
    assert _conteudo_declarado("LORATADINA 10 MG CPR C/12 NEO/GN") == 12
    assert _conteudo_declarado("PARACETAMOL 500 MG CPR C/10 PRAT/GN") == 10
    assert _conteudo_declarado("FRALDA LOVECARE MEGA XG C/44") == 44
    assert _conteudo_declarado("SERINGA INSULINA 50UI X 8MM COM 100 UNIDADES") == 100


def test_nome_por_extenso_dos_sites():
    assert _conteudo_declarado("Minilax Com 7 Bisnagas", minimo=1) == 7
    assert _conteudo_declarado("Fralda Mili Love e Care Mega P 56 unidades", minimo=1) == 56
    assert _conteudo_declarado("Loratadina 10mg 12 Comprimidos Neo Química", minimo=1) == 12
    assert _conteudo_declarado("Epocler Abacaxi com 6 flaconetes", minimo=1) == 6


def test_conteudo_ganha_do_numero_da_marca():
    """"REPOPIL 35 CPR C/63": 35 e a marca/dosagem, 63 e o conteudo."""
    assert _conteudo_declarado("REPOPIL 35 CPR C/63") == 63
    assert _conteudo_declarado("ALMEIDA PRADO 46 CPR C/60") == 60
    assert _conteudo_declarado("DIOSMINA+HESPERIDINA 450/50 CPR C/30 BIOLAB/GN") == 30
    assert _conteudo_declarado("ELANI 28 CPR C/84") == 84


def test_c1_so_aparece_com_minimo_1():
    """Default historico ignora C/1 (nao serve de fator); a comparacao precisa dele."""
    assert _conteudo_declarado("MINILAX ADULTO BISNAGA C/1") is None
    assert _conteudo_declarado("MINILAX ADULTO BISNAGA C/1", minimo=1) == 1


def test_minilax_a_divergencia_que_gerou_o_falso_positivo():
    coletado = conteudo_coletado([
        "Minilax 714mg/g + 7,70mg/g Solução Retal 7 Bisnagas 6,5g",
        "Minilax Com 7 Bisnagas",
        "Minilax 7 Bisnagas Momenta",
        "Minilax 7 Bisnagas 6,5g",
    ])
    assert coletado == 7
    assert _conteudo_declarado("MINILAX ADULTO BISNAGA C/1", minimo=1) == 1


def test_moda_ignora_o_site_que_escreve_diferente():
    assert conteudo_coletado([
        "Paracetamol 500mg 10 Comprimidos Prati", "PARACETAMOL 500MG 10 COMPRIMIDOS",
        "Paracetamol 500mg 10 Comprimidos Genérico", "Paracetamol 500mg 20 Comprimidos",
    ]) == 10


def test_sem_quantidade_no_nome_nao_inventa():
    assert conteudo_coletado(["Vick Vaporub Pomada", "Vick VapoRub"]) is None
    assert conteudo_coletado([]) is None


def test_miligrama_nao_vira_quantidade():
    """"500 MG" nao e' conteudo de embalagem -- MG nao esta em _UNIDADES_VENDA."""
    assert _conteudo_declarado("DIPIRONA 500 MG", minimo=1) is None


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
