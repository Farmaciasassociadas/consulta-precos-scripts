"""Auditoria de categoria e de base de embalagem do relatorio de estoque do ERP.

Duas coisas que o relatorio nao resolve sozinho:

1. CATEGORIA. O `Nome Grupo` do ERP e' a fonte primaria, mas em 3 situacoes ele
   nao serve: e' guarda-chuva ("PERFUMARIA - GERAL", "NAO IDENTIFICADO"), ou
   contradiz a `Descricao da Classe Terapeutica` do proprio ERP, ou contradiz o
   segmento do Brick. O eixo (ETICOS/GENERICO/SIMILAR) vale dinheiro: e' ele que
   escolhe o lucro-alvo da politica, entao errar o eixo subprecifica o item.

2. BASE DE EMBALAGEM. O ERP mistura preco de caixa com preco de unidade nos
   fracionados: `Preco Comp.Unit`/`Preco de Venda` ficam na base da caixa
   enquanto `Ult. Prc. Entrada` fica na base da fracao. O preco praticado sai
   80x maior que o de mercado sem que nada esteja errado na politica de preco.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------- eixo

# A classe terapeutica e' um campo independente do grupo, preenchido pela
# distribuidora: quando os dois discordam, ha' evidencia de cadastro errado.
EIXO_POR_CLASSE = {
    "GENERICO": "GENERICO",
    "GENÉRICO": "GENERICO",
    "SIMILARES": "SIMILAR",
    "REFERENCIA": "ETICOS",
    "PERFUMARIA": "PERFUMARIA",
}
# Segmento do Brick -- auditoria de terceiro, mesma convencao de engine.economico.
EIXO_POR_BRICK = {"GEN": "GENERICO", "SIM": "SIMILAR", "RX": "ETICOS"}
EIXOS_MEDICAMENTO = ("ETICOS", "GENERICO", "SIMILAR")

# Traducao da subcategoria quando o item troca de eixo (SIMILAR usa nomes proprios).
SUBCATEGORIA_EQUIVALENTE = {
    ("SIMILAR", "RX"): "RX-SIMILAR",
    ("SIMILAR", "O.T.C/MIP"): "O.T.C/MIP-SIMILAR",
    ("ETICOS", "RX-SIMILAR"): "RX",
    ("ETICOS", "O.T.C/MIP-SIMILAR"): "O.T.C/MIP",
    ("GENERICO", "RX-SIMILAR"): "RX",
    ("GENERICO", "O.T.C/MIP-SIMILAR"): "O.T.C/MIP",
}

# ------------------------------------------------------- regras por descricao
# Ordem importa: a primeira que casar vence ("ESC DENTAL" antes de "ESCOVA",
# "LIXA" antes de qualquer coisa de unha). Sao intencionalmente coladas nas
# abreviacoes do ERP -- as regras do app usam nome por extenso e nao casam aqui.
# Nenhuma regra decide eixo de medicamento: nome comercial nao prova RX,
# controlado ou antibiotico.
REGRAS_DESCRICAO: tuple[tuple[str, str], ...] = (
    (r"\bESC(OVA)? DENTAL|CREME DENTAL|FIO DENTAL|FITA DENTAL|ENXAG|ANTISSEPT.* BUCAL|"
     r"LIMPADOR DE LINGUA|FIXADOR DE DENTADURA", "PERFUMARIA > HIGIENE BUCAL"),
    (r"CILIOS POSTICOS|\bBATOM\b|PO COMPACTO|PO BANANA|\bBLUSH\b|CORRETIVO|ILUMINADOR|"
     r"\bESMALTE\b|DELINEADOR|\bRIMEL\b|MASCARA (DE )?(CILIOS|SOBRANCELHA)|PINCEIS|"
     r"\bBASE (FACIAL|LIQUIDA)\b|ESPONJA MANGO", "PERFUMARIA > MAQUIAGEM"),
    (r"\bLIXA\b|\bPINCA\b|TESOURA|ALICATE|CORTADOR DE UNHA", "VAREJO > ACESSORIOS"),
    (r"\bAGULHA|SERINGA|\bGAZE\b|COMPRESSA|LANCETA|LUVA|ESPARADRAPO|ATADURA|CURATIVO|"
     r"BAND AID|TERMOMETRO|\bALCOOL\b", "VAREJO > ACESSORIOS"),
    (r"\bFRALDA|^FR VITA MAGNA", "PERFUMARIA > FRALDAS"),
    (r"MAMADEIRA|CHUPETA|SUGADOR NASAL|CONCHA PARA SEIO|\bBABY\b|INFANTIL",
     "PERFUMARIA > LINHA INFANTIL"),
    (r"ESCOVA DE CABELO|^SH |SHAMPOO|\bCOND(ICIONADOR)?\b|GEL FIXADOR|TOUCA DE CETIM|"
     r"MASCARA CAPILAR|CREME P/? PENTEAR", "PERFUMARIA > LINHA CAPILAR"),
    (r"TINTURA|COLORACAO|AGUA OXIG|DESCOLORANTE", "PERFUMARIA > TINTURAS"),
    (r"PROT(ETOR)? SOLAR|BRONZEAD|HIDRATANTE", "PERFUMARIA > BRONZ & HIDRATANTES"),
    (r"DESODORANTE|\bDEO\b|COLONIA|PERFUME", "PERFUMARIA > COLONIAS & DESODORANTES"),
    (r"TONICO FACIAL|LIMPEZA FACIAL|FAIXA FACIAL|AGUA MICELAR|\bSERUM\b|ESFOLIANTE|"
     r"CREME DE PEPINO", "PERFUMARIA > DERMOCOSMETICOS"),
    (r"\bSAB(ONETE)?\b|PAPEL HIG|TOALHA(S)? UMED|LENCO UMED|HASTE(S)? FLEXIVEI|"
     r"BOLAS DE ALGOD|\bALGODAO\b|ABSORVENTE|PROTETOR DIARIO|PRESERV|\bLAMINA\b|"
     r"APAR(ELHO)? BARBEAR", "PERFUMARIA > HIGIENE PESSOAL"),
    (r"CHOCOLATE|TABLETE|BOMBOM|\bBALA\b|PASTILHA|REFRIGERANTE|ENERGY|AGUA MINERAL|"
     r"\bWAFER\b|BISCOITO", "VAREJO > BEBIDAS E BOMBONIERE"),
    (r"JOELHEIRA|TORNOZELEIRA|MUNHEQUEIRA|MEIA (DE )?COMPRESSAO|BENGALA|CINTA ",
     "VAREJO > ORTOPEDICOS"),
    (r"LEITE EM PO|FORMULA INFANTIL|COMPOSTO LACTEO", "VAREJO > LEITES NUTRICAO"),
)

_ACENTOS = str.maketrans("ÁÀÃÂÄÉÊËÍÏÓÕÔÖÚÜÇ", "AAAAAEEEIIOOOOUUC")


def _limpar(texto: str) -> str:
    return str(texto or "").upper().translate(_ACENTOS)


def _num(valor) -> float | None:
    """Celula vazia do pandas vira NaN, e `bool(nan)` e' True -- sem isto todo
    item sem PMC passaria por "tem PMC"."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return None
    return None if v != v or v <= 0 else v


def categoria_por_descricao(descricao: str) -> str | None:
    alvo = _limpar(descricao)
    for padrao, categoria in REGRAS_DESCRICAO:
        if re.search(padrao, alvo):
            return categoria
    return None


def _partes(categoria: str) -> tuple[str, str]:
    eixo, _, sub = str(categoria or "").partition(" > ")
    return eixo, sub


def _recompor(eixo: str, sub: str, permitidas: set[str]) -> str | None:
    sub = SUBCATEGORIA_EQUIVALENTE.get((eixo, sub), sub)
    candidato = f"{eixo} > {sub}"
    if candidato in permitidas:
        return candidato
    padrao = {"ETICOS": "ETICOS > RX", "GENERICO": "GENERICO > RX",
              "SIMILAR": "SIMILAR > RX-SIMILAR", "PERFUMARIA": "PERFUMARIA > HIGIENE PESSOAL",
              "VAREJO": "VAREJO > VAREJINHO"}.get(eixo)
    return padrao if padrao in permitidas else None


def auditar_categoria(r, permitidas: set[str]) -> tuple[str | None, str]:
    """Devolve (categoria_proposta, evidencia). Proposta None = manter a atual.

    Ordem das evidencias, da mais forte para a mais fraca:
      1. PMC da CMED preenchido prova medicamento -- nao pode ficar em PERFUMARIA/VAREJO
      2. segmento do Brick (auditoria de terceiro) define o eixo
      3. classe terapeutica do proprio ERP define o eixo
      4. descricao resolve a subcategoria de nao-medicamento
    """
    atual = r["categoria_final"] or ""
    eixo_atual, sub_atual = _partes(atual)
    classe = _limpar(r["classe_terapeutica"])
    eixo_classe = EIXO_POR_CLASSE.get(classe)
    eixo_brick = EIXO_POR_BRICK.get(r["segmento_brick"] or "")
    tem_pmc = _num(r["pmc_cmed"]) is not None
    por_descricao = categoria_por_descricao(r["descricao"])

    # EXCLUSIVOS e' marca propria: eixo comercial, nao natureza do produto. Sair
    # dele custa 25% de lucro-alvo e o preco dela vem da lista do fornecedor, nao
    # da concorrencia. So o PMC (prova de medicamento) justifica mexer.
    if eixo_atual == "EXCLUSIVOS" and not tem_pmc:
        return None, ""

    # Gaze, agulha e bombom nao viram medicamento porque a distribuidora escreveu
    # "SIMILARES" na classe terapeutica. A descricao prova a natureza fisica e,
    # sem PMC, ela vence a classe e o Brick. Custa caro errar: VAREJO >
    # ACESSORIOS mira 25% de lucro contra 15% de SIMILAR > RX-SIMILAR.
    nao_medicamento = por_descricao and not por_descricao.startswith(EIXOS_MEDICAMENTO)
    if nao_medicamento and not tem_pmc and eixo_atual not in EIXOS_MEDICAMENTO:
        return (por_descricao, "descricao prova que nao e medicamento"
                ) if por_descricao != atual else (None, "")

    if r["segmento_brick"] == "NMED" and eixo_atual in EIXOS_MEDICAMENTO and not tem_pmc:
        alvo = por_descricao or "PERFUMARIA > HIGIENE PESSOAL"
        return (alvo, "Brick classifica como nao-medicamento (NMED) e nao ha PMC da CMED"
                ) if alvo != atual else (None, "")

    if eixo_brick and eixo_brick != eixo_atual:
        proposta = _recompor(eixo_brick, sub_atual or "RX", permitidas)
        if proposta and proposta != atual:
            return proposta, f"segmento do Brick = {r['segmento_brick']} (auditoria de terceiro)"

    # Promocao a medicamento sem o Brick dizer RX cai em O.T.C/MIP, nao em RX:
    # supor prescricao em pomada e polvilho e' o erro mais caro dos dois.
    # A classe terapeutica so decide eixo entre medicamentos ou quando nao ha eixo.
    # Ela vem preenchida com "SIMILARES" por default em Coca-Cola, Halls e KitKat:
    # se o proprio ERP ja pos o item em VAREJO/PERFUMARIA, esse campo nao tem
    # autoridade para promove-lo a medicamento -- so o Brick ou o PMC tem.
    classe_pode_mover = (eixo_classe == "PERFUMARIA"
                         or eixo_atual in EIXOS_MEDICAMENTO or not eixo_atual)
    if eixo_classe and eixo_classe != eixo_atual and not eixo_brick and classe_pode_mover:
        if eixo_classe == "PERFUMARIA":
            if tem_pmc:
                return None, ""  # tem PMC: e' medicamento, a classe esta errada
            proposta = por_descricao or "PERFUMARIA > HIGIENE PESSOAL"
        else:
            proposta = _recompor(eixo_classe, sub_atual or "O.T.C/MIP", permitidas)
        if proposta and proposta != atual:
            return proposta, f"classe terapeutica do ERP = {r['classe_terapeutica']}"

    if tem_pmc and eixo_atual not in EIXOS_MEDICAMENTO:
        proposta = _recompor("ETICOS", sub_atual or "O.T.C/MIP", permitidas)
        if proposta and proposta != atual:
            return proposta, "tem PMC na CMED: e' medicamento, nao pode ficar em PERFUMARIA/VAREJO"

    if not atual:
        if por_descricao:
            return por_descricao, "sem categoria: inferida pela descricao"
        if classe == "LIBERADOS":
            return "ETICOS > O.T.C/MIP", ("sem categoria: classe LIBERADOS (isento de "
                                          "prescricao) -- CONFERIR o eixo etico/similar")
        return None, ""

    if eixo_atual == "PERFUMARIA" and sub_atual in ("HIGIENE PESSOAL", ""):
        if por_descricao and por_descricao != atual and por_descricao.startswith("PERFUMARIA"):
            return por_descricao, "subcategoria generica: refinada pela descricao"
    return None, ""


# ------------------------------------------------------------ base de embalagem

TOLERANCIA_MERCADO = 0.30   # o preco corrigido tem de cair perto do preco de mercado
FATOR_MINIMO = 2.0


def _fator_de_embalagem(fator: float) -> float | None:
    """Embalagem tem numero inteiro de unidades. O fator tirado de
    custo/ultima-entrada e' ruidoso (custo medio contra ultima nota), entao so
    vale quando cai em cima de um inteiro -- 79,8 e' uma caixa de 80; 4,26 nao e'
    caixa nenhuma, e' custo desatualizado."""
    inteiro = round(fator)
    return float(inteiro) if inteiro >= FATOR_MINIMO and abs(fator - inteiro) <= 0.05 * inteiro else None


# Unidades de venda que aparecem depois do numero no nome do produto. O ERP
# abrevia ("C/10", "CX 30 COMP"); os sites escrevem por extenso ("7 Bisnagas",
# "56 Unidades", "12 Comprimidos"). Os dois lados precisam do mesmo leitor para
# que a comparacao de apresentacao signifique alguma coisa.
_UNIDADES_VENDA = (r"UN(?:IDADES?)?|COMP(?:RIMIDOS?)?|CPR|CAPS?(?:ULAS?)?|BISNAGAS?"
                   r"|TIRAS?|FLACONETES?|ENVELOPES?|SACHES?|AMPOLAS?|FRALDAS?")
# Em ordem de confianca, e a ordem importa. "REPOPIL 35 CPR C/63" tem os dois
# formatos: o 35 e' a dosagem/numero da marca e o 63 e' o conteudo. Uma
# alternacao unica devolveria o 35 so por vir antes na string, e o item entrava
# como apresentacao divergente sem ter divergencia nenhuma (mesmo caso de
# "ALMEIDA PRADO 46 CPR C/60" e "DIOSMINA+HESPERIDINA 450/50 CPR C/30").
_PADROES_CONTEUDO = (
    re.compile(r"\bC[/ ]?(\d{1,3})\b"),
    re.compile(r"\bCX (\d{1,3})\b"),
    re.compile(r"\bCOM (\d{1,3})\b"),
    re.compile(rf"\b(\d{{1,3}})\s?(?:{_UNIDADES_VENDA})\b"),
)


def _conteudo_declarado(descricao: str, minimo: int = 2) -> int | None:
    """C/10, CX 30 COMP, 20UN, "com 7 bisnagas", "56 Unidades" -> 10, 30, 20, 7, 56.

    `minimo=2` e' o default historico (para inferir fator de embalagem, 1 nao
    ajuda). A comparacao de apresentacao usa `minimo=1`, porque "C/1" contra
    "7 Bisnagas" e' justamente a divergencia que interessa.
    """
    texto = _limpar(descricao)
    for padrao in _PADROES_CONTEUDO:
        achado = padrao.search(texto)
        if achado and (valor := int(achado.group(1))) >= minimo:
            return valor
    return None


def conteudo_coletado(nomes) -> int | None:
    """Conteudo que a COLETA viu, pelo nome do produto no site do concorrente.

    Evidencia direta da apresentacao, diferente de `resolver_unidade`, que
    infere o fator e usa a sugestao do motor como arbitro -- circular quando a
    propria sugestao saiu de uma coleta em outra apresentacao. Foi o caso do
    Minilax: o ERP vende a bisnaga avulsa (C/1), a internet so vende a caixa de
    7, e a comparacao acusou um "prejuizo" de 83% que nao existia.

    Moda das leituras: um site que escreve o nome de outro jeito nao derruba o
    consenso dos demais.
    """
    lidos = [c for n in nomes if (c := _conteudo_declarado(n, minimo=1))]
    return max(set(lidos), key=lidos.count) if lidos else None


def resolver_unidade(r) -> tuple[float | None, float | None, str, str]:
    """Devolve (fator, preco_unitario_corrigido, situacao, explicacao).

    A sugestao do motor e' o arbitro: so aceita a correcao quando dividir o preco
    praticado pelo fator o coloca perto do preco de mercado. Sem esse teste seria
    chute -- um fator qualquer sempre "explica" a diferenca.
    """
    praticado, sugerido = _num(r["preco_praticado"]), _num(r["preco_sugerido"])
    if praticado is None:
        return None, None, "SEM PRECO", "item sem preco de venda cadastrado no ERP"
    if sugerido is None:
        return None, None, "", ""
    razao = praticado / sugerido
    if 0.4 <= razao <= 2.5:
        return None, None, "", ""

    candidatos: dict[str, float] = {}
    if r["un_cx"] > 1:
        candidatos["Unidades por Cx. do ERP"] = float(r["un_cx"])
    entrada, custo_erp = _num(r["ult_entrada"]), _num(r["custo_unit_erp"])
    if entrada and custo_erp:
        candidatos["custo do ERP / ultima entrada"] = custo_erp / entrada
    conteudo = _conteudo_declarado(r["descricao"])
    if conteudo:
        candidatos["conteudo declarado na descricao"] = float(conteudo)
    candidatos = {o: arredondado for o, f in candidatos.items()
                  if (arredondado := _fator_de_embalagem(f))}

    # Duas falhas opostas, e so uma delas se corrige mexendo no preco da loja.
    melhor = None
    for origem, fator in candidatos.items():
        # (a) a loja lancou preco de caixa como preco de unidade
        erro = abs(praticado / fator - sugerido) / sugerido
        if erro <= TOLERANCIA_MERCADO and (melhor is None or erro < melhor[0]):
            melhor = (erro, fator, round(praticado / fator, 2), origem, "loja")
        # (b) a loja vende a unidade e foi a COLETA que pegou a caixa: o preco da
        #     loja esta certo, quem esta na base errada e' a sugestao
        erro = abs(praticado - sugerido / fator) / (sugerido / fator)
        if erro <= TOLERANCIA_MERCADO and (melhor is None or erro < melhor[0]):
            melhor = (erro, fator, None, origem, "coleta")
    if melhor:
        _, fator, corrigido, origem, lado = melhor
        if lado == "loja":
            return fator, corrigido, "RESOLVIDO", (
                f"preco da loja estava na base de {fator:.0f} unidades ({origem}); "
                f"R$ {praticado:.2f} / {fator:.0f} = R$ {corrigido:.2f}, que bate com o "
                f"mercado (R$ {sugerido:.2f})")
        return fator, None, "SUGESTAO EM BASE DE CAIXA", (
            f"o preco da loja (R$ {praticado:.2f}) esta certo: a COLETA pegou a "
            f"embalagem de {fator:.0f} unidades ({origem}). Sugestao por unidade seria "
            f"R$ {sugerido / fator:.2f} -- nao aplicar os R$ {sugerido:.2f}")
    return None, None, "CONFERIR NA LOJA", (
        f"praticado (R$ {praticado:.2f}) e mercado (R$ {sugerido:.2f}) diferem "
        f"{max(razao, 1 / razao):.0f}x e nenhum fator de embalagem conhecido "
        f"({', '.join(f'{o}={f:.0f}' for o, f in candidatos.items()) or 'nenhum'}) explica")
