(function () {
    const snapshots = new WeakMap();
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');

    function workspace() {
        return document.getElementById('verification-workspace');
    }

    function snapshot(root) {
        return {
            states: new Map(Array.from(root.querySelectorAll('[data-verification-state]'),
                card => [card.id, card.dataset.verificationState])),
            complete: root.dataset.phaseComplete === 'true',
            progress: root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow'),
            focusedId: document.activeElement?.closest('[data-verification-state]')?.id,
        };
    }

    function showError(root) {
        const message = root.querySelector('[data-verification-error]');
        if (message) message.hidden = false;
    }

    // Refresh the server-rendered workspace, including unlocks and history, without
    // losing the previous state needed to animate a genuine result transition.
    document.addEventListener('htmx:beforeOnLoad', function (event) {
        if (event.detail.xhr.getResponseHeader('X-Verification-Complete') !== 'true') return;
        const root = workspace();
        if (!root || !root.contains(event.detail.elt)) return;
        event.preventDefault();
        htmx.ajax('GET', window.location.pathname + window.location.search, {
            source: root,
            target: root,
            select: '#verification-workspace',
            swap: 'outerHTML',
        }).catch(() => showError(root));
    });

    document.addEventListener('htmx:beforeSwap', function (event) {
        const root = workspace();
        if (root && (event.detail.target === root || root.contains(event.detail.target))) {
            snapshots.set(event.detail.xhr, snapshot(root));
        }
    });

    document.addEventListener('htmx:afterSettle', function (event) {
        const before = snapshots.get(event.detail.xhr);
        if (!before) return;
        snapshots.delete(event.detail.xhr);
        const root = workspace();
        if (!root) return;
        const changed = Array.from(root.querySelectorAll('[data-verification-state]'))
            .filter(card => before.states.get(card.id) !== card.dataset.verificationState);
        const result = changed.find(card => before.states.get(card.id) === 'checking'
            && card.dataset.verificationState !== 'checking');
        const celebrate = !before.complete && root.dataset.phaseComplete === 'true';

        if (!reducedMotion.matches) {
            for (const card of changed) {
                card.classList.add('verification-enter');
                if (card.dataset.verificationState === 'passed') {
                    card.classList.add('verification-success');
                    card.closest('.verification-step')?.classList.add('verification-step-completed');
                }
            }
            if (celebrate) root.querySelector('[data-phase-celebration]')?.classList.add('verification-success');
            const bar = root.querySelector('[role="progressbar"]');
            if (bar && before.progress !== null && before.progress !== undefined
                && before.progress !== bar.getAttribute('aria-valuenow')) {
                bar.firstElementChild.animate([
                    { width: before.progress + '%' },
                    { width: bar.getAttribute('aria-valuenow') + '%' },
                ], { duration: 600, easing: 'ease-out' });
            }
        }

        if (result) {
            const passed = result.dataset.verificationState === 'passed';
            root.querySelector('[data-verification-announcement]').textContent = celebrate
                ? 'Phase verified. Every requirement is complete.'
                : passed ? 'Requirement verified. The next requirement is ready.'
                    : 'Verification finished. Review the result and next steps.';
        }
        // Only restore focus if the refreshed content removed the focused control.
        // Background polling must not pull a learner away from history or navigation.
        if (before.focusedId && (document.activeElement === document.body
            || document.activeElement === document.documentElement)) {
            const focusTarget = celebrate ? root.querySelector('[data-phase-celebration]')
                : document.getElementById(before.focusedId);
            focusTarget?.focus({ preventScroll: true });
        }
    });

    for (const name of ['htmx:responseError', 'htmx:sendError', 'htmx:timeout', 'htmx:swapError']) {
        document.addEventListener(name, function (event) {
            const root = workspace();
            if (root && (event.detail.elt === root || root.contains(event.detail.elt))) {
                showError(root);
            }
        });
    }
})();
