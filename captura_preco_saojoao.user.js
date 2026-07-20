// ==UserScript==
// @name         Captura de Preço - Farmácias São João (Assistente EAN)
// @namespace    consulta-precos-drogaraia
// @version      2.8
// @downloadURL  https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_saojoao.user.js
// @updateURL    https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_saojoao.user.js
// @description  Consulta o EAN na API pública do site da São João (VTEX) e copia o preço para a área de transferência. Não precisa navegar até o produto.
// @match        https://www.saojoaofarmacias.com.br/*
// @grant        GM_setClipboard
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SITE = 'saojoao';

    // ------------------------------------------------------------------
    // PREPARO DA PÁGINA: aceitar cookies e informar o CEP sozinho.
    // Genérico de propósito (procura por texto/atributo, não por seletor
    // fixo) para sobreviver a mudanças de layout dos 4 sites.
    // ------------------------------------------------------------------
    const CEP_ROBO = '87010-055';

    function _txt(el) { return (el.innerText || el.textContent || '').trim(); }

    function aceitarCookies() {
        const re = /^(aceitar|permitir todos|aceito|concordo|entendi|ok,? entendi|prosseguir)/i;
        for (const b of document.querySelectorAll('button, a[role="button"], [role="button"]')) {
            if (b.offsetParent === null) continue;
            const t = _txt(b);
            if (t && t.length <= 45 && re.test(t)) { b.click(); return true; }
        }
        return false;
    }

    function preencherCep() {
        const alvo = [...document.querySelectorAll('input')].find((i) => {
            if (i.offsetParent === null || i.disabled || i.readOnly) return false;
            const a = ((i.placeholder || '') + ' ' + (i.name || '') + ' ' + (i.id || '') + ' '
                + (i.className || '') + ' ' + (i.getAttribute('aria-label') || '')).toLowerCase();
            return /cep|postal/.test(a);
        });
        if (!alvo) return false;
        if ((alvo.value || '').replace(/\D/g, '').length >= 8) return false; // já preenchido
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(alvo, CEP_ROBO);
        alvo.dispatchEvent(new Event('input', { bubbles: true }));
        alvo.dispatchEvent(new Event('change', { bubbles: true }));
        setTimeout(() => {
            const reBt = /inserir|confirmar|buscar|aplicar|salvar|continuar|ok/i;
            let no = alvo;
            for (let i = 0; i < 6 && no.parentElement; i++) {
                no = no.parentElement;
                const bt = [...no.querySelectorAll('button')].find(
                    (b) => b.offsetParent !== null && reBt.test(_txt(b)));
                if (bt) { bt.click(); return; }
            }
            alvo.dispatchEvent(new KeyboardEvent('keydown',
                { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            const form = alvo.closest('form');
            if (form) { try { form.requestSubmit ? form.requestSubmit() : form.submit(); } catch (e) { } }
        }, 300);
        console.log('[assistente-ean] CEP preenchido automaticamente:', CEP_ROBO);
        return true;
    }

    let _tentativasPreparo = 0;
    (function prepararPagina() {
        try { aceitarCookies(); preencherCep(); } catch (e) { }
        if (++_tentativasPreparo < 12) setTimeout(prepararPagina, 900);
    })();
    // Conferencia manual (botao direito no assistente): a URL vem com este
    // marcador para o script NAO agir - sem ele, a aba capturava o preco e
    // fechava sozinha na cara do usuario.
    if (/assistente_ignorar/.test(location.hash || '')) return;


    // O site da São João roda em VTEX, que expõe uma API pública de catálogo.
    // Uma única requisição devolve nome, preço, preço "de", disponibilidade e
    // promoções (Teasers) — sem precisar abrir a página do produto.
    // A URL aberta pelo assistente é a busca normal do site, com o EAN no
    // fragmento (#assistente_ean=<ean>) E no parâmetro _q. Lemos dos dois:
    // sites VTEX às vezes reescrevem a URL no carregamento e derrubam o
    // fragmento — o _q sobrevive. Sem nenhum dos dois, o script não faz nada.
    const EAN_DO_FRAGMENTO = (() => {
        const m = (location.hash || '').match(/assistente_ean=(\d{8,14})/);
        if (m) return m[1];
        const q = (new URLSearchParams(location.search).get('_q') || '').trim();
        if (/^\d{8,14}$/.test(q)) return q;
        return '';
    })();

    // Pagina onde o preco foi encontrado: vai no protocolo (URL=) para o
    // assistente abrir DIRETO na conferencia manual (botao direito).
    let URL_DO_RESULTADO = '';

    // "Principio Ativo": a Sao Joao e o site que mais expoe isso de forma
    // limpa (secao "Especificacoes" da pagina do produto), mas a busca
    // PRINCIPAL aqui e via API (sem renderizar a pagina) - so a camada 3 de
    // fallback (buscarNoDomDaPagina/produtoDaPaginaDoLink) baixa HTML de
    // verdade, de onde extraimos isso (ver extrairProdutoDeHtml). Fora dessa
    // camada, fica vazio (campo OPCIONAL, nunca bloqueia).
    let PRINCIPIO_ATIVO_PAGINA = '';
    function principioAtivoDoHtml(html) {
        const texto = (html || '').replace(/<[^>]+>/g, '\n');
        const m = texto.match(/Princ[ií]pio Ativo:?\s*\n+\s*([^\n]{2,60})/i);
        return m ? m[1].trim() : '';
    }

    function montarSentinel(ean, status, preco, estoque, obs, nome) {
        const limpar = (t) => (t || '').replace(/[;=\n\r]/g, ' ').replace(/\s+/g, ' ').trim();
        return `EAN=${ean};SITE=${SITE};STATUS=${status};PRECO=${preco || ''};ESTOQUE=${estoque || ''};OBS=${limpar(obs)};NOME=${limpar(nome)};URL=${(URL_DO_RESULTADO || '').replace(/[;\s]/g, '')};PRINCIPIO=${limpar(PRINCIPIO_ATIVO_PAGINA)}`;
    }

    function encerrarAba() {
        setTimeout(() => {
            try { window.close(); } catch (e) { /* ignorado */ }
        }, 800);
    }

    function formatarBR(valor) {
        const n = parseFloat(valor);
        if (isNaN(n)) return 'R$ ' + valor;
        return 'R$ ' + n.toFixed(2).replace('.', ',');
    }

    const semZeros = (t) => (t || '').replace(/^0+/, '');

    // A São João guarda o EAN EXATAMENTE como cadastrado (com zeros à
    // esquerda, ao contrário de Raia/Nissei). Tentamos as variações mais
    // prováveis, em ordem, até uma responder.
    function variacoesDoEan(ean) {
        const v = [ean, semZeros(ean), ean.padStart(13, '0'), ean.padStart(14, '0')];
        return [...new Set(v.filter(x => x && x.length >= 8))];
    }

    function buscarNaApi(termo) {
        return fetch('/api/catalog_system/pub/products/search?fq=alternateIds_Ean:' + encodeURIComponent(termo))
            .then(r => (r.ok ? r.json() : []))
            .catch(() => []);
    }

    // A São João é VTEX com REGIONALIZAÇÃO: parte do catálogo (ex.: genéricos
    // EMS) só aparece com a loja/região da sessão. A API antiga ignora isso e
    // responde vazio (caso real: EAN 7896004726533 em 07/2026 — a página do
    // site achava, a API não). O cookie vtex_segment guarda a região.
    function lerSegmento() {
        try {
            const m = document.cookie.match(/vtex_segment=([^;]+)/);
            if (!m) return {};
            return JSON.parse(atob(decodeURIComponent(m[1]))) || {};
        } catch (e) { return {}; }
    }

    function buscarInteligente(consulta) {
        const seg = lerSegmento();
        let url = '/api/io/_v/api/intelligent-search/product_search/?query=' + encodeURIComponent(consulta);
        if (seg.regionId) url += '&regionId=' + encodeURIComponent(seg.regionId);
        if (seg.channel) url += '&salesChannel=' + encodeURIComponent(seg.channel);
        return fetch(url)
            .then(r => (r.ok ? r.json() : {}))
            .then(j => (j && j.products) || [])
            .catch(() => []);
    }

    // Última camada: a PÁGINA de busca aberta pelo assistente (que roda com a
    // sessão completa e comprovadamente acha o produto). Pega o link do
    // resultado e lê o JSON-LD da página do produto via fetch.
    function extrairProdutoDeHtml(html) {
        const blocos = html.match(/<script[^>]*application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi) || [];
        for (const b of blocos) {
            const texto = b.replace(/^<script[^>]*>/i, '').replace(/<\/script>$/i, '');
            if (!/"@type"\s*:\s*"Product"/.test(texto)) continue;
            let dado = null;
            try { dado = JSON.parse(texto); } catch (e) { }
            const pega = (re) => { const m = texto.match(re); return m ? m[1] : ''; };
            const nome = (dado && dado.name) || pega(/"name"\s*:\s*"([^"]*)"/);
            const preco = (dado && dado.offers && (dado.offers.price || (dado.offers[0] || {}).price))
                || pega(/"price"\s*:\s*"?([\d.]+)"?/);
            const gtin = (dado && (dado.gtin13 || dado.gtin)) || pega(/"gtin1?[34]?"\s*:\s*"?(\d+)"?/);
            const disp = (dado && dado.offers && dado.offers.availability) || pega(/"availability"\s*:\s*"([^"]*)"/);
            if (!preco) return null;
            return {
                productName: nome,
                principioAtivo: principioAtivoDoHtml(html),
                items: [{
                    ean: gtin,
                    sellers: [{ commertialOffer: { Price: parseFloat(preco), ListPrice: 0, IsAvailable: /InStock/i.test(disp || '') } }],
                }],
            };
        }
        return null;
    }

    function linksDeResultado() {
        return [...document.querySelectorAll('a[href$="/p"], a[href*="/p?"]')]
            .filter(a => (a.innerText || '').trim())
            .map(a => {
                const cont = a.closest('article, li, div');
                return { url: a.href.split('#')[0], texto: ((cont ? cont.innerText : '') || a.innerText || '') };
            });
    }

    function buscarNoDomDaPagina(tentativa) {
        return new Promise((resolve) => {
            const tentar = (n) => {
                const links = linksDeResultado();
                if (links.length) { resolve(links); return; }
                const semResultado = /não encontr|nenhum result|0\s*resultado/i.test(document.body.innerText);
                if (semResultado || n <= 0) { resolve([]); return; }
                setTimeout(() => tentar(n - 1), 600);
            };
            tentar(tentativa || 15);
        });
    }

    async function produtoDaPaginaDoLink(url) {
        try {
            const html = await fetch(url).then(r => (r.ok ? r.text() : ''));
            return html ? extrairProdutoDeHtml(html) : null;
        } catch (e) { return null; }
    }

    // Busca por NOME (retaguarda): o assistente manda o nome esperado no
    // fragmento quando o EAN não foi encontrado e outra farmácia já
    // identificou o produto.
    const NOME_ESPERADO = (() => {
        const m = (location.hash || '').match(/assistente_nome=([^&]+)/);
        if (!m) return '';
        try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    })();

    const LIMIAR_NOME = 0.6;

    function tokensDoNome(t) {
        const irrelevantes = new Set(['de', 'da', 'do', 'para', 'com', 'em', 'un', 'und',
            'unidade', 'unidades', 'x', 'c', 'e', 'o', 'a', 'kit', 'generico', 'generica', 'revestido', 'revestidos', 'leve', 'pague', 'cada', 'gratis']);
        return new Set((t || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '')
            .replace(/[^a-z0-9 ]/g, ' ').split(/\s+/)
            .filter(w => w.length >= 2 && !irrelevantes.has(w)));
    }

    // Prefixos com 4+ letras valem ("shamp" ~ "shampoo", "cond" ~
    // "condicionador" — a Raia abrevia nomes). Denominador = tokens da
    // REFERÊNCIA: privilegia o candidato que contém tudo que ela pede
    // (o kit vence o shampoo avulso).
    // REGRA DA MARCA: o 1º token útil da referência (quase sempre a marca)
    // PRECISA existir no candidato — "Sintocalmy Passiflora 30 comprimidos"
    // não pode mais passar por "SonoZzz Passiflora 8 comprimidos" só porque
    // "passiflora comprimidos" coincide (erro real de 07/2026: outra marca,
    // outra quantidade, preço 2,5x maior).
    function similaridadeNomes(a, b) {
        const A = [...tokensDoNome(a)], B = [...tokensDoNome(b)];
        if (!A.length || !B.length) return 0;
        const bate = (w) => B.some(x => x === w || (w.length >= 4 && x.startsWith(w)) || (x.length >= 4 && w.startsWith(x)));
        if (!bate(A[0])) return 0;
        let comum = 0;
        for (const w of A) {
            if (bate(w)) comum++;
        }
        if (comum < 2) return 0;
        return comum / A.length;
    }

    // Quantidade de unidades embutida no nome ("4x2" = 8; "8 Unidades" = 8).
    // Distingue variações do mesmo produto (carga com 2, 4 ou 8 unidades),
    // que empatariam na semelhança de palavras.
    function unidadesDoNome(t) {
        const s = (t || '').toLowerCase();
        let m = s.match(/(\d+)\s*(?:un|und|unid\w*)?\s*x\s*(\d+)/);
        if (m) return parseInt(m[1], 10) * parseInt(m[2], 10);
        m = s.match(/(\d+)\s*(?:un|und|unid\w*|comprimidos?|c[aá]psulas?|refis|refil|cargas?|sach[eê]s?|envelopes?)/);
        if (m) return parseInt(m[1], 10);
        return null;
    }

    // MEDIDAS SÃO ELIMINATÓRIAS (peso/volume/dosagem): "25mg" vs "50mg" é
    // OUTRO produto, mesmo com o resto do nome idêntico (erro real de
    // 07/2026: Sildenafila 50mg aceito no lugar do 25mg, preço pela metade).
    // Regra: quando os DOIS nomes declaram a mesma unidade, pelo menos um
    // valor precisa coincidir; unidade declarada só de um lado não elimina
    // (kit vs avulso continua tolerado).
    // Cobre: mcg/mg/g/gr/gramas/kg (massa), ml/l (volume), UI e mEq (potencia
    // de principio ativo - ex.: Litio em mEq), % (concentracao, ex.:
    // Minoxidil 5%) e h (duracao de liberacao/protecao, ex.: "XR 24h",
    // desodorante 72h). (?![a-z0-9]) evita match parcial ("gr" nao virar so
    // "g" com sobra) e cobre "%" no fim (\b nao funciona depois de simbolo).
    function medidasDoNome(t) {
        const s = (t || '').toLowerCase().replace(/,/g, '.');
        const re = /(\d+(?:\.\d+)?)\s*(mcg|mg|gramas?|gr|g|kg|ml|l|meq|ui|mts|h|%)(?![a-z0-9])/g;
        const medidas = {};
        let m;
        while ((m = re.exec(s)) !== null) {
            let valor = parseFloat(m[1]), unidade = m[2];
            if (unidade === 'g' || unidade === 'gr' || unidade === 'gramas' || unidade === 'grama') { valor *= 1000; unidade = 'mg'; }
            if (unidade === 'kg') { valor *= 1000000; unidade = 'mg'; }
            if (unidade === 'l') { valor *= 1000; unidade = 'ml'; }
            if (!medidas[unidade]) medidas[unidade] = [];
            medidas[unidade].push(valor);
        }
        return medidas;
    }

    const UNIDADES_EMBALAGEM = new Set(['ml', 'l']); // volume: kit x avulso tolerado

    function medidasConflitam(a, b) {
        const A = medidasDoNome(a), B = medidasDoNome(b);
        for (const unidade in A) {
            const va = A[unidade], vb = B[unidade];
            if (!vb) continue;
            if (UNIDADES_EMBALAGEM.has(unidade)) {
                // Volume (ml/l): contagem diferente e kit x avulso (embalagem),
                // tolerado - so compara quando a CONTAGEM bate. Exige conjuntos
                // IDENTICOS quando bate, nao so 1 valor em comum - senao
                // "10+40" passava como igual a "10+20" (bug real de 07/2026:
                // Ezetimiba 10mg + Sinvastatina 40mg x 20mg).
                if (va.length === vb.length) {
                    const sa = [...va].sort((x, y) => x - y).join(',');
                    const sb = [...vb].sort((x, y) => x - y).join(',');
                    if (sa !== sb) return true;
                }
            } else {
                // Dosagem de principio ativo (mg/mcg/UI): remedio COMBINADO x
                // ISOLADO tem que ser rejeitado mesmo com contagem diferente -
                // "Olmesartana 40mg" sozinho NAO e "Olmesartana 40mg +
                // Anlodipino 10mg" (bug real de 07/2026: um site pegou so o
                // principio ativo isolado no lugar da combinacao). Exige o
                // CONJUNTO exato dos dois lados.
                const sa = [...new Set(va)].sort((x, y) => x - y).join(',');
                const sb = [...new Set(vb)].sort((x, y) => x - y).join(',');
                if (sa !== sb) return true;
            }
        }
        return false;
    }

    // QUANTIDADE DE FORMA FARMACEUTICA e ELIMINATORIA: "14 comprimidos" e um
    // produto diferente de "28 comprimidos" (outro EAN, outro preco) — erro
    // real de 07/2026: aceitaram 28 cp no lugar de 14 cp (R$ 312 vs R$ 90).
    // Difere de EMBALAGEM (kit/un/refil), que continua tolerada e conciliada.
    function doseDoNome(t) {
        const s = (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        const formas = '(?:comprimidos?|comprs?|comp|cpr|cps|cp|capsulas?|caps|drageas?|'
            + 'saches?|envelopes?|ampolas?|flaconetes?|pastilhas?|ovulos?|supositorios?|adesivos?|'
            + 'doses?|gomas?)';
        let m = s.match(new RegExp('(\d{1,4})\s*' + formas + '\b'));
        if (m) return parseInt(m[1], 10);
        m = s.match(new RegExp('\bc\s*/\s*(\d{1,4})\s*' + formas + '?\b'));
        if (m) return parseInt(m[1], 10);
        return null;
    }

    function notaComUnidades(esperado, candidato) {
        let nota = similaridadeNomes(esperado, candidato);
        if (!nota) return 0;
        if (medidasConflitam(esperado, candidato)) return 0;
        // quantidade de comprimidos/capsulas diferente = OUTRO produto
        const de = doseDoNome(esperado), dc = doseDoNome(candidato);
        if (de !== null && dc !== null && de !== dc) return 0;
        const ue = unidadesDoNome(esperado), uc = unidadesDoNome(candidato);
        // Quantidade igual ganha bônus; quantidade declarada e DIFERENTE pesa
        // CONTRA (8 vs 30 comprimidos raramente é o mesmo produto). Um kit
        // legítimo do mesmo item ainda passa: o resto do nome bate quase 100%
        // (≈1,0 − 0,2 = 0,8 ≥ limiar). Quando um dos lados não declara
        // quantidade, nada muda (kit vs avulso continua aceito e conciliado).
        if (ue !== null && uc !== null) {
            nota += (ue === uc) ? 0.2 : -0.2;
        }
        return Math.max(0, Math.min(1, nota));
    }

    // Embalagem diferente da referência (kit de N vs unidade): aceita, mas
    // avisa e calcula o preço por unidade para conciliar com as demais.
    function obsEmbalagem(precoStr, nomeSite) {
        const ue = unidadesDoNome(NOME_ESPERADO);
        const uc = unidadesDoNome(nomeSite);
        const p = parseFloat(precoStr);
        if (uc && uc > 1 && uc !== (ue || 1) && !isNaN(p)) {
            const porUn = (p / uc).toFixed(2).replace('.', ',');
            return ` / ATENÇÃO: embalagem com ${uc} un (referência: ${ue || 1} un) / ≈ R$ ${porUn} por unidade`;
        }
        if (ue && ue > 1 && uc === 1) {
            return ` / ATENÇÃO: site vende 1 un (referência: ${ue} un)`;
        }
        return '';
    }

    async function consultar() {
        const ean = EAN_DO_FRAGMENTO;
        // Sinal de vida: confirma ao assistente que o script está instalado e
        // rodou (o Python só loga, não grava).
        GM_setClipboard(`EAN=${ean};SITE=${SITE};STATUS=PING;PRECO=;ESTOQUE=;OBS=;NOME=`);

        if (NOME_ESPERADO) {
            await consultarPorNome(ean);
            return;
        }

        // Camada 1: API antiga por EAN (rápida, mas ignora o catálogo regional)
        let produto = null;
        for (const termo of variacoesDoEan(ean)) {
            const lista = await buscarNaApi(termo);
            if (lista && lista.length) { produto = lista[0]; break; }
        }

        // Nas camadas 2 e 3 a consulta é "textual": o resultado SÓ vale se o
        // EAN do produto bater com o buscado — sem isso, um produto de
        // vitrine/carrossel da página vira resposta (erro real de 07/2026:
        // lenços Huggies gravados como DIVERGENTE de um Sildenafila).
        const eanBate = (p) => (p && (p.items || []).some(
            (i) => semZeros((i.ean || '').toString()) === semZeros(ean)));

        // Camada 2: Intelligent Search com a região da sessão
        if (!produto) {
            for (const termo of variacoesDoEan(ean)) {
                const lista = await buscarInteligente(termo);
                const certo = (lista || []).find(eanBate);
                if (certo) {
                    produto = certo;
                    console.log('[assistente-ean] Sao Joao: achado pela Intelligent Search (regional)');
                    break;
                }
            }
        }

        // Camada 3: a própria página de busca aberta (sessão completa) —
        // testa até 3 links de resultado e exige EAN idêntico no JSON-LD.
        if (!produto) {
            const links = await buscarNoDomDaPagina(15);
            for (const l of links.slice(0, 3)) {
                const p = await produtoDaPaginaDoLink(l.url);
                if (eanBate(p)) {
                    p.urlPagina = l.url;
                    produto = p;
                    console.log('[assistente-ean] Sao Joao: achado pela PAGINA de busca (fallback DOM)');
                    break;
                }
            }
        }

        if (!produto) {
            GM_setClipboard(montarSentinel(ean, 'NAO_ENCONTRADO', '', '', '', ''));
            console.log('[assistente-ean] Sao Joao: nao encontrado:', ean);
            encerrarAba();
            return;
        }
        emitirDeProduto(produto, ean, false);
    }

    // Termo enxuto para a busca textual: nomes completos com "175ml +" etc.
    // devolvem ZERO resultados na API (testado ao vivo em 07/2026). A escolha
    // fina fica com a pontuação de semelhança, que usa o nome completo.
    function termoCurto(nome) {
        const medidas = /^\d+([.,]\d+)?(ml|l|g|mg|kg|un|und|cp|cpr|comp\w*)?$|^x\d+$|^\d+x\d+$/;
        const ignorar = new Set(['de', 'da', 'do', 'para', 'com', 'e', 'em']);
        const tokens = (nome || '').toLowerCase().match(/[a-zà-ÿ0-9\-]+/g) || [];
        const uteis = tokens.filter(t => t.length >= 2 && !ignorar.has(t) && !medidas.test(t));
        return uteis.slice(0, 4).join(' ') || (nome || '').slice(0, 30);
    }

    // Busca por nome: API antiga -> Intelligent Search regional -> resultados
    // renderizados na própria página. Aceita só acima do limiar.
    async function consultarPorNome(ean) {
        const termo = termoCurto(NOME_ESPERADO);
        let lista = await fetch('/api/catalog_system/pub/products/search?ft=' + encodeURIComponent(termo) + '&_from=0&_to=20')
            .then(r => (r.ok ? r.json() : []))
            .catch(() => []);
        if (!lista || !lista.length) {
            lista = await buscarInteligente(termo);
        }
        let melhor = null, melhorNota = 0;
        for (const p of (lista || [])) {
            const nota = notaComUnidades(NOME_ESPERADO, p.productName || '');
            if (nota > melhorNota) { melhorNota = nota; melhor = p; }
        }
        if (melhor && melhorNota >= LIMIAR_NOME) {
            console.log('[assistente-ean] Sao Joao: candidato por nome aceito (nota', melhorNota.toFixed(2), ')');
            emitirDeProduto(melhor, ean, true);
            return;
        }
        // Fallback: o que a PÁGINA de busca mostrou (catálogo regional completo)
        const links = await buscarNoDomDaPagina(15);
        let melhorLink = null; let notaLink = 0;
        for (const c of links) {
            const nota = notaComUnidades(NOME_ESPERADO, c.texto);
            if (nota > notaLink) { notaLink = nota; melhorLink = c; }
        }
        if (melhorLink && notaLink >= LIMIAR_NOME) {
            const produto = await produtoDaPaginaDoLink(melhorLink.url);
            if (produto) {
                produto.urlPagina = melhorLink.url;
                console.log('[assistente-ean] Sao Joao: candidato por nome via PAGINA (nota', notaLink.toFixed(2), ')');
                emitirDeProduto(produto, ean, true);
                return;
            }
        }
        console.log('[assistente-ean] Sao Joao: nenhum candidato por nome (melhor:',
            Math.max(melhorNota, notaLink).toFixed(2), ')');
        GM_setClipboard(montarSentinel(ean, 'NAO_ENCONTRADO', '', '', '', ''));
        encerrarAba();
    }

    function emitirDeProduto(produto, ean, porNome) {
        // Página do produto para a conferência manual (🌐 abre direto nela).
        URL_DO_RESULTADO = produto.urlPagina
            || (produto.linkText ? (location.origin + '/' + produto.linkText + '/p') : '');
        PRINCIPIO_ATIVO_PAGINA = produto.principioAtivo || '';
        // Prefere o item cujo EAN bate com o buscado (produtos podem ter
        // múltiplas variações/itens).
        const itens = produto.items || [];
        let item = itens.find(i => semZeros(i.ean) === semZeros(ean)) || itens[0];
        if (!item || !item.sellers || !item.sellers.length) {
            GM_setClipboard(montarSentinel(ean, 'NAO_ENCONTRADO', '', '', '', ''));
            encerrarAba();
            return;
        }

        const oferta = item.sellers[0].commertialOffer || {};
        const nome = produto.productName || '';
        const precoAtual = oferta.Price || 0;
        const precoDe = oferta.ListPrice || 0;
        const estoque = oferta.IsAvailable ? 'EM_ESTOQUE' : 'SEM_ESTOQUE';

        // Promoções:
        //  - desconto simples: ListPrice > Price ("de X por Y"; Price já é o promocional);
        //  - leve mais pague menos: vem nos Teasers, ex.
        //    "NOVALGINA 1G 10CP OPELLA LEVE 2 POR R$ 17,99 CADA |...| QTD 2 ..."
        //    e o Price segue sendo o preço de 1 unidade.
        const partes = [];
        if (precoDe > precoAtual + 0.009) {
            partes.push(`de ${formatarBR(precoDe)} por ${formatarBR(precoAtual)}`);
        }
        const teasers = [...(oferta.Teasers || []), ...(oferta.PromotionTeasers || [])];
        for (const t of teasers) {
            const nomeTeaser = (t && (t.Name || t['<Name>k__BackingField'])) || '';
            const m = nomeTeaser.match(/leve\s*(\d+)\s*por\s*R\$\s*([\d.,]+)\s*cada/i);
            if (m) {
                partes.push(`leve ${m[1]} por R$ ${m[2]} cada (preço de 1 unidade: ${formatarBR(precoAtual)})`);
                break; // teasers costumam vir duplicados
            }
        }
        const obs = partes.length ? 'Promoção: ' + partes.join(' / ') : '';

        const preco = precoAtual > 0 ? String(precoAtual) : '';
        const gtinItem = (item.ean || '').toString().trim();

        // Produto cadastrado mas sem preço/estoque: registra como INDISPONIVEL.
        if (!preco) {
            GM_setClipboard(montarSentinel(ean, 'INDISPONIVEL', '', 'SEM_ESTOQUE', '', nome));
            console.log('[assistente-ean] Sao Joao: preco INDISPONIVEL para', ean);
            encerrarAba();
            return;
        }

        if (porNome) {
            // Produto aceito pela SEMELHANÇA DE NOME (o EAN não bateu na busca).
            const obsNome = `Achado por NOME (EAN do site: ${gtinItem || '-'})` + obsEmbalagem(preco, nome) + (obs ? ' / ' + obs : '');
            GM_setClipboard(montarSentinel(ean, 'POR_NOME', preco, estoque, obsNome, nome));
            console.log('[assistente-ean] Sao Joao: preco POR NOME:', preco, 'EAN do site:', gtinItem);
        } else if (gtinItem && semZeros(gtinItem) !== semZeros(ean)) {
            GM_setClipboard(montarSentinel(ean, 'DIVERGENTE', preco, estoque, obs, `${nome} (ean real: ${gtinItem})`));
            console.log('[assistente-ean] Sao Joao: EAN divergente. Buscado:', ean, 'API:', gtinItem);
        } else {
            GM_setClipboard(montarSentinel(ean, 'OK', preco, estoque, obs, nome));
            console.log('[assistente-ean] Sao Joao: preco copiado:', preco, 'Obs:', obs || '(sem promo)');
        }

        encerrarAba();
    }

    console.log('[assistente-ean] Sao Joao v2.2 ativo em', location.pathname,
        EAN_DO_FRAGMENTO ? '(ean pendente: ' + EAN_DO_FRAGMENTO + ')' : '');

    if (EAN_DO_FRAGMENTO) {
        // Pequeno atraso só para a página assentar; a consulta em si é via API.
        // O .catch() é ESSENCIAL: sem ele, uma exceção dentro do async morre
        // calada (unhandled rejection) e o assistente só vê um timeout mudo.
        setTimeout(() => {
            try {
                const p = consultar();
                if (p && p.catch) {
                    p.catch((e) => {
                        console.error('[assistente-ean] Sao Joao: erro na consulta', e);
                        GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', 'erro interno do script', ''));
                        encerrarAba();
                    });
                }
            } catch (e) {
                console.error('[assistente-ean] Sao Joao: erro sincrono', e);
                GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', 'erro interno do script', ''));
                encerrarAba();
            }
        }, 800);
    }
})();
