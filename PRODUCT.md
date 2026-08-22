# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Bruno (dono, admin).** Sentado no desktop, fora do horário de pico. Precifica
lotes de 300+ EANs por rodada, decide preço item a item e quer saber onde está
perdendo margem. É quem edita.

**Balcão (três contas `atendimentoassociadasmaringa`).** Em pé, atrás do caixa,
com cliente esperando e outra pessoa na fila. Consulta o preço de UM produto e
precisa da resposta em segundos. Só leitura.

**Leitura ocasional (docze2, dionatan).** Olham de vez em quando; mesma tela do
admin, sem poder editar.

## Product Purpose

Decidir e defender o preço de venda de ~3.400 produtos de farmácia. O motor de
precificação já calcula um preço sugerido a partir de custo, categoria, piso
competitivo e coleta diária das farmácias concorrentes. Este dashboard é a
tela onde esse trabalho é lido, conferido e corrigido de qualquer lugar —
hoje ele só existe dentro de um app Tkinter que roda em dois PCs.

## Positioning

Coleta própria e diária dos preços praticados pelas farmácias concorrentes
(oito hoje, a lista cresce),
por EAN, com histórico desde julho/2026 — não uma tabela de mercado comprada.
Somado ao custo real vindo da NF-e, permite responder "quanto eu cobro contra
quem vende ao meu lado", produto a produto.

## Operating Context

- O trabalho acontece em rodadas: cola-se uma lista de EANs, coleta-se nas
  farmácias, o motor precifica, o operador revisa e salva.
- Fonte da verdade migrando para Supabase (schema `precificacao`), com espelho
  local em CSV para funcionar sem internet. Coleta nunca pode parar por rede.
- Três aplicações sobre os mesmos dados: MiniPreço (desktop, precifica),
  Consulta EAN (desktop, coleta), este dashboard (browser, lê e edita).
- Permissão por conta Google, definida em tabela: dois admins escrevem, cinco
  contas leem, quem não está na tabela não vê nada.

## Capabilities and Constraints

- **Três preços distintos, nunca o mesmo número:** `preco_motor` (só o motor
  escreve), `preco_manual` (só o humano), `meu_preco` (o que a farmácia cobra).
- Chave canônica `gtin13`, preenchida com zeros à esquerda. GTIN-14 com
  indicador 1–8 é CAIXA e nunca se funde com a unidade.
- Vocabulário do produto, usado nas telas: piso, alvo, teto CMED, curva ABC,
  âncora PMC, preço cortesia, preço que cobrimos, faixa de balcão, Brick.
- Histórico de observações das farmácias: 81 mil linhas, 3.238 EANs, desde
  julho/2026. O Brick é referência de mercado com carga mensal: o valor vale o mês inteiro
  e salta na virada, então o banco guarda um retrato datado por carga em vez de
  sobrescrever o anterior.
- **Não decidido:** se o balcão ganha uma tela própria de produto único.

## Brand Commitments

Identidade herdada do MiniPreço, já implementada e com contraste verificado:
teal `#00B4AC` / `#00706D`, laranja `#F26F20` / `#C2410C` como segunda cor,
fundo `#F3F8F8`, texto `#123B42`. Referência estrutural apontada pelo usuário:
o painel de mercado do NAPP (tabela densa, cabeçalho sólido colorido, variação
percentual com sinal e cor).

## Evidence on Hand

- `C:\Users\docze\ConsultaPrecosEAN\precos_historico.csv` — 81.385 observações
  reais das farmácias concorrentes.
- `minipreco.py:586-700` — o painel lateral direito, que o usuário nomeou como
  o conteúdo principal do dashboard.
- `design-qa-implementation.png` — captura do app real.
- **Não fabricar:** preço, custo, margem ou EAN reais em qualquer arquivo sob
  `C:\Claude`, que tem origin público. Mockups usam dados sintéticos rotulados.

## Product Principles

1. **Três preços, três colunas.** Sugerido, manual e praticado nunca dividem o
   mesmo campo — foi assim que o número do motor se perdeu por meses.
2. **O dado do dia primeiro.** A coleta das farmácias vem antes da base de
   cálculo: é o que muda e o que o operador abre a tela para ver.
3. **Nunca parar por rede.** Toda tela assume que o dado pode estar do espelho
   local e diz isso, em vez de travar.
4. **Nada aparece sem procedência.** Todo número mostra de onde veio e quando
   foi visto; "sem dado" é um estado legítimo, não um zero.

## Accessibility & Inclusion

Contraste já tratado como requisito no app existente (razões anotadas no
código: 5.93:1, 5.18:1, 10.98:1). Manter ≥4.5:1 em texto de corpo. O balcão lê
a tela de pé, a alguma distância: números de decisão não podem ser pequenos.
