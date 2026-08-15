"""Validacao e recuperacao de GTIN. Casos reais do cadastro (15/08/2026)."""
from gerar_acoes_cadastro import candidatos, com_dv, dv_ok


def test_gtin13_valido():
    assert dv_ok("7894900010015")   # Coca-Cola lata 350ml, conferido na internet
    assert dv_ok("7891317015176")   # Minilax bisnaga


def test_upc12_com_zero_a_esquerda_e_valido():
    """O zero cai em campo numerico e sobram 11 digitos -- nao e codigo invalido."""
    assert dv_ok("070341689769")    # Santo Habito, como esta na planilha
    assert dv_ok("70341689769")     # o mesmo sem o zero
    assert dv_ok("70847022503")     # Monster (caixa)
    assert dv_ok("70341368190")     # Deo Principia


def test_digito_errado_e_reprovado():
    assert not dv_ok("7894900010013")   # Coca-Cola com o ultimo digito trocado
    assert not dv_ok("7896104994006")   # Fralda Lovecare XG


def test_nao_e_codigo_de_barras():
    assert not dv_ok("00000")


def test_com_dv_fecha_o_codigo():
    assert com_dv("789490001001") == "7894900010015"
    assert com_dv("789490050000") == "7894900500004"   # Powerade Limao


def test_ultimo_digito_corrigido_recupera_o_ean_real():
    """Erro de digitacao no ultimo digito: o corpo esta certo."""
    achados = [c for c, _ in candidatos("7894900010013")]
    assert "7894900010015" in achados
    achados = [c for c, _ in candidatos("7896104994006")]
    assert "7896104994009" in achados


def test_dun14_devolve_o_ean13_embutido():
    assert "7894900010015" in [c for c, _ in candidatos("17894900010015")]


def test_candidato_nunca_repete_o_proprio_codigo():
    assert "7894900010015" not in [c for c, _ in candidatos("7894900010015")]


if __name__ == "__main__":
    import sys
    sys.exit(__import__("pytest").main([__file__, "-q"]))
