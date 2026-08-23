/* Um check so', e no que da' para errar caro: ler o preco digitado.
   Roda com `node dashboard/teste_preco.js`. Le a funcao do proprio index.html
   -- copiar o codigo para ca' testaria a copia, nao o que vai para o ar. */
const fs = require('fs'), assert = require('assert'), path = require('path');
const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const fonte = html.match(/function precoDoTexto\(txt\)\{[\s\S]*?\n\}/);
assert.ok(fonte, 'precoDoTexto sumiu do index.html');
const precoDoTexto = new Function(fonte[0] + '; return precoDoTexto')();

const casos = [
  ['19,90', 19.9], ['19.90', 19.9], ['R$ 19,90', 19.9], [' 19,90 ', 19.9],
  ['1.234,50', 1234.5],          // ponto e' milhar quando existe virgula
  ['1234.50', 1234.5],           // ponto e' decimal quando nao existe
  ['19,904', 19.9], ['19,905', 19.91],
  ['', null], ['abc', null], ['0', null], ['-5', null], ['0,00', null]
];
for (const [entrada, esperado] of casos) {
  assert.strictEqual(precoDoTexto(entrada), esperado,
    `precoDoTexto(${JSON.stringify(entrada)}) deu ${precoDoTexto(entrada)}, esperado ${esperado}`);
}
console.log(`ok — ${casos.length} casos`);
