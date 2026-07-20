// ==UserScript==
// @name         Captura de Preço - Farmácias São Paulo (Assistente EAN)
// @namespace    consulta-precos-drogaraia
// @version      3.3
// @downloadURL  https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_saopaulo.user.js
// @updateURL    https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_saopaulo.user.js
// @description  Busca o EAN na Farmácias São Paulo, entra no produto, lé o preço via JSON-LD e copia para a área de transferência.
// @match        https://www.farmaciassaopaulo.com.br/*
// @grant        GM_setClipboard
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SITE = 'saopaulo';

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


    const EAN_DO_FRAGMENTO = (() => {
        const m = (location.hash || '').match(/assistente_ean=(\d{8,14})/);
        return m ? m[1] : '';
    })();

    const EAN_DA_BUSCA = (() => {
        const q = (new URLSearchParams(location.search).get('q') || '').trim();
        if (/^\d{8,14}$/.test(q)) return q;
        const mPath = location.pathname.match(/^\/(\d{8,14})\/?$/);
        if (mPath) return mPath[1];
        return '';
    })();

    function pegarEanPendente() {
        return EAN_DO_FRAGMENTO || GM_getValue('ean_buscado', '');
    }

    const NOME_ESPERADO = (() => {
        const m = (location.hash || '').match(/assistente_nome=([^&]+)/);
        if (!m) return '';
        try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    })();
    const MODO_POR_NOME = /assistente_por_nome=1/.test(location.hash || '');

    const LIMIAR_NOME = 0.6;

    function tokensDoNome(t) {
        const irrelevantes = new Set(['de','da','do','para','com','em','un','und','unidade','unidades','x','c','e','o','a','kit','generico','generica','revestido','revestidos','leve','pague','cada','gratis']);
        return new Set((t||'').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g,'')
            .replace(/[^a-z0-9 ]/g,' ').split(/\s+/).filter(w => w.length >= 2 && !irrelevantes.has(w)));
    }

    // REGRA DA MARCA: o 1º token útil da referência (quase sempre a marca)
    // PRECISA existir no candidato — evita aceitar produto parecido de OUTRA
    // marca (erro real de 07/2026: Sintocalmy aceito no lugar de SonoZzz).
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
    // Numeros grandes em formato brasileiro usam "." (ou espaco) como
    // separador de MILHAR, nao de decimal (ex.: "100.000 UI" = cem mil, nao
    // 100,0) - o oposto do padrao internacional que o resto do parsing
    // supoe. Sem normalizar isso primeiro, "100.000ui" virava 100.0 e
    // "100 000ui" (MESMO produto, outro site) virava 0.0 - nomes IDENTICOS
    // marcados como incoerentes so por formatacao de numero (achado real de
    // 07/2026, mesmo bug do lado Python). So normaliza quando o separador
    // vem seguido de EXATAMENTE 3 digitos e logo antes de unidade
    // reconhecida - nunca mexe em decimal de verdade ("0.5mg").
    const RE_MILHAR = /(\d{1,3}(?:[.\s]\d{3})+)(?=\s*(?:mcg|mg|gramas?|gr|g|kg|ml|l|meq|ui|mts|h|%)(?![a-z0-9]))/g;

    function normalizarMilhares(s) {
        return s.replace(RE_MILHAR, (m) => m.replace(/[.\s]/g, ''));
    }

    function medidasDoNome(t) {
        const s = normalizarMilhares((t || '').toLowerCase()).replace(/,/g, '.');
        const re = /(\d+(?:\.\d+)?)\s*(mcg|mg|gramas?|gr|g|kg|ml|l|meq|ui|mts|h|%)(?![a-z0-9])/g;
        const medidas = {};
        let m;
        while ((m = re.exec(s)) !== null) {
            let valor = parseFloat(m[1]), unidade = m[2];
            // g/gr/gramas ficam em bucket PROPRIO ("g"), separado de "mg": o
            // peso do tubo/bisnaga (ex.: "Creme 30g") nao pode colidir com a
            // dosagem do principio ativo (ex.: "20mg") so porque um site
            // omite a dosagem - bug real de 07/2026 com cremes EMS/Eurofarma.
            if (unidade === 'gr' || unidade === 'gramas' || unidade === 'grama') { unidade = 'g'; }
            if (unidade === 'kg') { valor *= 1000; unidade = 'g'; }
            if (unidade === 'l') { valor *= 1000; unidade = 'ml'; }
            if (!medidas[unidade]) medidas[unidade] = [];
            medidas[unidade].push(valor);
        }
        return medidas;
    }

    const UNIDADES_EMBALAGEM = new Set(['ml', 'l', 'g']); // volume/peso de embalagem: kit x avulso tolerado

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
                // MULTICONJUNTO exato - sort() sem Set(): "Alginac 50mg" (1
                // substancia) tem que continuar rejeitado contra "Alginac
                // 50mg+50mg+50mg" (3 substancias, cada uma coincidentemente
                // 50mg) - um Set() aqui colapsa os tres 50mg em um so e
                // deixa passar por engano (achado real na revisao de
                // 07/2026, auditando o proprio precos.csv).
                const sa = [...va].sort((x, y) => x - y).join(',');
                const sb = [...vb].sort((x, y) => x - y).join(',');
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
        // ATENCAO: dentro de uma STRING (nao de um literal /regex/), "\d",
        // "\s" e "\b" NAO sao escapes de regex - sao processados pelo
        // parser do JS ANTES do RegExp existir. "\d"/"\s" perdem a barra
        // (viram "d"/"s" literais) e "\b" vira um caractere de BACKSPACE
        // de verdade. O resultado era um regex que nunca casava nada -
        // doseDoNome() sempre devolvia null, silenciosamente (bug real
        // achado na revisao de 07/2026). Corrigido com barra dupla.
        let m = s.match(new RegExp('(\\d{1,4})\\s*' + formas + '\\b'));
        if (m) return parseInt(m[1], 10);
        m = s.match(new RegExp('\\bc\\s*/\\s*(\\d{1,4})\\s*' + formas + '?\\b'));
        if (m) return parseInt(m[1], 10);
        return null;
    }

    // Sinal de KIT DE PRODUTOS DIFERENTES (espelha eh_kit_ou_combo() do
    // Python) - nao confundir com "kit" de N unidades do MESMO produto (ja
    // coberto por unidadesDoNome). Exige um PAR de categorias de produto
    // DIFERENTES no mesmo nome, nao uma palavra solta ("kit"/"leve X pague
    // Y" sozinhos tambem aparecem em pacotes do MESMO produto e ate em
    // remedios combinados - "EMS 875mg + 125mg" tem um "+" entre doses).
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

    // Laboratorio/fabricante do GENERICO citado no nome (espelha
    // laboratorio_do_nome() do Python) - generico do MESMO principio
    // ativo/dose/contagem mas de LABORATORIO diferente e outro produto/EAN
    // (achado real no teste assistido de 07/2026: Rosuvastatina Eurofarma
    // trocada por Sandoz, Olanzapina Eurofarma trocada por Geolab).
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
        // quantidade de comprimidos/capsulas diferente = OUTRO produto
        const de = doseDoNome(esperado), dc = doseDoNome(candidato);
        if (de !== null && dc !== null && de !== dc) return 0;
        const ue = unidadesDoNome(esperado), uc = unidadesDoNome(candidato);
        // Quantidade igual = bônus; declarada e diferente = penalidade (um
        // kit legítimo do mesmo item ainda passa: o resto do nome bate ~100%).
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

    // Pagina onde o preco foi encontrado: vai no protocolo (URL=) para o
    // assistente abrir DIRETO na conferencia manual (botao direito).
    let URL_DO_RESULTADO = '';

    // "Principio Ativo" da especificacao do produto, quando a pagina expoe
    // isso (campo OPCIONAL - nem todo site/produto tem). Evidencia extra na
    // auditoria de coerencia entre farmacias: mais confiavel que raspar do
    // titulo, quando presente. Regex generico (nao depende de layout/classe
    // CSS) contra o texto visivel da pagina - testado ao vivo em 07/2026.
    let PRINCIPIO_ATIVO_PAGINA = '';
    function principioAtivoDaPagina(texto) {
        const m = (texto || '').match(/Princ[ií]pio Ativo:?\s*\n?\s*([^\n]{2,60})/i);
        return m ? m[1].trim() : '';
    }

    // "Marca": cobre categorias SEM principio ativo (desodorante, fralda,
    // camisinha etc.) - mesma ideia do Principio Ativo, mas generica pra
    // qualquer produto. Testado ao vivo contra o TEXTO da pagina (nao o
    // JSON-LD: aqui o brand do JSON-LD e a LINHA do produto, ex. "Mach 3",
    // nao a marca de verdade "Gillette" - o texto da especificacao e mais
    // consistente).
    let MARCA_PAGINA = '';
    function marcaDaPagina(texto) {
        // ':' OBRIGATORIO: sem isso, "marca" dentro de frase solta (ex.: aviso
        // regulatorio "esta marca deve deixar explicito que o produto nao
        // possui acao clareadora...") virava falso positivo - caso real de
        // 07/2026, Bepantol Derma com o campo "marca" virando lixo de aviso.
        const m = (texto || '').match(/\bMarca:\s*\n?\s*([^\n]{2,60})/i);
        return m ? m[1].trim() : '';
    }

    function montarSentinel(ean, status, preco, estoque, obs, nome) {
        const limpar = (t) => (t || '').replace(/[;=\n\r]/g, ' ').replace(/\s+/g, ' ').trim();
        return `EAN=${ean};SITE=${SITE};STATUS=${status};PRECO=${preco || ''};ESTOQUE=${estoque || ''};OBS=${limpar(obs)};NOME=${limpar(nome)};URL=${(URL_DO_RESULTADO || '').replace(/[;\s]/g, '')};PRINCIPIO=${limpar(PRINCIPIO_ATIVO_PAGINA)};MARCA=${limpar(MARCA_PAGINA)}`;
    }

    function encerrarAba() {
        setTimeout(() => {
            try { window.close(); } catch (e) { }
        }, 800);
    }

    function extrairValorBR(texto) {
        const m = (texto || '').match(/R\$\s*([\d.]*\d,\d{2}|\d+(?:\.\d{1,2})?)/);
        if (!m) return '';
        const bruto = m[1];
        if (bruto.includes(',')) return bruto.replace(/\./g, '').replace(',', '.');
        return bruto;
    }

    function formatarBR(valor) {
        const n = parseFloat(valor);
        if (isNaN(n)) return 'R$ ' + valor;
        return 'R$ ' + n.toFixed(2).replace('.', ',');
    }

    const semZeros = (t) => (t || '').replace(/^0+/, '');

    let pingEnviado = false;
    function enviarPing(ean) {
        if (pingEnviado) return;
        pingEnviado = true;
        GM_setClipboard(`EAN=${ean};SITE=${SITE};STATUS=PING;PRECO=;ESTOQUE=;OBS=;NOME=`);
    }

    function paginaDeBusca(ean) {
        if (!ean) return;
        enviarPing(ean);

        const semResultado = /0\s*resultados|não encontr|nenhum result/i.test(document.body.innerText);
        const link = [...document.querySelectorAll('a[href$="/p"]')].find(a => (a.innerText || '').trim());

        if (!link) {
            if (semResultado) {
                GM_setClipboard(montarSentinel(ean, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Sao Paulo: nao encontrado:', ean);
                encerrarAba();
                return;
            }
            setTimeout(() => paginaDeBusca(ean), 500);
            return;
        }

        GM_setValue('ean_buscado', ean);
        location.href = link.href + '#assistente_ean=' + ean;
    }

    let tentativasNome = 0;

    function paginaDeBuscaPorNome() {
        enviarPing(EAN_DO_FRAGMENTO);
        const candidatos = [...document.querySelectorAll('a[href$="/p"]')]
            .filter(a => (a.innerText || '').trim())
            .map(a => {
                const cont = a.closest('li, article, div');
                return { url: a.href, texto: ((cont ? cont.innerText : '') || a.innerText || '') };
            });
        if (!candidatos.length) {
            tentativasNome++;
            const semResultado = /0\s*resultados|não encontr|nenhum result/i.test(document.body.innerText);
            if (semResultado || tentativasNome > 20) {
                GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Sao Paulo: busca por nome sem resultados');
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
            console.log('[assistente-ean] Sao Paulo: nenhum candidato parecido o bastante (melhor:', melhorNota.toFixed(2), ')');
            GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
            encerrarAba();
            return;
        }
        console.log('[assistente-ean] Sao Paulo: candidato por nome aceito (nota', melhorNota.toFixed(2), ')');
        GM_setValue('ean_buscado', EAN_DO_FRAGMENTO);
        location.href = melhor.url.split('#')[0] + '#assistente_ean=' + EAN_DO_FRAGMENTO + '&assistente_por_nome=1';
    }

    let tentativasProduto = 0;

    function paginaDeProduto() {
        const eanBuscado = pegarEanPendente();
        URL_DO_RESULTADO = location.href.split('#')[0];
        PRINCIPIO_ATIVO_PAGINA = principioAtivoDaPagina(document.body.innerText);
        MARCA_PAGINA = marcaDaPagina(document.body.innerText);
        if (!eanBuscado) return;

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
                    console.log('[assistente-ean] Sao Paulo: JSON-LD quebrado, campos recuperados por regex');
                    produto = recuperado;
                    break;
                }
            }
        }

        if (!produto || !produto.offers || !produto.offers.price) {
            if (/página não encontrada|page not found/i.test(document.body.innerText)) {
                GM_setValue('ean_buscado', '');
                GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Sao Paulo: pagina 404 — NAO_ENCONTRADO para', eanBuscado);
                encerrarAba();
                return;
            }
            tentativasProduto++;
            const textoIndisponivel = /pre[cç]o\s*indispon|produto\s*indispon/i.test(document.body.innerText);
            if (textoIndisponivel) {
                const nome = (produto && produto.name) || (document.querySelector('h1') || {}).innerText || '';
                GM_setValue('ean_buscado', '');
                try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }
                GM_setClipboard(montarSentinel(eanBuscado, 'INDISPONIVEL', '', 'SEM_ESTOQUE', '', nome));
                console.log('[assistente-ean] Sao Paulo: preco INDISPONIVEL para', eanBuscado);
                encerrarAba();
                return;
            }
            setTimeout(paginaDeProduto, 500);
            return;
        }

        const gtin = (produto.gtin13 || produto.gtin || '').toString().trim();
        const preco = produto.offers.price;
        const nome = produto.name || '';
        const disponibilidade = (produto.offers.availability || '').toString();
        const estoque = disponibilidade.includes('InStock') ? 'EM_ESTOQUE' : 'SEM_ESTOQUE';

        const promoDom = detectarPromocao();
        const obs = montarObservacao(preco, promoDom, nome);

        GM_setValue('ean_buscado', '');
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }

        const semZerosFunc = (t) => t.replace(/^0+/, '');

        if (MODO_POR_NOME) {
            const obsNome = `Achado por NOME (EAN do site: ${gtin || '-'})` + obsEmbalagem(preco, nome) + (obs ? ' / ' + obs : '');
            GM_setClipboard(montarSentinel(eanBuscado, 'POR_NOME', preco, estoque, obsNome, nome));
            console.log('[assistente-ean] Sao Paulo: preco POR NOME:', preco, 'EAN do site:', gtin);
        } else if (gtin && semZerosFunc(gtin) !== semZerosFunc(eanBuscado)) {
            GM_setClipboard(montarSentinel(eanBuscado, 'DIVERGENTE', preco, estoque, obs, `${nome} (gtin real: ${gtin})`));
            console.log('[assistente-ean] Sao Paulo: EAN divergente. Buscado:', eanBuscado, 'Pagina:', gtin);
        } else {
            GM_setClipboard(montarSentinel(eanBuscado, 'OK', preco, estoque, obs, nome));
            console.log('[assistente-ean] Sao Paulo: preco copiado:', preco, 'Estoque:', estoque, 'Obs:', obs || '(sem promo)');
        }

        encerrarAba();
    }

    const PADRAO_LEVE = /leve\s*\+?\s*\d+\s*(?:e\s*)?(?:pague\s*\d+|(?:unidades?\s*)?por\s*R\$\s*[\d.,]+(?:\s*cada)?|[^\n]{0,40}?R\$\s*[\d.,]+\s*cada)/i;

    function detectarPromocao() {
        const resultado = { precoOriginal: '', fraseLeve: '' };
        const precoEl = document.querySelector('.unit-price');
        if (!precoEl) return resultado;

        let e = precoEl.parentElement;
        for (let nivel = 0; nivel < 6 && e && e !== document.body; nivel++, e = e.parentElement) {
            if (!resultado.precoOriginal) {
                for (const el of e.querySelectorAll('span, p, s, del')) {
                    if (el.children.length) continue;
                    if (el.closest('a, article, section')) continue;
                    const texto = el.textContent || '';
                    if (!/R\$\s*\d/.test(texto)) continue;
                    let riscado = false;
                    try { riscado = getComputedStyle(el).textDecorationLine.includes('line-through'); } catch (err) { }
                    if (riscado) {
                        resultado.precoOriginal = extrairValorBR(texto);
                        break;
                    }
                }
            }
            if (!resultado.fraseLeve) {
                const copia = e.cloneNode(true);
                for (const lixo of copia.querySelectorAll('a, article, section')) lixo.remove();
                const m = (copia.textContent || '').match(PADRAO_LEVE);
                if (m) resultado.fraseLeve = m[0].replace(/\s+/g, ' ').trim();
            }
            if (resultado.precoOriginal && resultado.fraseLeve) break;
        }
        return resultado;
    }

    function montarObservacao(preco, promo, nome) {
        const partes = [];
        if (promo.precoOriginal) {
            partes.push(`Promoção: de ${formatarBR(promo.precoOriginal)} por ${formatarBR(preco)}`);
        }
        if (promo.fraseLeve) {
            partes.push(`Promoção: ${promo.fraseLeve}`);
        }
        return partes.join(' / ');
    }

    // NAO esperar 'load' (trackers seguram o evento alem do timeout).
    setTimeout(() => {
            if (/\/p\/?$|\/p\/\d+/.test(location.pathname)) {
                paginaDeProduto();
            } else if (NOME_ESPERADO && EAN_DO_FRAGMENTO) {
                paginaDeBuscaPorNome();
            } else if (EAN_DA_BUSCA) {
                paginaDeBusca(EAN_DA_BUSCA);
            }
        }, 600);
})();
