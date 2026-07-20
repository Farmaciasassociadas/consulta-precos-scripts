// ==UserScript==
// @name         Captura de Preço - Panvel (Assistente EAN)
// @namespace    consulta-precos-drogaraia
// @version      1.0
// @downloadURL  https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_panvel.user.js
// @updateURL    https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_panvel.user.js
// @description  Busca o EAN na Panvel, entra no produto, lê o preço via JSON-LD e copia para a área de transferência.
// @match        https://www.panvel.com/*
// @grant        GM_setClipboard
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SITE = 'panvel';

    // ------------------------------------------------------------------
    // PREPARO DA PÁGINA: aceitar cookies e informar o CEP sozinho.
    // Genérico de propósito (procura por texto/atributo, não por seletor
    // fixo) para sobreviver a mudanças de layout. Regex de cookies com
    // "eu concordo" a mais: é o texto exato do botão da Panvel (testado
    // ao vivo em 07/2026 — os outros 4 sites usam "aceitar"/"concordo"
    // sozinho, sem o "eu" na frente).
    // ------------------------------------------------------------------
    const CEP_ROBO = '87010-055';

    function _txt(el) { return (el.innerText || el.textContent || '').trim(); }

    function aceitarCookies() {
        const re = /^(aceitar|permitir todos|aceito|eu concordo|concordo|entendi|ok,? entendi|prosseguir)/i;
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


    // O EAN buscado viaja da página de busca para a do produto pelo FRAGMENTO
    // da URL (#assistente_ean=...): o GM_setValue grava de forma assíncrona e
    // pode se perder quando a navegação é imediata. O GM fica como reserva.
    const EAN_DO_FRAGMENTO = (() => {
        const m = (location.hash || '').match(/assistente_ean=(\d{8,14})/);
        return m ? m[1] : '';
    })();

    // Busca por NOME (retaguarda): o assistente manda o nome esperado no
    // fragmento quando o EAN não foi encontrado e outra farmácia já
    // identificou o produto.
    const NOME_ESPERADO = (() => {
        const m = (location.hash || '').match(/assistente_nome=([^&]+)/);
        if (!m) return '';
        try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    })();
    const MODO_POR_NOME = /assistente_por_nome=1/.test(location.hash || '');

    function pegarEanPendente() {
        return EAN_DO_FRAGMENTO || GM_getValue('ean_buscado', '');
    }

    // ---- semelhança de nomes (aceita o produto só acima do limiar) ----
    // Bloco IDÊNTICO ao dos outros 4 scripts (Raia/Nissei/São João/São
    // Paulo) — mesma lógica de coerência, só a raspagem da página muda
    // de site pra site.
    const LIMIAR_NOME = 0.6;

    function tokensDoNome(t) {
        const irrelevantes = new Set(['de', 'da', 'do', 'para', 'com', 'em', 'un', 'und',
            'unidade', 'unidades', 'x', 'c', 'e', 'o', 'a', 'kit', 'generico', 'generica', 'revestido', 'revestidos', 'leve', 'pague', 'cada', 'gratis']);
        return new Set((t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '')
            .replace(/[^a-z0-9 ]/g, ' ').split(/\s+/)
            .filter(w => w.length >= 2 && !irrelevantes.has(w)));
    }

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

    function unidadesDoNome(t) {
        const s = (t || '').toLowerCase();
        let m = s.match(/(\d+)\s*(?:un|und|unid\w*)?\s*x\s*(\d+)/);
        if (m) return parseInt(m[1], 10) * parseInt(m[2], 10);
        m = s.match(/(\d+)\s*(?:un|und|unid\w*|comprimidos?|c[aá]psulas?|refis|refil|cargas?|sach[eê]s?|envelopes?)/);
        if (m) return parseInt(m[1], 10);
        return null;
    }

    const RE_MILHAR = /(\d{1,3}(?:[.\s]\d{3})+)(?=\s*(?:mcg|mg|gramas?|gr|g|kg|ml|litros?|l|meq|ui|mts|metros?|h|%)(?![a-z0-9]))/g;

    function normalizarMilhares(s) {
        return s.replace(RE_MILHAR, (m) => m.replace(/[.\s]/g, ''));
    }

    function medidasDoNome(t) {
        const s = normalizarMilhares((t || '').toLowerCase()).replace(/,/g, '.');
        const re = /(\d+(?:\.\d+)?)\s*(mcg|mg|gramas?|gr|g|kg|ml|litros?|l|meq|ui|mts|metros?|h|%)(?![a-z0-9])/g;
        const medidas = {};
        let m;
        while ((m = re.exec(s)) !== null) {
            let valor = parseFloat(m[1]), unidade = m[2];
            if (unidade === 'gr' || unidade === 'gramas' || unidade === 'grama') { unidade = 'g'; }
            if (unidade === 'kg') { valor *= 1000; unidade = 'g'; }
            if (unidade === 'l' || unidade === 'litro' || unidade === 'litros') { valor *= 1000; unidade = 'ml'; }
            if (unidade === 'metro' || unidade === 'metros') { unidade = 'mts'; }
            if (!medidas[unidade]) medidas[unidade] = [];
            medidas[unidade].push(valor);
        }
        return medidas;
    }

    const UNIDADES_EMBALAGEM = new Set(['ml', 'l', 'g']);

    function medidasConflitam(a, b) {
        const A = medidasDoNome(a), B = medidasDoNome(b);
        for (const unidade in A) {
            const va = A[unidade], vb = B[unidade];
            if (!vb) continue;
            if (UNIDADES_EMBALAGEM.has(unidade)) {
                if (va.length === vb.length) {
                    const sa = [...va].sort((x, y) => x - y).join(',');
                    const sb = [...vb].sort((x, y) => x - y).join(',');
                    if (sa !== sb) return true;
                }
            } else {
                const sa = [...va].sort((x, y) => x - y).join(',');
                const sb = [...vb].sort((x, y) => x - y).join(',');
                if (sa !== sb) return true;
            }
        }
        return false;
    }

    function doseDoNome(t) {
        const s = (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        const formas = '(?:comprimidos?|comprs?|comp|cpr|cps|cp|capsulas?|caps|drageas?|'
            + 'saches?|envelopes?|ampolas?|flaconetes?|pastilhas?|ovulos?|supositorios?|adesivos?|'
            + 'doses?|gomas?)';
        let m = s.match(new RegExp('(\\d{1,4})\\s*' + formas + '\\b'));
        if (m) return parseInt(m[1], 10);
        m = s.match(new RegExp('\\bc\\s*/\\s*(\\d{1,4})\\s*' + formas + '?\\b'));
        if (m) return parseInt(m[1], 10);
        return null;
    }

    const PARES_PRODUTO_COMBINADO = [
        [/\bshamp\w*\b/, /\bcondicionador\b|\bcond\.?\b/],
        [/\baparelho\b|\bbarbeador\b/, /\bcarga\w*\b|\brefil\w*\b|\bcartucho\w*\b/],
        [/\bcreme dental\b|\bpasta de dente\w*\b/, /\benxaguante\w*\b|\bantisseptico\w*\b/],
        [/\bsabonete\b/, /\bhidratante\b|\bcreme\b(?!\s+dental)/],
    ];

    function ehKitOuCombo(t) {
        const s = (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        return PARES_PRODUTO_COMBINADO.some(([pa, pb]) => pa.test(s) && pb.test(s));
    }

    const LABORATORIOS_GENERICO = [
        'eurofarma', 'ems', 'medley', 'neo quimica', 'germed', 'prati donaduzzi',
        'prati', 'teuto', 'legrand', 'biosintetica', 'sandoz', 'cimed', 'geolab',
        'zydus', 'nova quimica', 'cristalia', 'ache', 'hipolabor', 'sanval',
        'vitamedic', 'belfar', 'natulab', 'ranbaxy', 'torrent', 'eurogenericos',
    ];
    const RE_LABORATORIO = new RegExp('\\b(' +
        [...LABORATORIOS_GENERICO].sort((a, b) => b.length - a.length).join('|') + ')\\b');

    function laboratorioDoNome(t) {
        const s = (t || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
        const m = s.match(RE_LABORATORIO);
        return m ? m[1] : null;
    }

    function notaComUnidades(esperado, candidato) {
        let nota = similaridadeNomes(esperado, candidato);
        if (!nota) return 0;
        if (medidasConflitam(esperado, candidato)) return 0;
        if (ehKitOuCombo(esperado) !== ehKitOuCombo(candidato)) return 0;
        const labE = laboratorioDoNome(esperado), labC = laboratorioDoNome(candidato);
        if (labE && labC && labE !== labC) return 0;
        const de = doseDoNome(esperado), dc = doseDoNome(candidato);
        if (de !== null && dc !== null && de !== dc) return 0;
        const ue = unidadesDoNome(esperado), uc = unidadesDoNome(candidato);
        if (ue !== null && uc !== null) {
            nota += (ue === uc) ? 0.2 : -0.2;
        }
        return Math.max(0, Math.min(1, nota));
    }

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

    // JSON-LD quebrado não parseia, mas os campos simples continuam
    // extraíveis por regex (mesma defesa usada nos outros 4 scripts).
    function extrairProdutoDeJsonLdQuebrado(texto) {
        if (!/"@type"\s*:\s*"Product"/.test(texto)) return null;
        const pega = (re) => { const m = texto.match(re); return m ? m[1] : ''; };
        const price = pega(/"price"\s*:\s*"?([\d.]+)"?/);
        if (!price) return null;
        return {
            name: pega(/"name"\s*:\s*"([^"]*)"/),
            gtin13: pega(/"gtin1?[34]?"\s*:\s*"?(\d+)"?/),
            offers: { price: price, availability: pega(/"availability"\s*:\s*"([^"]*)"/) },
        };
    }

    // Protocolo do clipboard lido pelo Python (SITE identifica a farmácia):
    //   EAN=<digitos>;SITE=panvel;STATUS=OK;PRECO=<valor>;ESTOQUE=EM_ESTOQUE|SEM_ESTOQUE;OBS=<texto>;NOME=<texto>
    //   EAN=<digitos>;SITE=panvel;STATUS=NAO_ENCONTRADO;PRECO=;ESTOQUE=;OBS=;NOME=
    //   EAN=<digitos>;SITE=panvel;STATUS=DIVERGENTE;PRECO=<valor>;ESTOQUE=...;OBS=<texto>;NOME=<texto>   (gtin13 da página != EAN buscado)
    let URL_DO_RESULTADO = '';
    let PRINCIPIO_ATIVO_PAGINA = '';
    let MARCA_PAGINA = '';

    // A Panvel expõe princípio ativo/marca em campos ESTRUTURADOS no
    // próprio JSON-LD (additionalProperty) — mais confiável que raspar
    // texto da página, como os outros 4 sites precisam fazer (testado ao
    // vivo em 07/2026: "Princípio Ativo": "Prednisolona", "Marca": "Ems").
    // Nem todo produto tem additionalProperty (ex.: cosméticos simples);
    // nesse caso cai pro brand.name do próprio JSON-LD como reserva.
    function campoAdicional(produto, trechoNome) {
        const lista = (produto && produto.additionalProperty) || [];
        const item = lista.find(p => (p.name || '').toLowerCase().includes(trechoNome));
        return item ? String(item.value || '').trim() : '';
    }

    function montarSentinel(ean, status, preco, estoque, obs, nome) {
        const limpar = (t) => (t || '').replace(/[;=\n\r]/g, ' ').replace(/\s+/g, ' ').trim();
        return `EAN=${ean};SITE=${SITE};STATUS=${status};PRECO=${preco || ''};ESTOQUE=${estoque || ''};OBS=${limpar(obs)};NOME=${limpar(nome)};URL=${(URL_DO_RESULTADO || '').replace(/[;\s]/g, '')};PRINCIPIO=${limpar(PRINCIPIO_ATIVO_PAGINA)};MARCA=${limpar(MARCA_PAGINA)}`;
    }

    function encerrarAba() {
        setTimeout(() => {
            try { window.close(); } catch (e) { /* ignorado */ }
        }, 800);
    }

    function formatarBR(precoStr) {
        const n = parseFloat(precoStr);
        if (isNaN(n)) return 'R$ ' + precoStr;
        return 'R$ ' + n.toFixed(2).replace('.', ',');
    }

    // Promoção: a Panvel traz o preço "de" estruturado no próprio JSON-LD
    // (offers.highPrice, quando > offers.price) — não precisa raspar DOM
    // riscado como a Raia. Não foi confirmado "leve mais pague menos" na
    // Panvel; se existir, fica de fora por ora (preço unitário do JSON-LD
    // continua correto, só a observação de promoção fica mais simples).
    function montarObservacaoPromo(produto) {
        const preco = parseFloat(produto.offers && produto.offers.price);
        const alto = parseFloat(produto.offers && produto.offers.highPrice);
        if (!isNaN(alto) && !isNaN(preco) && alto > preco + 0.009) {
            return 'Promoção: de ' + formatarBR(alto) + ' por ' + formatarBR(preco);
        }
        return '';
    }

    let pingEnviado = false;
    function enviarPing(ean) {
        if (pingEnviado) return;
        pingEnviado = true;
        GM_setClipboard(`EAN=${ean};SITE=${SITE};STATUS=PING;PRECO=;ESTOQUE=;OBS=;NOME=`);
    }

    // "DESCULPE, MAS NÃO ENCONTRAMOS RESULTADO PARA SUA PESQUISA" (a
    // Panvel escreve tudo em CAIXA ALTA nessa mensagem — testado ao vivo).
    const RE_SEM_RESULTADO = /n[ãa]o encontramos resultado/i;

    let tentativasBusca = 0;

    function paginaDeBusca() {
        const params = new URLSearchParams(location.search);
        const eanBuscado = params.get('termoPesquisa');
        if (!eanBuscado) return;
        enviarPing(eanBuscado);

        // Produto PRIMEIRO: se há card, usa — não importa qualquer texto
        // transitório na página (mesma cautela da Raia: SPA pode mostrar
        // "não encontramos" por uma fração de segundo enquanto hidrata).
        const link = document.querySelector('[data-testid^="product-card"] a[href*="/p-"]');
        if (link) {
            GM_setValue('ean_buscado', eanBuscado);
            location.href = link.href + '#assistente_ean=' + eanBuscado;
            return;
        }

        tentativasBusca++;
        const semResultado = RE_SEM_RESULTADO.test(document.body.innerText);
        if (semResultado && tentativasBusca >= 5) {
            GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
            console.log('[assistente-ean] Panvel: nao encontrado (confirmado apos', tentativasBusca, 'tentativas):', eanBuscado);
            encerrarAba();
            return;
        }
        if (tentativasBusca > 30) {
            console.log('[assistente-ean] Panvel: busca sem card e sem texto claro — aguardando timeout');
            return;
        }
        setTimeout(paginaDeBusca, 500);
    }

    // ---- Busca por NOME (retaguarda) ----

    let tentativasNome = 0;

    function paginaDeBuscaPorNome() {
        enviarPing(EAN_DO_FRAGMENTO);
        const semResultado = RE_SEM_RESULTADO.test(document.body.innerText);
        const candidatos = [...document.querySelectorAll('[data-testid^="product-card"]')]
            .map(card => {
                const a = card.querySelector('a[href*="/p-"]');
                return a ? { url: a.href, texto: card.innerText || '' } : null;
            }).filter(Boolean);

        if (!candidatos.length) {
            tentativasNome++;
            if (semResultado || tentativasNome > 20) {
                GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Panvel: busca por nome sem resultados');
                encerrarAba();
                return;
            }
            setTimeout(paginaDeBuscaPorNome, 500);
            return;
        }

        let melhor = null, melhorNota = 0;
        for (const c of candidatos) {
            const nota = notaComUnidades(NOME_ESPERADO, c.texto);
            if (nota > melhorNota) { melhorNota = nota; melhor = c; }
        }
        if (!melhor || melhorNota < LIMIAR_NOME) {
            console.log('[assistente-ean] Panvel: nenhum candidato parecido o bastante (melhor:', melhorNota.toFixed(2), ')');
            GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
            encerrarAba();
            return;
        }
        console.log('[assistente-ean] Panvel: candidato por nome aceito (nota', melhorNota.toFixed(2), ')');
        GM_setValue('ean_buscado', EAN_DO_FRAGMENTO);
        location.href = melhor.url.split('#')[0] + '#assistente_ean=' + EAN_DO_FRAGMENTO + '&assistente_por_nome=1';
    }

    let tentativasProduto = 0;

    function paginaDeProduto() {
        const eanBuscado = pegarEanPendente();
        URL_DO_RESULTADO = location.href.split('#')[0];
        if (!eanBuscado) return; // chegamos aqui sem vir de uma busca do assistente; ignora.

        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        let produto = null;
        for (const s of scripts) {
            try {
                const dado = JSON.parse(s.textContent);
                if (dado && dado['@type'] === 'Product') {
                    produto = dado;
                    break;
                }
            } catch (e) {
                const recuperado = extrairProdutoDeJsonLdQuebrado(s.textContent);
                if (recuperado) {
                    console.log('[assistente-ean] Panvel: JSON-LD quebrado, campos recuperados por regex');
                    produto = recuperado;
                    break;
                }
            }
        }

        PRINCIPIO_ATIVO_PAGINA = produto ? campoAdicional(produto, 'princ') : '';
        MARCA_PAGINA = produto
            ? (campoAdicional(produto, 'marca') || (produto.brand && produto.brand.name) || '')
            : '';

        if (!produto || !produto.offers || !produto.offers.price) {
            if (/p[aá]gina n[ãa]o encontrada|page not found/i.test(document.body.innerText)) {
                GM_setValue('ean_buscado', '');
                GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Panvel: pagina 404 — NAO_ENCONTRADO para', eanBuscado);
                encerrarAba();
                return;
            }
            tentativasProduto++;
            const textoIndisponivel = /pre[cç]o\s*indispon|produto\s*indispon/i.test(document.body.innerText);
            if (textoIndisponivel) {
                const nome = (produto && produto.name)
                    || ((document.querySelector('h1') || {}).innerText || '').trim();
                GM_setValue('ean_buscado', '');
                try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }
                GM_setClipboard(montarSentinel(eanBuscado, 'INDISPONIVEL', '', 'SEM_ESTOQUE', '', nome));
                console.log('[assistente-ean] Panvel: preco INDISPONIVEL para', eanBuscado);
                encerrarAba();
                return;
            }
            // JSON-LD não apareceu ainda; tenta de novo em breve.
            setTimeout(paginaDeProduto, 500);
            return;
        }

        const gtin = (produto.gtin13 || produto.gtin || '').toString().trim();
        const preco = produto.offers.price;
        const nome = produto.name || '';
        // Além de "InStock", a Panvel usa "InStoreOnly" (só disponível na
        // loja física, não entrega) — tratado como SEM_ESTOQUE de
        // propósito: não é um preço que dá pra comparar/comprar online
        // (achado ao vivo em 07/2026, Celecoxibe 200mg).
        const disponibilidade = (produto.offers.availability || '').toString();
        const estoque = disponibilidade.includes('InStock') && !disponibilidade.includes('InStoreOnly')
            ? 'EM_ESTOQUE' : 'SEM_ESTOQUE';

        const obs = montarObservacaoPromo(produto);

        GM_setValue('ean_buscado', '');
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }

        // Compara sem zeros à esquerda: EANs de origem UPC vêm na lista como
        // "0020800750158" e o site pode publicar o gtin sem esses zeros.
        const semZeros = (t) => t.replace(/^0+/, '');

        if (MODO_POR_NOME) {
            const obsNome = `Achado por NOME (EAN do site: ${gtin || '-'})` + obsEmbalagem(preco, nome) + (obs ? ' / ' + obs : '');
            GM_setClipboard(montarSentinel(eanBuscado, 'POR_NOME', preco, estoque, obsNome, nome));
            console.log('[assistente-ean] Panvel: preco POR NOME:', preco, 'EAN buscado:', eanBuscado, 'EAN do site:', gtin);
        } else if (gtin && semZeros(gtin) !== semZeros(eanBuscado)) {
            GM_setClipboard(montarSentinel(eanBuscado, 'DIVERGENTE', preco, estoque, obs, `${nome} (gtin real: ${gtin})`));
            console.log('[assistente-ean] Panvel: EAN divergente. Buscado:', eanBuscado, 'Pagina:', gtin);
        } else {
            GM_setClipboard(montarSentinel(eanBuscado, 'OK', preco, estoque, obs, nome));
            console.log('[assistente-ean] Panvel: preco copiado:', preco, 'Estoque:', estoque, 'Obs:', obs || '(sem promo)');
        }

        encerrarAba();
    }

    // Rodamos a partir do document-idle (padrão dos outros 4 scripts); as
    // funções já re-tentam sozinhas se a página ainda estiver hidratando.
    setTimeout(() => {
        if (location.pathname === '/panvel/buscarProduto.do') {
            if (NOME_ESPERADO && EAN_DO_FRAGMENTO) {
                paginaDeBuscaPorNome();
            } else {
                paginaDeBusca();
            }
        } else if (/\/p-\d+$/.test(location.pathname)) {
            paginaDeProduto();
        }
    }, 600);
})();
