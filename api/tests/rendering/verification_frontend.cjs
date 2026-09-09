const assert = require('node:assert/strict');
const listeners = new Map();
const reduced = process.argv[3] === 'true';
const ajaxCalls = [];
const progressAnimations = [];
const announcement = { textContent: '' };
const error = { hidden: true };
const celebration = { classList: new Set() };
const bar = {
    value: '0',
    getAttribute: () => bar.value,
    firstElementChild: { animate: frames => progressAnimations.push(frames) },
};
let cards = [];
function card(id, state) {
    const step = { classList: new Set() };
    return {
        id, dataset: { verificationState: state }, classList: new Set(),
        closest: () => step,
        focus() { document.activeElement = this; },
    };
}
const root = {
    dataset: { phaseComplete: 'false' },
    contains: element => cards.includes(element),
    querySelectorAll: () => cards,
    querySelector: selector => ({
        '[role="progressbar"]': bar,
        '[data-verification-announcement]': announcement,
        '[data-verification-error]': error,
        '[data-phase-celebration]': celebration,
    })[selector],
};
let currentRoot = root;
global.document = {
    body: {}, documentElement: {}, activeElement: null,
    getElementById: id => id === 'verification-workspace' ? currentRoot
        : cards.find(item => item.id === id),
    addEventListener: (name, fn) => listeners.set(name, fn),
};
global.window = {
    matchMedia: () => ({ matches: reduced }),
    location: { pathname: '/verifications/phase/1', search: '?history_page=2' },
};
global.htmx = {
    ajax: (...args) => { ajaxCalls.push(args); return Promise.resolve(); },
};
require(process.argv[2]);

function swap(next, { complete = false, progress = '0' } = {}) {
    const xhr = {};
    listeners.get('htmx:beforeSwap')({ detail: { target: root, xhr } });
    cards = next;
    root.dataset.phaseComplete = String(complete);
    bar.value = progress;
    document.activeElement = document.body;
    listeners.get('htmx:afterSettle')({ detail: { xhr } });
}

// Ordinary navigation has no prior verification state and must not celebrate.
cards = [card('first', 'passed')];
listeners.get('htmx:afterSettle')({ detail: { xhr: {} } });
assert.equal(cards[0].classList.size, 0);

cards = [card('first', 'not_started')];
document.activeElement = { closest: () => cards[0] };
swap([card('first', 'checking')]);
assert.equal(cards[0].classList.has('verification-enter'), !reduced);
assert.equal(document.activeElement, cards[0]);

document.activeElement = { closest: () => cards[0] };
swap([card('first', 'checking')]);
assert.equal(cards[0].classList.size, 0, 'polls must not replay entry');
assert.equal(announcement.textContent, '');

document.activeElement = { closest: () => cards[0] };
swap([card('first', 'passed'), card('second', 'not_started')], { progress: '50' });
assert.equal(cards[0].classList.has('verification-success'), !reduced);
assert.equal(cards[1].classList.has('verification-enter'), !reduced);
assert.equal(cards[0].closest().classList.has('verification-step-completed'), !reduced);
assert.equal(document.activeElement, cards[0]);
assert.match(announcement.textContent, /next requirement is ready/);
assert.equal(progressAnimations.length, reduced ? 0 : 1);
if (!reduced) assert.deepEqual(progressAnimations[0], [{ width: '0%' }, { width: '50%' }]);

// A result must not steal focus when the learner is reading elsewhere.
cards = [card('first', 'passed'), card('second', 'checking')];
document.activeElement = { closest: () => null };
swap([card('first', 'passed'), card('second', 'failed')], { progress: '50' });
assert.equal(document.activeElement, document.body);
assert.equal(cards[0].classList.size, 0);
assert.match(announcement.textContent, /Review the result/);
assert.equal(cards[1].classList.has('verification-success'), false);

cards = [card('first', 'passed'), card('second', 'checking')];
document.activeElement = { closest: () => null };
swap([card('first', 'passed'), card('second', 'passed')], { complete: true, progress: '100' });
assert.equal(celebration.classList.has('verification-success'), !reduced);
assert.match(announcement.textContent, /Every requirement is complete/);

function completion(header, element = cards[0]) {
    let cancelled = false;
    listeners.get('htmx:beforeOnLoad')({
        detail: { xhr: { getResponseHeader: () => header }, elt: element },
        preventDefault: () => { cancelled = true; },
    });
    return cancelled;
}
assert.equal(completion(null), false);
assert.equal(completion('true', {}), false, 'ignore stale detached polling responses');
assert.equal(completion('true'), true);
assert.equal(ajaxCalls.length, 1);
assert.equal(ajaxCalls[0][0], 'GET');
assert.equal(ajaxCalls[0][1], '/verifications/phase/1?history_page=2');
assert.equal(ajaxCalls[0][2].select, '#verification-workspace');
assert.equal(ajaxCalls[0][2].swap, 'outerHTML');
currentRoot = null;
assert.equal(completion('true'), false, 'retain reload fallback outside the workspace');
currentRoot = root;

for (const name of ['htmx:responseError', 'htmx:sendError', 'htmx:timeout', 'htmx:swapError']) {
    error.hidden = true;
    listeners.get(name)({ detail: { elt: {} } });
    assert.equal(error.hidden, true);
    listeners.get(name)({ detail: { elt: cards[0] } });
    assert.equal(error.hidden, false);
}
