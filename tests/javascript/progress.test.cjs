const {test} = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const path = require('node:path');

function element() {
    return {
        listeners: {}, dataset: {startUrl: '/runs'}, disabled: false, hidden: true,
        textContent: '', classes: new Set(),
        children: [], scrollHeight: 0, scrollTop: 0, clientHeight: 0,
        append(...nodes) { this.children.push(...nodes); },
        replaceChildren() { this.children = []; },
        addEventListener(name, callback) { this.listeners[name] = callback; },
        get classList() { return {add: name => this.classes.add(name), remove: name => this.classes.delete(name)}; },
    };
}

function setup(responses, savedUrl) {
    const elements = Object.fromEntries(['research-form', 'submit-button', 'loading-overlay', 'progress-status', 'progress-error', 'activity-list', 'activity-empty'].map(id => [id, element()]));
    const timers = [], destinations = [], calls = [], storage = new Map();
    if (savedUrl) storage.set('investigationStatusUrl', savedUrl);
    const context = {
        document: {getElementById: id => elements[id], createElement: () => element()}, FormData: class {},
        fetch: async (url, options) => {
            calls.push({url, options});
            const response = responses.shift();
            if (response instanceof Error) throw response;
            assert.ok(response, 'Unexpected fetch');
            return {ok: true, json: async () => response, ...response};
        },
        window: {
            setTimeout: callback => timers.push(callback),
            location: {assign: url => destinations.push(url)},
            sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key)},
        },
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../static/progress.js'), 'utf8'), context);
    return {elements, timers, destinations, calls, storage,
        submit: () => elements['research-form'].listeners.submit({preventDefault() {}})};
}

const flush = () => new Promise(resolve => setImmediate(resolve));

test('submit, real status, repeated replanning and completion redirect', async () => {
    const page = setup([
        {status_url: '/runs/abc/status'},
        {status: 'running', message: 'Planning search'},
        {status: 'running', message: 'Replanning if needed'},
        {status: 'completed', message: 'Investigation complete', report_url: '/runs/abc/report'},
    ]);
    await page.submit(); await flush();
    assert.equal(page.elements['progress-status'].textContent, 'Planning search');
    assert.ok(page.elements['loading-overlay'].classes.has('visible'));
    await page.submit(); // Double submission is ignored.
    assert.equal(page.calls.filter(c => c.options.method === 'POST').length, 1);
    await page.timers.shift()(); await flush();
    assert.equal(page.elements['progress-status'].textContent, 'Replanning if needed');
    await page.timers.shift()(); await flush();
    assert.deepEqual(page.destinations, ['/runs/abc/report']);
    assert.equal(page.storage.size, 0);
    assert.equal(page.timers.length, 0);
});

test('failed run removes overlay, restores form and stops polling', async () => {
    const page = setup([{status_url: '/runs/abc/status'}, {status: 'failed', message: 'Please try again.'}]);
    await page.submit(); await flush();
    assert.equal(page.elements['submit-button'].disabled, false);
    assert.equal(page.elements['progress-error'].textContent, 'Please try again.');
    assert.equal(page.elements['progress-error'].hidden, false);
    assert.equal(page.elements['loading-overlay'].classes.has('visible'), false);
    assert.equal(page.timers.length, 0);
});

test('polling reconnects to the same run and survives page refresh', async () => {
    const page = setup([new Error('offline'), {status: 'running', message: 'Processing evidence'}], '/runs/abc/status');
    await flush();
    assert.match(page.elements['progress-status'].textContent, /Reconnecting/);
    await page.timers.shift()(); await flush();
    assert.equal(page.elements['progress-status'].textContent, 'Processing evidence');
    assert.ok(page.calls.every(call => call.url === '/runs/abc/status'));
    assert.equal(page.storage.get('investigationStatusUrl'), '/runs/abc/status');
});

test('missing run stops polling and allows a fresh investigation', async () => {
    const page = setup([{ok: false, status: 404}], '/runs/missing/status');
    await flush();
    assert.equal(page.timers.length, 0);
    assert.equal(page.storage.size, 0);
    assert.equal(page.elements['submit-button'].disabled, false);
});

test('start rejection shows server error and allows retry', async () => {
    const page = setup([{ok: false, error: 'Investigations are busy.'}]);
    await page.submit();
    assert.equal(page.elements['progress-error'].textContent, 'Investigations are busy.');
    assert.equal(page.elements['submit-button'].disabled, false);
});

test('activity preserves history, avoids duplicates and highlights current action', async () => {
    const started = {id: 1, component: 'Planner', action: 'started', cycle: 1, message: 'Planning search', timestamp: '2026-09-10T12:00:00Z'};
    const completed = {...started, id: 2, action: 'completed', message: 'Search plan prepared.'};
    const retrieval = {...started, id: 3, component: 'Retrieval', message: 'Retrieving academic sources'};
    const page = setup([
        {status: 'running', message: 'Planning search', events: [started]},
        {status: 'running', message: 'Retrieving academic sources', events: [started, completed, retrieval]},
        {status: 'running', message: 'Retrieving academic sources', events: [started, completed, retrieval]},
    ], '/runs/abc/status');
    await flush();
    const list = page.elements['activity-list'];
    assert.equal(list.children.length, 1);
    assert.equal(list.children[0].className, 'activity-step started');
    await page.timers.shift()(); await flush();
    assert.equal(list.children.length, 3);
    assert.equal(list.children[0].className, 'activity-step finished');
    assert.equal(list.children[0].children[1].textContent, 'Planning search');
    assert.equal(list.children[2].className, 'activity-step started');
    await page.timers.shift()(); await flush();
    assert.equal(list.children.length, 3);
    assert.equal(page.elements['activity-empty'].hidden, true);
});

test('tabs support click and keyboard selection with matching panel visibility', () => {
    const tabs = Array.from({length: 4}, element);
    const panels = Array.from({length: 4}, element);
    tabs.forEach((tab, index) => {
        tab.attributes = {'aria-controls': `panel-${index}`};
        tab.setAttribute = (key, value) => tab.attributes[key] = value;
        tab.getAttribute = key => tab.attributes[key];
        tab.focus = () => tab.focused = true;
    });
    const tablist = {hidden: true, querySelectorAll: () => tabs};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../../static/report-tabs.js'), 'utf8'), {
        document: {getElementById: id => id === 'report-tabs' ? tablist : panels[Number(id.slice(-1))]},
    });
    assert.equal(tablist.hidden, false);
    assert.equal(panels[0].hidden, false);
    assert.equal(panels[1].hidden, true);
    tabs[1].listeners.click();
    assert.equal(panels[0].hidden, true);
    assert.equal(panels[1].hidden, false);
    assert.equal(tabs[1].attributes['aria-selected'], 'true');
    tabs[1].listeners.keydown({key: 'End', preventDefault() {}});
    assert.equal(tabs[3].focused, true);
    assert.equal(panels[3].hidden, false);
    assert.ok(panels.slice(0, 3).every(panel => panel.hidden));
    tabs[3].listeners.keydown({key: 'ArrowRight', preventDefault() {}});
    assert.equal(tabs[0].focused, true);
    assert.equal(tabs[0].tabIndex, 0);
    assert.equal(tabs[1].tabIndex, -1);
    assert.equal(panels[0].hidden, false);
});


test('paper IDs in the live feed open the source in a new tab', async () => {
    const id = 'a'.repeat(20);
    const page = setup([{status_url:'/runs/a/status'}, {status:'running', message:'Processing', events:[{id:1, component:'Processing', action:'chunks_created', message:'Paper '+id+' ready', paper_id:id, paper_url:'https://doi.org/10.1234/test', display_timestamp:'Now'}]}]);
    await page.submit(); await flush();
    const message = page.elements['activity-list'].children[0].children[1];
    const link = message.children[1];
    assert.equal(link.textContent, id);
    assert.equal(link.href, 'https://doi.org/10.1234/test');
    assert.equal(link.target, '_blank');
    assert.equal(link.rel, 'noopener noreferrer');
});
