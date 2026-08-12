/**
 * app/static/js/onboarding.js
 * Motor genérico de "tour guiado" (balões de ajuda passo a passo).
 *
 * Cada página registra seus próprios passos:
 *
 *   NomdoTour.register('imoveis', [
 *       {
 *           selector: '#imoveis-grid-principal',
 *           title: 'Seus imóveis',
 *           text: 'Aqui ficam todos os imóveis cadastrados...',
 *           position: 'bottom'   // 'top' | 'bottom' | 'left' | 'right' | 'auto' (padrão)
 *       },
 *       {
 *           selector: '#modalVisualizar .tabs-wrapper',
 *           title: 'Abas do imóvel',
 *           text: 'Alterne entre Detalhes e Estadias.',
 *           before: function () { visualizarImovel(algumId); },  // roda antes de procurar o elemento
 *           beforeDelay: 400      // ms de espera após before() (padrão 150ms)
 *       }
 *   ]);
 *
 * Cada passo aceita:
 *   - selector   (obrigatório) — seletor CSS do elemento a destacar.
 *                 Se não existir na tela (mesmo depois de before()), o
 *                 passo é pulado automaticamente — nunca quebra o tour.
 *   - title, text (obrigatório) — conteúdo do balão.
 *   - position   (opcional) — lado preferido do balão. Em telas
 *                 estreitas (<=640px) isso é ignorado; o balão vira um
 *                 cartão fixo na base da tela.
 *   - before()   (opcional) — função executada antes de mostrar o passo
 *                 (ex: abrir um modal, trocar de aba).
 *   - beforeDelay (opcional) — ms de espera após before(), pra dar
 *                 tempo de animações/renderização (padrão 150).
 *   - after()    (opcional) — função executada ao SAIR do passo (voltar
 *                 ou avançar), útil pra fechar algo que before() abriu.
 *   - padding    (opcional) — respiro (px) entre o elemento e o recorte
 *                 do spotlight (padrão 8).
 *
 * NomdoTour.start('imoveis')               — (re)inicia o tour manualmente.
 * NomdoTour.autoStartIfNeeded('imoveis')    — só inicia se a pessoa nunca
 *                                              tiver visto (ou "pulado")
 *                                              o tour desta página.
 */
(function () {
    'use strict';

    var registry = {};
    var state = {
        pageId: null,
        steps: [],
        index: 0,
        els: null
    };

    function storageKey(pageId) {
        return 'nomdo_tour_done_' + pageId;
    }

    function jaVisto(pageId) {
        try {
            return localStorage.getItem(storageKey(pageId)) === '1';
        } catch (e) {
            return false;
        }
    }

    function marcarVisto(pageId) {
        try {
            localStorage.setItem(storageKey(pageId), '1');
        } catch (e) { /* localStorage indisponível — sem problema */ }
    }

    function register(pageId, steps, options) {
        registry[pageId] = {
            steps: steps || [],
            options: options || {}
        };
    }

    function isRegistered(pageId) {
        return !!(registry[pageId] && registry[pageId].steps.length);
    }

    // ── construção da UI (uma vez só, reaproveitada entre tours) ────────

    function buildUI() {
        if (state.els) return state.els;

        var backdrop = document.createElement('div');
        backdrop.className = 'nomdo-tour-backdrop';

        var spot = document.createElement('div');
        spot.className = 'nomdo-tour-spot';

        var bubble = document.createElement('div');
        bubble.className = 'nomdo-tour-bubble';
        bubble.setAttribute('role', 'dialog');
        bubble.setAttribute('aria-live', 'polite');
        bubble.innerHTML =
            '<div class="nomdo-tour-progress"></div>' +
            '<h4 class="nomdo-tour-title"><i class="fa-solid fa-lightbulb"></i><span></span></h4>' +
            '<p class="nomdo-tour-text"></p>' +
            '<div class="nomdo-tour-dots"></div>' +
            '<div class="nomdo-tour-actions">' +
                '<button type="button" class="nomdo-tour-skip">Pular tour</button>' +
                '<div class="nomdo-tour-nav">' +
                    '<button type="button" class="nomdo-tour-back">Voltar</button>' +
                    '<button type="button" class="nomdo-tour-next">Próximo</button>' +
                '</div>' +
            '</div>';

        document.body.appendChild(backdrop);
        document.body.appendChild(spot);
        document.body.appendChild(bubble);

        var els = {
            backdrop: backdrop,
            spot: spot,
            bubble: bubble,
            progress: bubble.querySelector('.nomdo-tour-progress'),
            title: bubble.querySelector('.nomdo-tour-title span'),
            text: bubble.querySelector('.nomdo-tour-text'),
            dots: bubble.querySelector('.nomdo-tour-dots'),
            skipBtn: bubble.querySelector('.nomdo-tour-skip'),
            backBtn: bubble.querySelector('.nomdo-tour-back'),
            nextBtn: bubble.querySelector('.nomdo-tour-next')
        };

        els.skipBtn.addEventListener('click', function () { finish(true); });
        els.backBtn.addEventListener('click', back);
        els.nextBtn.addEventListener('click', next);
        backdrop.addEventListener('click', function (e) { e.stopPropagation(); });

        document.addEventListener('keydown', onKeydown);
        window.addEventListener('resize', onReposition);
        window.addEventListener('scroll', onReposition, true);

        state.els = els;
        return els;
    }

    function destroyUI() {
        if (!state.els) return;
        state.els.backdrop.remove();
        state.els.spot.remove();
        state.els.bubble.remove();
        document.removeEventListener('keydown', onKeydown);
        window.removeEventListener('resize', onReposition);
        window.removeEventListener('scroll', onReposition, true);
        state.els = null;
    }

    function onKeydown(e) {
        if (!state.active) return;
        if (e.key === 'Escape') { finish(true); }
        else if (e.key === 'ArrowRight' || e.key === 'Enter') { next(); }
        else if (e.key === 'ArrowLeft') { back(); }
    }

    function onReposition() {
        if (!state.active) return;
        var step = state.steps[state.index];
        if (!step) return;
        var el = document.querySelector(step.selector);
        if (el) posicionar(el, step);
    }

    // ── fluxo do tour ────────────────────────────────────────────────

    function start(pageId) {
        var entry = registry[pageId];
        if (!entry || !entry.steps.length) {
            avisoSemGuia();
            return false;
        }
        state.pageId = pageId;
        state.steps = entry.steps;
        state.index = 0;
        state.active = true;
        buildUI();
        document.body.style.overflow = document.body.style.overflow || '';
        showStep(0);
        return true;
    }

    function avisoSemGuia() {
        if (typeof Swal !== 'undefined') {
            Swal.fire({
                toast: true,
                position: 'bottom-end',
                icon: 'info',
                title: 'Ainda não há um guia pra esta página.',
                showConfirmButton: false,
                timer: 2600,
                timerProgressBar: true
            });
        }
    }

    function runAfterHook() {
        var prevStep = state.steps[state.index];
        if (prevStep && typeof prevStep.after === 'function') {
            try { prevStep.after(); } catch (e) { console.warn('NomdoTour: erro em after()', e); }
        }
    }

    function next() {
        if (state.index >= state.steps.length - 1) {
            finish(false);
            return;
        }
        runAfterHook();
        state.index += 1;
        showStep(state.index);
    }

    function back() {
        if (state.index <= 0) return;
        runAfterHook();
        state.index -= 1;
        showStep(state.index);
    }

    function finish(pulou) {
        runAfterHook();
        state.active = false;
        marcarVisto(state.pageId);
        destroyUI();
        if (typeof Swal !== 'undefined' && !pulou) {
            Swal.fire({
                toast: true,
                position: 'bottom-end',
                icon: 'success',
                title: 'Tour concluído!',
                text: 'Clique no botão de ajuda (❓) sempre que quiser rever.',
                showConfirmButton: false,
                timer: 3200,
                timerProgressBar: true
            });
        }
    }

    function showStep(index, tentativas) {
        tentativas = tentativas || 0;
        var step = state.steps[index];
        if (!step) { finish(false); return; }

        if (typeof step.before === 'function') {
            try { step.before(); } catch (e) { console.warn('NomdoTour: erro em before()', e); }
        }

        var delay = (step.beforeDelay != null) ? step.beforeDelay : 150;

        setTimeout(function () {
            var el = step.selector ? document.querySelector(step.selector) : null;

            if (!el && step.selector) {
                // Elemento não existe nessa página/estado — pula pro
                // próximo passo em vez de quebrar o tour. Tenta no
                // máximo uma vez por passo pra não travar em loop.
                if (tentativas === 0) {
                    console.warn('NomdoTour: elemento não encontrado, pulando passo:', step.selector);
                }
                if (index >= state.steps.length - 1) { finish(false); return; }
                state.index = index + 1;
                showStep(state.index);
                return;
            }

            renderStep(el, step, index);
        }, delay);
    }

    function renderStep(el, step, index) {
        var els = state.els;

        if (el && el.scrollIntoView) {
            try { el.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' }); } catch (e) {}
        }

        // pequena espera pro scroll suave assentar antes de medir a posição
        setTimeout(function () {
            posicionar(el, step);

            els.progress.textContent = 'Passo ' + (index + 1) + ' de ' + state.steps.length;
            els.title.textContent = step.title || '';
            els.text.textContent = step.text || '';

            els.dots.innerHTML = '';
            state.steps.forEach(function (_, i) {
                var dot = document.createElement('span');
                if (i === index) dot.className = 'nomdo-tour-dot--active';
                els.dots.appendChild(dot);
            });

            els.backBtn.disabled = (index === 0);
            els.nextBtn.textContent = (index === state.steps.length - 1) ? 'Concluir' : 'Próximo';

            els.bubble.classList.add('nomdo-tour-bubble--visible');
        }, 260);
    }

    function posicionar(el, step) {
        var els = state.els;
        var padding = (step.padding != null) ? step.padding : 8;
        var rect = el.getBoundingClientRect();

        var spotTop = Math.max(rect.top - padding, 4);
        var spotLeft = Math.max(rect.left - padding, 4);
        var spotWidth = rect.width + padding * 2;
        var spotHeight = rect.height + padding * 2;

        els.spot.style.top = spotTop + 'px';
        els.spot.style.left = spotLeft + 'px';
        els.spot.style.width = spotWidth + 'px';
        els.spot.style.height = spotHeight + 'px';

        // Em telas estreitas o CSS já fixa o balão embaixo (ver
        // onboarding.css); só precisamos posicionar no desktop.
        if (window.innerWidth <= 640) return;

        var bubbleRect = els.bubble.getBoundingClientRect();
        var bw = bubbleRect.width || 340;
        var bh = bubbleRect.height || 200;
        var gap = 16;
        var pos = step.position || 'auto';

        var espacoAbaixo = window.innerHeight - (spotTop + spotHeight);
        var espacoAcima = spotTop;
        var espacoDireita = window.innerWidth - (spotLeft + spotWidth);
        var espacoEsquerda = spotLeft;

        if (pos === 'auto') {
            if (espacoAbaixo >= bh + gap) pos = 'bottom';
            else if (espacoAcima >= bh + gap) pos = 'top';
            else if (espacoDireita >= bw + gap) pos = 'right';
            else if (espacoEsquerda >= bw + gap) pos = 'left';
            else pos = 'bottom';
        }

        var top, left;
        if (pos === 'bottom') {
            top = spotTop + spotHeight + gap;
            left = spotLeft + (spotWidth / 2) - (bw / 2);
        } else if (pos === 'top') {
            top = spotTop - bh - gap;
            left = spotLeft + (spotWidth / 2) - (bw / 2);
        } else if (pos === 'right') {
            top = spotTop + (spotHeight / 2) - (bh / 2);
            left = spotLeft + spotWidth + gap;
        } else { // left
            top = spotTop + (spotHeight / 2) - (bh / 2);
            left = spotLeft - bw - gap;
        }

        // trava dentro da viewport com uma margem de 12px
        top = Math.min(Math.max(top, 12), window.innerHeight - bh - 12);
        left = Math.min(Math.max(left, 12), window.innerWidth - bw - 12);

        els.bubble.style.top = top + 'px';
        els.bubble.style.left = left + 'px';
    }

    // ── auto-início na 1ª visita ─────────────────────────────────────

    function autoStartIfNeeded(pageId) {
        var entry = registry[pageId];
        if (!entry || !entry.steps.length) return;
        if (entry.options.autoStart === false) return;
        if (jaVisto(pageId)) return;
        setTimeout(function () { start(pageId); }, 900);
    }

    window.NomdoTour = {
        register: register,
        start: start,
        isRegistered: isRegistered,
        autoStartIfNeeded: autoStartIfNeeded
    };

    // Dispara sozinho quando o body tiver data-tour-page e o DOM
    // já estiver pronto (cada template registra seus passos antes
    // deste ponto, no próprio extra_js).
    document.addEventListener('DOMContentLoaded', function () {
        var pageId = document.body.getAttribute('data-tour-page');
        var fab = document.querySelector('.nomdo-help-fab');

        // Página sem tour registrado (ainda) — some com o botão em vez
        // de deixar um "?" que não faz nada ao clicar.
        if (fab && !isRegistered(pageId)) {
            fab.style.display = 'none';
        }

        if (pageId) window.NomdoTour.autoStartIfNeeded(pageId);
    });
})();
