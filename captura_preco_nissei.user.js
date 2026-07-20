// ==UserScript==
// @name         Captura de Preço - Farmácias Nissei (Assistente EAN)
// @namespace    consulta-precos-drogaraia
// @version      3.5
// @downloadURL  https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_nissei.user.js
// @updateURL    https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco_nissei.user.js
// @description  Busca o EAN na Nissei, entra no produto, lê o preço via JSON-LD + bloco de preço e copia para a área de transferência.
// @match        https://www.farmaciasnissei.com.br/*
// @grant        GM_setClipboard
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SITE = 'nissei';

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


    // O EAN buscado viaja da página de busca para a do produto pelo FRAGMENTO
    // da URL (#assistente_ean=...): o GM_setValue grava de forma assíncrona e
    // pode se perder quando a navegação é imediata — foi exatamente o bug que
    // fazia a página do produto ficar muda. Lemos o fragmento já na injeção,
    // antes que o site possa normalizar a URL.
    const EAN_DO_FRAGMENTO = (() => {
        const m = (location.hash || '').match(/assistente_ean=(\d{8,14})/);
        return m ? m[1] : '';
    })();

    function pegarEanPendente() {
        return EAN_DO_FRAGMENTO || GM_getValue('ean_buscado', '');
    }

    // Busca por NOME (retaguarda): o assistente manda o nome esperado no
    // fragmento quando o EAN não foi encontrado e outra farmácia já
    // identificou o produto.
    const NOME_ESPERADO = (() => {
        const m = (location.hash || '').match(/assistente_nome=([^&]+)/);
        if (!m) return '';
        try { return decodeURIComponent(m[1]); } catch (e) { return m[1]; }
    })();
    const MODO_POR_NOME = /assistente_por_nome=1/.test(location.hash || '');

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
    // Numeros grandes em formato brasileiro usam "." (ou espaco) como
    // separador de MILHAR, nao de decimal (ex.: "100.000 UI" = cem mil, nao
    // 100,0) - o oposto do padrao internacional que o resto do parsing
    // supoe. Sem normalizar isso primeiro, "100.000ui" virava 100.0 e
    // "100 000ui" (MESMO produto, outro site) virava 0.0 - nomes IDENTICOS
    // marcados como incoerentes so por formatacao de numero (achado real de
    // 07/2026, mesmo bug do lado Python). So normaliza quando o separador
    // vem seguido de EXATAMENTE 3 digitos e logo antes de unidade
    // reconhecida - nunca mexe em decimal de verdade ("0.5mg").
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
            // g/gr/gramas ficam em bucket PROPRIO ("g"), separado de "mg": o
            // peso do tubo/bisnaga (ex.: "Creme 30g") nao pode colidir com a
            // dosagem do principio ativo (ex.: "20mg") so porque um site
            // omite a dosagem - bug real de 07/2026 com cremes EMS/Eurofarma.
            if (unidade === 'gr' || unidade === 'gramas' || unidade === 'grama') { unidade = 'g'; }
            if (unidade === 'kg') { valor *= 1000; unidade = 'g'; }
            if (unidade === 'l' || unidade === 'litro' || unidade === 'litros') { valor *= 1000; unidade = 'ml'; }
            if (unidade === 'metro' || unidade === 'metros') { unidade = 'mts'; }
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

    // Alguns produtos da Nissei têm o JSON-LD QUEBRADO (caractere de controle
    // na descrição — visto ao vivo no EAN 7896044999911 em 07/2026): o
    // JSON.parse falha, mas os campos simples continuam extraíveis por regex.
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

    // A busca por EAN inexistente na Nissei NÃO mostra "não encontrado": ela
    // devolve uma listagem genérica com centenas de produtos. Acima deste
    // número de resultados, tratamos como NAO_ENCONTRADO.
    const MAX_RESULTADOS_REAIS = 3;

    // Protocolo do clipboard lido pelo Python (SITE identifica a farmácia):
    //   EAN=<digitos>;SITE=nissei;STATUS=OK;PRECO=<valor>;ESTOQUE=...;OBS=<texto>;NOME=<texto>
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
    // JSON-LD: em alguns sites o brand do JSON-LD e a LINHA do produto, ex.
    // "Mach 3", nao a marca de verdade "Gillette" - o texto da especificacao
    // e mais consistente).
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
            try { window.close(); } catch (e) { /* ignorado */ }
        }, 800);
    }

    // "77,90" / "1.299,90" -> "77.90" / "1299.90"
    function paraDecimal(texto) {
        const m = (texto || '').match(/([\d.]*\d,\d{2}|\d+(?:\.\d{1,2})?)/);
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

    // Só age quando o termo da URL /pesquisa/<termo> é um código de barras
    // (8 a 14 dígitos) — navegação manual no site não dispara nada.
    function pegarEanDaBusca() {
        const seg = decodeURIComponent((location.pathname.split('/')[2] || '').trim());
        return /^\d{8,14}$/.test(seg) ? seg : '';
    }

    function acharLinkProduto() {
        const pc = document.querySelector('.preco-produto');
        if (!pc) return null;
        let e = pc;
        for (let i = 0; i < 8 && e; i++, e = e.parentElement) {
            const a = e.querySelector('a[href]');
            if (a && !a.href.includes('/pesquisa')) return a;
        }
        return null;
    }

    // Sinal de vida para o assistente: confirma que o script está instalado
    // e rodou nesta página (o Python só loga, não grava).
    let pingEnviado = false;
    function enviarPing(ean) {
        if (pingEnviado) return;
        pingEnviado = true;
        GM_setClipboard(`EAN=${ean};SITE=${SITE};STATUS=PING;PRECO=;ESTOQUE=;OBS=;NOME=`);
    }

    function paginaDeBusca() {
        const ean = pegarEanDaBusca();
        if (!ean) return;
        enviarPing(ean);

        const m = document.body.innerText.match(/(\d+)\s*produtos?/i);
        if (!m) {
            // A contagem de resultados ainda não renderizou; tenta de novo.
            setTimeout(paginaDeBusca, 500);
            return;
        }
        const n = parseInt(m[1], 10);

        if (n === 0 || n > MAX_RESULTADOS_REAIS) {
            GM_setClipboard(montarSentinel(ean, 'NAO_ENCONTRADO', '', '', '', ''));
            console.log('[assistente-ean] Nissei: nao encontrado (', n, 'resultados):', ean);
            encerrarAba();
            return;
        }

        const link = acharLinkProduto();
        if (!link) {
            setTimeout(paginaDeBusca, 500);
            return;
        }

        GM_setValue('ean_buscado', ean); // reserva, caso o fragmento se perca
        location.href = link.href + '#assistente_ean=' + ean;
    }

    // ---- Busca por NOME (retaguarda) ----

    let tentativasNome = 0;

    function candidatosDaBusca() {
        const vistos = new Set();
        const lista = [];
        for (const pc of document.querySelectorAll('.preco-produto')) {
            let e = pc, a = null;
            for (let i = 0; i < 8 && e; i++, e = e.parentElement) {
                a = e.querySelector('a[href]');
                if (a && !a.href.includes('/pesquisa')) break;
                a = null;
            }
            if (a && !vistos.has(a.href)) {
                vistos.add(a.href);
                lista.push({ url: a.href, texto: ((e ? e.innerText : '') || a.innerText || '') });
            }
        }
        return lista;
    }

    function paginaDeBuscaPorNome() {
        enviarPing(EAN_DO_FRAGMENTO);
        const candidatos = candidatosDaBusca();
        if (!candidatos.length) {
            tentativasNome++;
            const m = document.body.innerText.match(/(\d+)\s*produtos?/i);
            if ((m && parseInt(m[1], 10) === 0) || tentativasNome > 20) {
                GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Nissei: busca por nome sem resultados');
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
            console.log('[assistente-ean] Nissei: nenhum candidato parecido o bastante (melhor:', melhorNota.toFixed(2), ')');
            GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
            encerrarAba();
            return;
        }
        console.log('[assistente-ean] Nissei: candidato por nome aceito (nota', melhorNota.toFixed(2), ')');
        GM_setValue('ean_buscado', EAN_DO_FRAGMENTO);
        location.href = melhor.url.split('#')[0] + '#assistente_ean=' + EAN_DO_FRAGMENTO + '&assistente_por_nome=1';
    }

    let tentativasProduto = 0;

    function paginaDeProduto() {
        const eanBuscado = pegarEanPendente();
        URL_DO_RESULTADO = location.href.split('#')[0];
        PRINCIPIO_ATIVO_PAGINA = principioAtivoDaPagina(document.body.innerText);
        MARCA_PAGINA = marcaDaPagina(document.body.innerText);
        if (!eanBuscado) return; // não viemos de uma busca do assistente

        let produto = null;
        for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
            try {
                const dado = JSON.parse(s.textContent);
                const tipo = dado && dado['@type'];
                if (tipo === 'Product' || (Array.isArray(tipo) && tipo.includes('Product'))) {
                    produto = dado;
                    break;
                }
            } catch (e) {
                const recuperado = extrairProdutoDeJsonLdQuebrado(s.textContent);
                if (recuperado) {
                    console.log('[assistente-ean] Nissei: JSON-LD quebrado, campos recuperados por regex');
                    produto = recuperado;
                    break;
                }
            }
        }
        if (!produto || !produto.offers || !produto.offers.price) {
            // Página 404 (link morto): conclui como NAO_ENCONTRADO na hora.
            if (/página não encontrada|page not found/i.test(document.body.innerText)) {
                GM_setValue('ean_buscado', '');
                GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Nissei: pagina 404 — NAO_ENCONTRADO para', eanBuscado);
                encerrarAba();
                return;
            }
            // Produto com "Preço indisponível": a Nissei publica a página sem
            // preço no JSON-LD. Só registra INDISPONIVEL quando o SITE DIZ
            // isso explicitamente — sem o texto, continua tentando e deixa o
            // assistente dar timeout (fica em branco/pendente: foi erro, não
            // indisponibilidade).
            tentativasProduto++;
            const textoIndisponivel = /pre[cç]o\s*indispon|produto\s*indispon/i.test(document.body.innerText);
            if (textoIndisponivel) {
                const nome = (produto && produto.name)
                    || ((document.querySelector('h1') || {}).innerText || '').trim();
                GM_setValue('ean_buscado', '');
                try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }
                GM_setClipboard(montarSentinel(eanBuscado, 'INDISPONIVEL', '', 'SEM_ESTOQUE', '', nome));
                console.log('[assistente-ean] Nissei: preco INDISPONIVEL para', eanBuscado);
                encerrarAba();
                return;
            }
            setTimeout(paginaDeProduto, 500);
            return;
        }

        const gtin = (produto.gtin13 || produto.gtin || '').toString().trim();
        const precoJson = produto.offers.price.toString();
        const nome = produto.name || '';

        const box = document.querySelector('.bloco-preco-produto')
            || document.querySelector('[data-target="preco-produto"]');
        const boxTexto = box ? box.innerText : '';

        let preco = precoJson;
        let obs = '';

        // "Leve mais por menos": o bloco mostra "1 por R$ 77,90 cada" e
        // "2 ou + por R$ 62,90 cada" — OU, em outro layout (visto ao vivo em
        // 07/2026 na Ciclobenzaprina), "1 por R$ 20,90" (sem o "cada") e
        // "3 por R$ 13,93 cada" (sem o "ou +"). O preço registrado deve ser
        // SEMPRE o de 1 unidade.
        const mUnit = boxTexto.match(/1\s*por\s*R\$\s*([\d.,]+)(?:\s*cada)?/i);
        let mMais = null;
        const reMais = /(\d+)\s*(?:ou\s*\+)?\s*por\s*R\$\s*([\d.,]+)\s*cada/gi;
        let mm;
        while ((mm = reMais.exec(boxTexto)) !== null) {
            if (parseInt(mm[1], 10) >= 2) { mMais = mm; break; }
        }
        if (!mMais) {
            mMais = boxTexto.match(/leve\s*(\d+)\s*por\s*R\$\s*([\d.,]+)\s*cada/i);
        }

        if (mUnit && mMais) {
            preco = paraDecimal(mUnit[1]);
            // " / " como separador: ";" seria removido pela sanitização do protocolo
            obs = `Promoção: 1 por R$ ${mUnit[1]} / ${mMais[0].replace(/\s+/g, ' ').trim()}`;
        }

        // JSON-LD MENTIROSO: alguns produtos publicam price "0.00" no JSON-LD
        // com o preço real só no HTML (caso real de 07/2026: Ciclobenzaprina
        // — JSON-LD 0.00, página mostrando "1 por R$ 20,90"). NUNCA aceitar
        // preço <= 0: usa o "1 por R$ X" do bloco; sem ele, só aceita se o
        // bloco tiver UM único valor; senão continua tentando (vira timeout e
        // o item fica pendente — melhor em branco do que errado).
        if (!(parseFloat(preco) > 0)) {
            if (mUnit) {
                preco = paraDecimal(mUnit[1]);
            } else {
                const valoresBox = (boxTexto.match(/R\$\s*[\d.,]+/g) || [])
                    .map(v => paraDecimal(v))
                    .filter(v => parseFloat(v) > 0);
                if (valoresBox.length === 1) preco = valoresBox[0];
            }
            if (!(parseFloat(preco) > 0)) {
                console.log('[assistente-ean] Nissei: JSON-LD com preco zero e bloco de preco ambíguo — aguardando');
                setTimeout(paginaDeProduto, 500);
                return;
            }
        }

        if (!obs) {
            // Desconto simples: o bloco mostra o preço antigo (maior) junto do
            // atual, ex.: "R$ 28,00  R$ 27,95". O JSON-LD já traz o promocional.
            const valores = (boxTexto.match(/R\$\s*[\d.,]+/g) || [])
                .map(v => parseFloat(paraDecimal(v)))
                .filter(v => !isNaN(v));
            const atual = parseFloat(preco);
            const maior = valores.length ? Math.max(...valores) : 0;
            if (maior > atual + 0.009) {
                obs = `Promoção: de ${formatarBR(maior)} por ${formatarBR(atual)}`;
            }
        }

        const semEstoque = /indispon|avise[\s-]?me|esgotad/i.test(boxTexto) || !/comprar/i.test(boxTexto);
        const estoque = semEstoque ? 'SEM_ESTOQUE' : 'EM_ESTOQUE';

        // O GTIN da Nissei vem com 14 dígitos (zero à esquerda): compara sem zeros.
        const semZeros = (t) => t.replace(/^0+/, '');

        GM_setValue('ean_buscado', '');
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }

        if (MODO_POR_NOME) {
            // Produto aceito pela SEMELHANÇA DE NOME (o EAN não bateu na busca).
            const obsNome = `Achado por NOME (EAN do site: ${gtin || '-'})` + obsEmbalagem(preco, nome) + (obs ? ' / ' + obs : '');
            GM_setClipboard(montarSentinel(eanBuscado, 'POR_NOME', preco, estoque, obsNome, nome));
            console.log('[assistente-ean] Nissei: preco POR NOME:', preco, 'EAN do site:', gtin);
        } else if (gtin && semZeros(gtin) !== semZeros(eanBuscado)) {
            GM_setClipboard(montarSentinel(eanBuscado, 'DIVERGENTE', preco, estoque, obs, `${nome} (gtin real: ${gtin})`));
            console.log('[assistente-ean] Nissei: EAN divergente. Buscado:', eanBuscado, 'Pagina:', gtin);
        } else {
            GM_setClipboard(montarSentinel(eanBuscado, 'OK', preco, estoque, obs, nome));
            console.log('[assistente-ean] Nissei: preco copiado:', preco, 'Obs:', obs || '(sem promo)');
        }

        encerrarAba();
    }

    // O site da Nissei mantém conexões abertas que seguram o evento 'load'
    // por minutos — por isso NÃO esperamos por ele: partimos direto do
    // document-idle com um pequeno atraso.
    console.log('[assistente-ean] Nissei v1.6 ativo em', location.pathname,
        EAN_DO_FRAGMENTO ? '(ean pendente: ' + EAN_DO_FRAGMENTO + ')' : '');
    setTimeout(() => {
        if (location.pathname.startsWith('/pesquisa')) {
            if (NOME_ESPERADO && EAN_DO_FRAGMENTO) {
                paginaDeBuscaPorNome();
            } else {
                paginaDeBusca();
            }
        } else {
            paginaDeProduto();
        }
    }, 900);
})();
