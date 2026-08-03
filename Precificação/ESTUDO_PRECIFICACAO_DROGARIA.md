# Estudo de precificação por categoria — drogaria física em Maringá/PR

Data do estudo: 25/07/2026  
Escopo: taxonomia de `GRUPOS E SUBGRUPOS.xlsx`, excluindo marca própria.

## 1. Recomendação executiva

Use três referências, nesta ordem:

1. **Piso absoluto de sobrevivência:** markup de **35,1% sobre o custo**, equivalente a **26,0% de margem bruta**. Abaixo disso, com as premissas atuais, a venda não paga cartão, Simples e despesas fixas.
2. **Alvo econômico da categoria:** definido na matriz `POLITICA_MARKUP_POR_CATEGORIA.csv`.
3. **Preço de mercado físico estimado:** mediana dos preços web comparáveis multiplicada pelo fator físico da categoria.

Não aplique um adicional físico único. O custo fixo de 17,5% já representa a operação da loja; somar 10% ou 15% a todos os preços web contaria a estrutura duas vezes. O fator físico recomendado varia de **1,00 a 1,10** conforme transparência de preço, urgência, conveniência e possibilidade de comparação.

### Fórmulas

Premissas mantidas do modelo vigente:

- cartão: 2,50%;
- Simples: 5,98% — estimativa que precisa de validação contábil;
- despesas fixas: 17,50%;
- lucro líquido alvo: varia por categoria.

Preço econômico:

`Preço = Custo / (1 - 0,025 - 0,0598 - 0,175 - lucro líquido alvo)`

Conversões:

`Markup % = (Preço / Custo - 1) × 100`

`Margem bruta % = (Preço - Custo) / Preço × 100`

Exemplos:

| Lucro líquido alvo | Markup sobre custo | Margem bruta |
|---:|---:|---:|
| 0% | 35,1% | 26,0% |
| 5% | 44,9% | 31,0% |
| 10% | 56,2% | 36,0% |
| 15% | 69,4% | 41,0% |
| 20% | 85,1% | 46,0% |
| 25% | 104,0% | 51,0% |
| 28% | 117,3% | 54,0% |

## 2. Leitura do seu caso

O relatório de entradas já processado, sem marca própria, contém:

- 1.825 linhas de compra;
- 1.728 EANs distintos;
- R$ 95.896,32 de custo total adquirido;
- 49,2% do capital comprado em `PERFUMARIA`;
- 24,9% em `LIBERADO`;
- 11,5% em `GENÉRICO`;
- 8,7% em `SIMILAR`;
- 5,7% em `REFERÊNCIA`.

Isso reforça uma política de **medicamentos, fraldas e leites como preço-imagem**, enquanto `PERFUMARIA`, `VAREJO` e itens exclusivos não próprios precisam carregar mais resultado. Como ainda não há histórico próprio de venda e giro, os percentuais são metas iniciais, não prova de rentabilidade realizada.

O relatório de compras ainda usa a classificação antiga (`LIBERADO`, `REFERÊNCIA` etc.). A política nova só deve ser aplicada depois do de-para por EAN para os rótulos do anexo.

## 3. Estratégia por macrogrupo

| Macrogrupo | Papel | Markup típico | Margem bruta típica | Ajuste físico sobre web |
|---|---|---:|---:|---:|
| `ETICOS` | preço-imagem e recorrência | 44,9% a 56,2% | 31,0% a 36,0% | 0% a 3% |
| `GENERICO` | equilíbrio entre competitividade e margem | 56,2% a 78,5% | 36,0% a 44,0% | 0% a 5% |
| `SIMILAR` | margem moderada com comparação por EAN | 56,2% a 78,5% | 36,0% a 44,0% | 0% a 5% |
| `PERFUMARIA` | principal financiador de margem | 56,2% a 92,2% | 36,0% a 48,0% | 0% a 8% |
| `VAREJO` | conveniência e compra por impulso | 44,9% a 117,3% | 31,0% a 54,0% | 0% a 10% |
| `EXCLUSIVOS` não próprios | proteção de margem | 104,0% a 117,3% | 51,0% a 54,0% | 8% a 10% |

Use o rótulo-pai somente como padrão de segurança. Havendo subgrupo, o subgrupo sempre prevalece.

## 4. Como transformar preços web em referência de loja física

Para cada EAN:

1. Separe preço web regular de preço de clube, app, assinatura, leve-mais-pague-menos e promoção.
2. Use somente apresentações idênticas e preços comparáveis.
3. Calcule a mediana web válida.
4. Calcule `Mediana física estimada = mediana web × fator físico`.
5. Para tier `PRECO_IMAGEM` ou `PADRAO`, use `mediana física estimada × 0,99`.
6. Para `PROTECAO_MARGEM`, use o preço econômico da categoria; se houver concorrência válida, limite-o a `mediana física estimada × 1,15`.
7. Nunca baixe do piso absoluto. Se o mercado exigir preço menor, marque revisão humana e decida conscientemente entre isca, renegociação ou não trabalhar o item.

O fator físico é **provisório**. Depois de 30 a 60 dias, substitua-o pela diferença observada entre os mesmos EANs em lojas físicas de Maringá e os preços web coletados no mesmo dia.

## 5. Onde ser agressivo e onde proteger margem

### Preço-imagem

- anticoncepcionais;
- uso contínuo;
- MIP/OTC muito conhecido;
- fraldas;
- leites;
- medicamentos de alto custo;
- itens Curva A ou com quatro ou mais concorrentes e baixa dispersão.

Esses itens podem trabalhar com lucro líquido alvo de 3% a 10%, mas nunca abaixo do piso absoluto sem decisão humana explícita.

### Proteção de margem

- maquiagem;
- acessórios;
- conveniências;
- bomboniere;
- varejinho;
- exclusivos não próprios;
- itens Curva C, sem concorrência válida ou com baixa comparabilidade.

Esses itens devem buscar lucro líquido de 20% a 28%, respeitando giro, validade e preço percebido.

## 6. Travas indispensáveis

- Medicamentos: conferir PMC CMED vigente por EAN, apresentação e ICMS aplicável ao Paraná.
- Controlados, fracionados, alto custo e judiciais: revisão humana obrigatória.
- Dois ou mais concorrentes abaixo do custo, todos abaixo do custo ou custo incompatível com embalagem: bloquear.
- Preço promocional não é preço regular.
- EAN de marca própria: excluir antes de qualquer regra, mesmo se estiver em outro grupo.
- `EXCLUSIVOS` não significa automaticamente marca própria. Aplicar a política apenas aos exclusivos que não estejam na lista de EANs próprios.
- A grade local continua `,49`, `,79`, `,90`, `,95`, `,99`, escolhendo a terminação mais próxima que respeite piso e teto.

## 7. Problemas encontrados na taxonomia recebida

A planilha tem 50 linhas, não 48. As linhas 18 e 19 repetem:

- `GENERICO`
- `GENERICO > ANTICONCEPCIONAL`

Logo depois aparecem subgrupos `SIMILAR`, mas não existe a linha-pai `SIMILAR` nem `SIMILAR > ANTICONCEPCIONAL`. Isso parece erro de cadastro, porém não deve ser corrigido por suposição. As duas linhas duplicadas ficaram bloqueadas na matriz com status `CORRIGIR_TAXONOMIA`.

## 8. Decisões humanas pendentes

1. Confirmar com o contador se o Simples efetivo é 5,98%.
2. Confirmar se os 17,5% de despesas fixas são percentuais sobre faturamento e incluem perdas, vencimento e quebra.
3. Corrigir ou confirmar as linhas 18 e 19 da taxonomia.
4. Informar a lista de EANs de marca própria para exclusão segura.
5. Após o primeiro mês, recalcular fatores físicos e alvos usando venda, giro, ruptura e estoque real.

## Fontes externas consultadas

- [CMED — Resolução nº 4, de 30 de março de 2026](https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/legislacao/RESOLUOCMCMEDN.4DE30DEMARODE2026DOU.pdf)
- [Anvisa — resoluções vigentes da CMED](https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/legislacao/resolucoes)
- [Sebrae — formação de preço e markup](https://blog.rn.sebrae.com.br/precificar-produto-2026/)
- [Procon-SP — preços de medicamentos e políticas distintas por canal](https://www.procon.sp.gov.br/wp-content/uploads/files/RTMedicamentos0310.pdf)
- [Abrafarma — participação atual do canal digital](https://www.abrafarma.com.br/noticias/e-commerce-de-medicamentos-se-consolida-no-brasil-com-movimentacao-recorde)

