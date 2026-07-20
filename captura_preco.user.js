// ==UserScript==
// @name         Captura de Preço - Droga Raia (Assistente EAN)
// @namespace    consulta-precos-drogaraia
// @version      4.2
// @downloadURL  https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco.user.js
// @updateURL    https://raw.githubusercontent.com/Farmaciasassociadas/consulta-precos-scripts/main/captura_preco.user.js
// @description  Busca o EAN na Droga Raia, entra no produto, lê o preço via JSON-LD (com detecção de promoções) e copia para a área de transferência.
// @match        https://www.drogaraia.com.br/*
// @grant        GM_setClipboard
// @grant        GM_setValue
// @grant        GM_getValue
// @run-at       document-idle
// ==/UserScript==

(function () {
    'use strict';

    const SITE = 'drogaraia';

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

    // JSON-LD quebrado (caractere de controle na descrição) não parseia, mas
    // os campos simples continuam extraíveis por regex.
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
    //   EAN=<digitos>;SITE=drogaraia;STATUS=OK;PRECO=<valor>;ESTOQUE=EM_ESTOQUE|SEM_ESTOQUE;OBS=<texto>;NOME=<texto>
    //   EAN=<digitos>;SITE=drogaraia;STATUS=NAO_ENCONTRADO;PRECO=;ESTOQUE=;OBS=;NOME=
    //   EAN=<digitos>;SITE=drogaraia;STATUS=DIVERGENTE;PRECO=<valor>;ESTOQUE=...;OBS=<texto>;NOME=<texto>   (gtin da página != EAN buscado)
    // Pagina onde o preco foi encontrado: vai no protocolo (URL=) para o
    // assistente abrir DIRETO na conferencia manual (botao direito).
    let URL_DO_RESULTADO = '';

    function montarSentinel(ean, status, preco, estoque, obs, nome) {
        const limpar = (t) => (t || '').replace(/[;=\n\r]/g, ' ').replace(/\s+/g, ' ').trim();
        return `EAN=${ean};SITE=${SITE};STATUS=${status};PRECO=${preco || ''};ESTOQUE=${estoque || ''};OBS=${limpar(obs)};NOME=${limpar(nome)};URL=${(URL_DO_RESULTADO || '').replace(/[;\s]/g, '')}`;
    }

    function encerrarAba() {
        // Best-effort: só funciona se a aba foi aberta via window.open() pelo próprio script.
        // O fechamento real e confiável é feito pelo Python (Ctrl+W), então isso é só um bônus.
        setTimeout(() => {
            try { window.close(); } catch (e) { /* ignorado */ }
        }, 800);
    }

    // "R$ 1.299,90" -> "1299.90" (formato que o Python/Decimal entende)
    function extrairValorBR(texto) {
        const m = (texto || '').match(/R\$\s*([\d.]*\d,\d{2}|\d+(?:\.\d{1,2})?)/);
        if (!m) return '';
        const bruto = m[1];
        if (bruto.includes(',')) return bruto.replace(/\./g, '').replace(',', '.');
        return bruto;
    }

    // "7.9" -> "R$ 7,90" (para o texto de observação ficar legível)
    function formatarBR(precoStr) {
        const n = parseFloat(precoStr);
        if (isNaN(n)) return 'R$ ' + precoStr;
        return 'R$ ' + n.toFixed(2).replace('.', ',');
    }

    // Procura, no bloco de compra (subindo a partir de .product-price), duas coisas:
    //  - preço original riscado (promoção "de X por Y") — detectado pelo line-through,
    //    porque as classes do site são hasheadas e mudam a cada build;
    //  - frase de "leve mais pague menos" (ex.: "Leve 2 por R$ 4,00 cada", "Leve 3 pague 2").
    // Elementos dentro de <a>/<article>/<section> são ignorados: os carrosséis de
    // produtos relacionados também têm preços riscados e entrariam como falso positivo
    // (verificado ao vivo no site em 07/2026).
    const PADRAO_LEVE = /leve\s*\+?\s*\d+\s*(?:e\s*)?(?:pague\s*\d+|(?:unidades?\s*)?por\s*R\$\s*[\d.,]+(?:\s*cada)?|[^\n]{0,40}?R\$\s*[\d.,]+\s*cada)/i;

    function detectarPromocao() {
        const resultado = { precoOriginal: '', fraseLeve: '' };
        const precoEl = document.querySelector('.product-price');
        if (!precoEl) return resultado;

        let e = precoEl.parentElement;
        for (let nivel = 0; nivel < 6 && e && e !== document.body; nivel++, e = e.parentElement) {
            if (!resultado.precoOriginal) {
                for (const el of e.querySelectorAll('span, p, s, del')) {
                    if (el.children.length) continue;
                    if (el.closest('a, article, section')) continue; // carrossel, não é o bloco de compra
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
                // Remove carrosséis antes de ler o texto, pelo mesmo motivo acima.
                const copia = e.cloneNode(true);
                for (const lixo of copia.querySelectorAll('a, article, section')) lixo.remove();
                const m = (copia.textContent || '').match(PADRAO_LEVE);
                if (m) resultado.fraseLeve = m[0].replace(/\s+/g, ' ').trim();
            }
            if (resultado.precoOriginal && resultado.fraseLeve) break;
        }
        return resultado;
    }

    // A Raia embute TODOS os dados de promoção no estado da página:
    //   "price_aux":{"value_to":7.9,"value_from":9.9,"lmpm_value_to":null,"lmpm_qty":null}
    //   (desconto simples: de 9,90 por 7,90)
    //   "price_aux":{"value_to":54,"value_from":54,"lmpm_value_to":45.9,"lmpm_qty":2}
    //   (leve 2 por 45,90 cada)
    // Esta é a fonte PRINCIPAL: não depende do bloco visual de preço, que
    // renderiza depois e fazia a promoção escapar. Como produtos relacionados
    // também têm um bloco desses, usamos o que tem value_to igual ao preço do
    // JSON-LD. (Verificado ao vivo em 07/2026.)
    function detectarPromocaoEstruturada(precoAtual) {
        const html = document.documentElement.outerHTML;
        const re = /"price_aux"\s*:\s*\{[^}]*?"value_to"\s*:\s*([\d.]+)\s*,\s*"value_from"\s*:\s*([\d.]+)\s*,\s*"lmpm_value_to"\s*:\s*([\d.]+|null)\s*,\s*"lmpm_qty"\s*:\s*(\d+|null)/g;
        const alvo = parseFloat(precoAtual);
        let m;
        while ((m = re.exec(html)) !== null) {
            if (Math.abs(parseFloat(m[1]) - alvo) < 0.005) {
                const valorDe = parseFloat(m[2]);
                return {
                    original: valorDe > alvo + 0.009 ? valorDe : null,
                    leveQtd: m[4] !== 'null' ? parseInt(m[4], 10) : null,
                    levePrecoCada: m[3] !== 'null' ? parseFloat(m[3]) : null,
                };
            }
        }
        return null;
    }

    // Regras combinadas com o operador:
    //  - Desconto simples (de X por Y): PRECO = promocional (JSON-LD já traz);
    //    OBS = "Promoção: de R$ X por R$ Y".
    //  - Leve N pague menos: PRECO = preço de 1 unidade (JSON-LD já traz);
    //    OBS = "Promoção: <frase do site> (preço de 1 unidade: R$ Y)".
    function montarObservacao(precoAtual, promoDom, nome, promoEst) {
        const partes = [];

        // Desconto simples: fonte principal = dados estruturados; o preço
        // riscado do DOM fica como reserva (ele renderiza tarde).
        let original = '';
        if (promoEst && promoEst.original) {
            original = String(promoEst.original);
        } else if (promoDom.precoOriginal && parseFloat(promoDom.precoOriginal) > parseFloat(precoAtual)) {
            original = promoDom.precoOriginal;
        }
        if (original) {
            partes.push(`de ${formatarBR(original)} por ${formatarBR(precoAtual)}`);
        }

        if (promoEst && promoEst.leveQtd && promoEst.levePrecoCada) {
            partes.push(
                `leve ${promoEst.leveQtd} por ${formatarBR(promoEst.levePrecoCada)} cada ` +
                `(preço de 1 unidade: ${formatarBR(precoAtual)})`
            );
        } else if (promoDom.fraseLeve && !(nome || '').toLowerCase().includes(promoDom.fraseLeve.toLowerCase())) {
            // Fallback por texto. Ignora "Leve 2 Pague 1" quando faz parte do
            // NOME do produto (kits que já vêm nomeados assim).
            partes.push(`${promoDom.fraseLeve} (preço de 1 unidade: ${formatarBR(precoAtual)})`);
        }
        if (!partes.length) return '';
        // " / " como separador: ";" seria removido pela sanitização do protocolo
        return 'Promoção: ' + partes.join(' / ');
    }

    // Sinal de vida para o assistente: confirma que o script está instalado
    // e rodou nesta página (o Python só loga, não grava).
    let pingEnviado = false;
    function enviarPing(ean) {
        if (pingEnviado) return;
        pingEnviado = true;
        GM_setClipboard(`EAN=${ean};SITE=${SITE};STATUS=PING;PRECO=;ESTOQUE=;OBS=;NOME=`);
    }

    let tentativasBusca = 0;

    function paginaDeBusca() {
        const params = new URLSearchParams(location.search);
        const eanBuscado = params.get('w');
        if (!eanBuscado) return;
        enviarPing(eanBuscado);

        // Produto PRIMEIRO: se há card, usa — não importa qualquer texto
        // transitório na página.
        const link = document.querySelector('[data-testid="container-products"] article a[href]');
        if (link) {
            GM_setValue('ean_buscado', eanBuscado); // reserva, caso o fragmento se perca
            location.href = link.href + '#assistente_ean=' + eanBuscado;
            return;
        }

        // Sem card ainda. A página SPA da Raia mostra "Não encontramos
        // resultados" ENQUANTO hidrata, mesmo para produtos que existem
        // (falso negativo real de 07/2026, agravado quando o Chrome estava
        // sobrecarregado de abas). Só concluímos NAO_ENCONTRADO se o texto
        // PERSISTIR por algumas tentativas (dando tempo de renderizar).
        tentativasBusca++;
        const semResultado = document.body.innerText.includes('Não encontramos resultados');
        if (semResultado && tentativasBusca >= 5) {
            GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
            console.log('[assistente-ean] Nao encontrado (confirmado apos', tentativasBusca, 'tentativas):', eanBuscado);
            encerrarAba();
            return;
        }
        if (tentativasBusca > 30) {
            // ~15s sem card e sem texto claro: deixa o assistente dar timeout
            // (item fica pendente, não vira falso "não achou").
            console.log('[assistente-ean] Raia: busca sem card e sem texto claro — aguardando timeout');
            return;
        }
        setTimeout(paginaDeBusca, 500);
    }

    // ---- Busca por NOME (retaguarda) ----

    let tentativasNome = 0;

    function paginaDeBuscaPorNome() {
        enviarPing(EAN_DO_FRAGMENTO);
        const semResultado = document.body.innerText.includes('Não encontramos resultados');
        const candidatos = [...document.querySelectorAll('[data-testid="container-products"] article')]
            .map(art => {
                const a = art.querySelector('a[href]');
                return a ? { url: a.href, texto: art.innerText || '' } : null;
            }).filter(Boolean);

        if (!candidatos.length) {
            tentativasNome++;
            if (semResultado || tentativasNome > 20) {
                GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Raia: busca por nome sem resultados');
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
            console.log('[assistente-ean] Raia: nenhum candidato parecido o bastante (melhor:', melhorNota.toFixed(2), ')');
            GM_setClipboard(montarSentinel(EAN_DO_FRAGMENTO, 'NAO_ENCONTRADO', '', '', '', ''));
            encerrarAba();
            return;
        }
        console.log('[assistente-ean] Raia: candidato por nome aceito (nota', melhorNota.toFixed(2), ')');
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
                    console.log('[assistente-ean] Raia: JSON-LD quebrado, campos recuperados por regex');
                    produto = recuperado;
                    break;
                }
            }
        }

        if (!produto || !produto.offers || !produto.offers.price) {
            // Página 404 (a busca da Raia às vezes lista cards com link morto):
            // conclui como NAO_ENCONTRADO na hora, sem esperar o timeout.
            if (/página não encontrada|page not found/i.test(document.body.innerText)) {
                GM_setValue('ean_buscado', '');
                GM_setClipboard(montarSentinel(eanBuscado, 'NAO_ENCONTRADO', '', '', '', ''));
                console.log('[assistente-ean] Raia: pagina 404 — NAO_ENCONTRADO para', eanBuscado);
                encerrarAba();
                return;
            }
            // Só registra INDISPONIVEL quando o SITE DIZ isso explicitamente —
            // sem o texto, continua tentando e deixa o assistente dar timeout
            // (fica em branco/pendente: foi erro, não indisponibilidade).
            tentativasProduto++;
            const textoIndisponivel = /pre[cç]o\s*indispon|produto\s*indispon/i.test(document.body.innerText);
            if (textoIndisponivel) {
                const nome = (produto && produto.name)
                    || ((document.querySelector('h1') || {}).innerText || '').trim();
                GM_setValue('ean_buscado', '');
                try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }
                GM_setClipboard(montarSentinel(eanBuscado, 'INDISPONIVEL', '', 'SEM_ESTOQUE', '', nome));
                console.log('[assistente-ean] Raia: preco INDISPONIVEL para', eanBuscado);
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
        const disponibilidade = (produto.offers.availability || '').toString();
        const estoque = disponibilidade.includes('InStock') ? 'EM_ESTOQUE' : 'SEM_ESTOQUE';

        const promoDom = detectarPromocao();
        const promoEst = detectarPromocaoEstruturada(preco);
        const obs = montarObservacao(preco, promoDom, nome, promoEst);

        GM_setValue('ean_buscado', ''); // limpa para não reaproveitar em navegação futura
        try { history.replaceState(null, '', location.pathname + location.search); } catch (e) { }

        // Compara sem zeros à esquerda: EANs de origem UPC vêm na lista como
        // "0020800750158" e o site pode publicar o gtin sem esses zeros.
        const semZeros = (t) => t.replace(/^0+/, '');

        if (MODO_POR_NOME) {
            // Produto aceito pela SEMELHANÇA DE NOME (o EAN não bateu na busca):
            // registra como POR_NOME, com o EAN real do site na observação.
            const obsNome = `Achado por NOME (EAN do site: ${gtin || '-'})` + obsEmbalagem(preco, nome) + (obs ? ' / ' + obs : '');
            GM_setClipboard(montarSentinel(eanBuscado, 'POR_NOME', preco, estoque, obsNome, nome));
            console.log('[assistente-ean] Preco POR NOME:', preco, 'EAN buscado:', eanBuscado, 'EAN do site:', gtin);
        } else if (gtin && semZeros(gtin) !== semZeros(eanBuscado)) {
            GM_setClipboard(montarSentinel(eanBuscado, 'DIVERGENTE', preco, estoque, obs, `${nome} (gtin real: ${gtin})`));
            console.log('[assistente-ean] EAN divergente. Buscado:', eanBuscado, 'Pagina:', gtin);
        } else {
            GM_setClipboard(montarSentinel(eanBuscado, 'OK', preco, estoque, obs, nome));
            console.log('[assistente-ean] Preco copiado:', preco, 'Estoque:', estoque, 'Obs:', obs || '(sem promo)');
        }

        encerrarAba();
    }

    // NAO esperar o evento 'load': a Raia mantem trackers/anuncios abertos e o
    // 'load' da PAGINA DO PRODUTO pode demorar mais que o timeout do assistente
    // (bug real de 07/2026: PING chegava da busca, mas o produto nunca emitia).
    // Rodamos a partir do document-idle; as funcoes ja re-tentam sozinhas.
    setTimeout(() => {
        if (location.pathname.startsWith('/search')) {
            if (NOME_ESPERADO && EAN_DO_FRAGMENTO) {
                paginaDeBuscaPorNome();
            } else {
                paginaDeBusca();
            }
        } else if (location.pathname.endsWith('.html')) {
            paginaDeProduto();
        }
    }, 600);
})();
