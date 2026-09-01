// Prova o veredito da busca da Raia diante do Akamai Bot Manager (09/2026).
//
// Tres paginas chegam SEM card de produto e so' o texto as distingue:
//   1) intersticial do desafio  -> esperar (resolve sozinho e recarrega)
//   2) "Access Denied" do WAF   -> BLOQUEIO com motivo
//   3) "Nao encontramos"        -> NAO_ENCONTRADO (so' depois de 5 tentativas)
// Confundir (1) com (3) grava um "nao achou" falso; confundir (1) com nada
// deixa o script mudo ate o app dar timeout — foi o que aconteceu em 31/08.
//
//   node test_desafio_akamai.js
const fs = require('fs'), path = require('path'), assert = require('assert');

const src = fs.readFileSync(path.join(__dirname, 'captura_preco.user.js'), 'utf8')
    .split('\r\n').join('\n');
const i = src.indexOf('    function paginaDeBusca() {');
assert(i >= 0, 'paginaDeBusca nao encontrada');
const j = src.indexOf('\n    }\n', src.indexOf('setTimeout(paginaDeBusca, 500);\n    }', i));
const corpo = src.slice(i, j + 6);

function rodar(textoPagina, temCard) {
    const emitidos = [];
    let pendentes = 0;
    const doc = {
        body: { innerText: textoPagina },
        querySelector: (sel) => (temCard && sel.includes('article a[href]')
            ? { href: 'https://www.drogaraia.com.br/produto.html' }
            : (temCard && sel === '[data-testid="container-products"]' ? {} : null)),
    };
    const fn = new Function(
        'location', 'document', 'enviarPing', 'GM_setValue', 'sufixoFlags',
        'emitirResultado', 'montarSentinel', 'encerrarAba', 'setTimeout',
        'let tentativasBusca = 0, tentativasDesafio = 0;\n' + corpo + '\nreturn paginaDeBusca;'
    )(
        { search: '?w=789', href: '' }, doc, () => { }, () => { }, () => '',
        (s) => emitidos.push(s),
        (ean, status, p, e, obs) => `STATUS=${status};OBS=${obs}`,
        () => { }, () => { pendentes++; }
    );
    // Repolla ate' o veredito ou ate' 60 ciclos (30s de pagina), o que vier antes.
    for (let n = 0; n < 60 && !emitidos.length; n++) { const antes = pendentes; fn(); if (pendentes === antes) break; }
    return { emitidos, pendentes };
}

const DESAFIO = 'Powered and protected by\nPrivacy';
const NEGADO = "Access Denied\nYou don't have permission to access this server.";
const VAZIO = 'Busca\nNão encontramos resultados';

// 1) intersticial: nao pode emitir veredito de cara — tem que esperar.
let r = rodar(DESAFIO, false);
assert.strictEqual(r.emitidos.length, 1, 'desafio deveria emitir 1 veredito no fim, deu ' + r.emitidos.length);
assert(/STATUS=BLOQUEIO;OBS=desafio Akamai/.test(r.emitidos[0]), 'veredito errado: ' + r.emitidos[0]);
assert(r.pendentes >= 24, 'desafio deveria esperar >=24 ciclos (12s), esperou ' + r.pendentes);

// 2) Access Denied: BLOQUEIO imediato, com motivo (nao mais "sem detalhe").
r = rodar(NEGADO, false);
assert(/STATUS=BLOQUEIO;OBS=Access Denied/.test(r.emitidos[0]), 'access denied: ' + r.emitidos[0]);
assert.strictEqual(r.pendentes, 0, 'access denied nao pode ficar repollando');

// 3) sem resultado de verdade: continua NAO_ENCONTRADO.
r = rodar(VAZIO, false);
assert(/STATUS=NAO_ENCONTRADO/.test(r.emitidos[0]), 'sem resultado: ' + r.emitidos[0]);

// 4) card presente: navega pro produto, sem veredito na busca.
r = rodar(DESAFIO, true);
assert.strictEqual(r.emitidos.length, 0, 'com card nao se emite veredito na busca');

console.log('ok  4 casos da busca da Raia');
