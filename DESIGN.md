---
name: MiniPreço
description: Sistema visual das ferramentas de precificação das Farmácias Associadas, extraído do app MiniPreço.
colors:
  teal: "#00B4AC"
  teal-acao: "#00706D"
  teal-pressionado: "#005F5C"
  teal-claro: "#E3F6F5"
  laranja: "#F26F20"
  laranja-texto: "#C2410C"
  laranja-claro: "#FFF1E8"
  fundo: "#F3F8F8"
  branco: "#FFFFFF"
  texto: "#123B42"
  texto-suave: "#5C7478"
  divisoria: "#9FC9C7"
  divisoria-forte: "#5C9490"
  linha-tabela: "#E6EFEF"
  zebra: "#FAFDFD"
  coleta-vazia: "#E1E9E9"
  alta: "#B42318"
  baixa: "#0B6B3A"
  impresso-borda: "#C9D6D6"
  impresso-apoio: "#4A6266"
typography:
  numero-decisao:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "26px"
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  marca:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "19px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "-0.015em"
  numero-apoio:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "normal"
  titulo:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "normal"
  body:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
    letterSpacing: "normal"
  meta:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  secao:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.08em"
  etiqueta:
    fontFamily: "'Segoe UI', system-ui, sans-serif"
    fontSize: "10px"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.07em"
rounded:
  sm: "3px"
  md: "6px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "20px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.teal-acao}"
    textColor: "{colors.branco}"
    rounded: "{rounded.sm}"
    padding: "10px 20px"
  button-primary-hover:
    backgroundColor: "{colors.teal-pressionado}"
    textColor: "{colors.branco}"
  bloco-decisao:
    backgroundColor: "{colors.teal-claro}"
    textColor: "{colors.texto}"
    rounded: "{rounded.sm}"
    padding: "8px 10px"
  bloco-alerta:
    backgroundColor: "{colors.laranja-claro}"
    textColor: "{colors.laranja-texto}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
  tabela-cabecalho:
    backgroundColor: "{colors.teal-acao}"
    textColor: "{colors.branco}"
    typography: "{typography.secao}"
    height: "38px"
---

## Overview

Sistema herdado do app MiniPreço (Tkinter), onde já foi calibrado com contraste
verificado linha a linha. O dashboard web estende esse mundo, não o substitui:
quem usa as duas telas no mesmo dia deve reconhecer a mesma ferramenta.

Registro é o de **instrumento de trabalho**: densidade alta, cromo baixo, cor
usada como sinal e não como enfeite. A tela é lida sentado, em monitor grande,
por alguém que já sabe o que está procurando.

## Colors

Teal é a cor da marca e da ação; laranja é a segunda cor e **trabalha**: marca
o que exige atenção (teto legal CMED, custo acima do mercado, título de seção).
Nunca use laranja como enfeite decorativo — ele perde a função de alerta.

- `teal-acao #00706D` sobre branco: 5.93:1. É o teal de texto e de botão.
- `teal #00B4AC` só como preenchimento e traço, nunca como texto sobre branco.
- `laranja-texto #C2410C` sobre branco: 5.18:1. É o laranja de texto.
- `laranja-claro #FFF1E8` com `texto #123B42` por cima: 10.98:1.
- `texto-suave #5C7478` é o rótulo; `texto #123B42` é o valor.

Estratégia: **Restrained** — neutros mais teal, com laranja reservado a sinal.
A tela é para operar; cor a mais compete com o número.

Variação percentual é o único lugar com semântica verde/vermelho, e sempre com
**sinal explícito** além da cor.

**Impressão tem dois tons próprios.** Etiqueta sai em papel, não em tela: a
divisória de tela (`divisoria #9FC9C7`) some na impressora e o texto de apoio
(`texto-suave #5C7478`) fica lavado no toner. Por isso `impresso-borda #C9D6D6`
para o contorno da etiqueta e `impresso-apoio #4A6266` para a apresentação do
produto — os dois existem só dentro da folha de etiquetas.

## Typography

Uma família só, `Segoe UI` com fallback de sistema. Peso e tamanho fazem toda a
hierarquia. Números tabulares (`font-variant-numeric: tabular-nums`) em toda
coluna de valor — sem isso a coluna não alinha e a comparação vertical morre.

Oito degraus, nada entre eles — meio pixel de diferença não é hierarquia, é
ruído: 26 (número que decide), 19 (marca), 16 (número de apoio), 14 (título de
painel), 13 (corpo e valor), 12 (meta e EAN), 11 (rótulo de seção, em
`laranja-texto`), 10 (etiqueta e badge).

## Layout

Densidade é requisito, não gosto: 3.400 linhas precisam caber. Linha de tabela
com 38–44px de altura, não mais. Rótulo à esquerda, valor à direita, dentro da
mesma linha — o padrão do painel lateral do app.

Grade do dashboard: tabela ocupa a área principal, painel de detalhe fixo à
direita com 340–380px. O painel **rola sozinho**, a tabela também, e o
cabeçalho de cada um fica sempre à vista.

Mais espaço acima de um título de seção do que abaixo dele.

## Elevation & Depth

Praticamente plano. Separação vem de linha de 1px (`divisoria #9FC9C7` entre regiões,
`linha-tabela #E6EFEF` entre linhas de tabela, que é mais leve porque se repete
40 vezes na tela) e de fundo (`zebra #FAFDFD` alternado, `fundo #F3F8F8` contra
`branco`). Blocos de destaque usam contorno de
1px na cor do próprio bloco, não sombra. Sombra só onde há sobreposição real
(menu de contexto, popover) e sempre com deslocamento e desfoque, nunca halo.

## Shapes

Raio pequeno: 3px em controles e blocos, 6px no que flutua. Formas retangulares
e honestas; nada de pílulas nem de cartões arredondados grandes.

## Components

**Cabeçalho de tabela:** faixa sólida `teal-acao`, texto branco, 38px, fixa na
rolagem. É a assinatura estrutural da referência do NAPP, na cor da casa.

**Bloco de decisão** (`teal-claro` com contorno `teal-acao`): guarda o número
que decide a venda. Um por tela, no máximo. É o maior número do painel.

**Bloco de alerta** (`laranja-claro` com contorno `laranja`): teto CMED, custo
acima do mercado. Só aparece quando existe o alerta — nunca em estado vazio.

**Linha rótulo/valor:** rótulo em `texto-suave` à esquerda, valor em `texto`
600 à direita. É a unidade de leitura do painel inteiro.

**Estado sem dado:** travessão `—` em `texto-suave`. Nunca zero, nunca vazio:
"não coletado" e "custa zero" são coisas diferentes.

## Do's and Don'ts

- **Faça** todo número dizer de onde veio e quando foi visto.
- **Faça** o dado do dia (coleta das farmácias) vir antes da base de cálculo.
- **Faça** a contagem de farmácias sair da lista, nunca escrita à mão: a lista
  cresce, e "8" fixo no texto vira mentira na primeira farmácia nova.
- **Faça** os três preços — motor, manual e praticado — ocuparem campos
  visualmente distintos. Nunca o mesmo lugar com significado variável.
- **Não** use cartões de tamanho igual como estrutura de página; a estrutura
  aqui é tabela e painel.
- **Não** use laranja decorativo. Laranja é alerta.
- **Não** troque `—` por `0` nem por célula vazia.
- **Não** esconda a procedência de um preço atrás de uma frase; ela é coluna.
