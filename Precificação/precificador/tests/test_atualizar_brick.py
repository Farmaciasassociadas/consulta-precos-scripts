"""Duas armadilhas da planilha do Brick, que nao dao erro nenhum quando erram:
o cabecalho nao fica na mesma linha em todas as abas, e `segmento` e' o EIXO
(nome da aba), nao a coluna "Catalogo Guia"."""
import sys
from pathlib import Path

import pytest
from openpyxl import Workbook

sys.path.insert(0, str(Path(__file__).parent.parent))
from atualizar_brick import atualizar, ler_brick  # noqa: E402

CABECALHO = ["Produto Desc Longa", "Ean", "Catálogo Guia", "RK BRICK",
             "CURVA EM VALOR", "VUM"]


@pytest.fixture
def planilha(tmp_path):
    wb = Workbook()
    rx = wb.active
    rx.title = "RX"
    rx.append(CABECALHO)
    rx.append(["FORXIGA 10MG", "005000456028561", "OUTROS", "5º", "A", 144.33])
    nmed = wb.create_sheet("NMED")
    nmed.append(["NAO_MEDICAMENTO_NTR", "REFERE A NUTRICIONAIS"])  # cabecalho so na 3a linha
    nmed.append([])
    nmed.append(["Setor nec Aberto", *CABECALHO])
    nmed.append(["NTR", "NINHO 800G", "0000078948327", "NMED_FORMULA", "1º", "B", 46.25])
    caminho = tmp_path / "brick.xlsx"
    wb.save(caminho)
    return caminho


def test_le_as_abas_com_cabecalho_deslocado(planilha):
    dados = ler_brick(planilha)
    # O EAN vai sem zero de enchimento, como o resto do projeto.
    assert set(dados) == {"5000456028561", "78948327"}
    assert dados["78948327"]["vum"] == pytest.approx(46.25)
    assert dados["78948327"]["posicao"] == "1º"


def test_segmento_e_o_eixo_da_aba_e_nao_o_catalogo(planilha):
    dados = ler_brick(planilha)
    assert dados["5000456028561"]["segmento"] == "RX"
    assert dados["78948327"]["segmento"] == "NMED"


def test_ean_fora_da_planilha_perde_o_brick_antigo(planilha, tmp_path):
    referencia = tmp_path / "ref.csv"
    referencia.write_text(
        "ean,categoria_provisoria,tem_icms_st,vum_brick,curva_abc,segmento_brick,pmc_maximo\n"
        "0005000456028561,MED,0,99.9900,C,NMED,150\n"
        "0000000009999999,MED,0,12.3400,A,RX,20\n",
        encoding="utf-8-sig")
    resumo = atualizar(planilha, referencia)
    assert (resumo["casaram"], resumo["perderam"]) == (1, 1)
    linhas = referencia.read_text(encoding="utf-8-sig").splitlines()
    assert linhas[1].split(",")[3:7] == ["144.3300", "A", "RX", "150"]
    # Preco velho de item que saiu do painel e' preco errado: sai junto.
    assert linhas[2].split(",")[3:6] == ["", "", ""]
