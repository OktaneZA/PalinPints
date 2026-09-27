// Exercise the real kiosk script with deterministic DOM measurements/timers.
// These tests verify behavior; they do not replace browser visual inspection.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { packPages } = require('../app/static/js/pagination.js');

function kiosk(width, height, reducedMotion = false) {
  function element(classes = [], rowHeight = 100) {
    const set = new Set(classes);
    return {
      style: {}, textContent: '', offsetHeight: rowHeight,
      classList: {
        add: name => set.add(name), remove: name => set.delete(name),
        contains: name => set.has(name),
        toggle(name, enabled) { if (enabled) set.add(name); else set.delete(name); },
      },
    };
  }
  const rows = Array.from({ length: 12 }, () => element(['beer-row']));
  const stage = element(), indicator = element(), clock = element();
  const header = element([], 32), categories = element();
  categories.clientHeight = 700;
  categories.querySelector = () => header;
  const body = element();
  body.dataset = { beersPerPage: '12', rotationInterval: '15', displayScale: '1', version: 'test' };
  const events = {}, intervals = new Map(), timeouts = [];
  let timerId = 0, fontReady, resized;
  const document = {
    body,
    fonts: { ready: { then(callback) { fontReady = callback; } } },
    querySelector: () => stage,
    getElementById: id => ({ categories, pageIndicator: indicator, clockNow: clock })[id],
    querySelectorAll(selector) {
      if (selector === '.beer-row, .tap-separator') return rows;
      if (selector.includes(':not(.is-hidden)')) return rows.filter(row => !row.classList.contains('is-hidden'));
      if (selector === '.is-fading-out') return rows.filter(row => row.classList.contains('is-fading-out'));
      throw new Error('Unexpected selector: ' + selector);
    },
  };
  const window = {
    innerWidth: width, innerHeight: height, packDisplayPages: packPages,
    matchMedia: () => ({ matches: reducedMotion }),
    addEventListener: (name, callback) => { events[name] = callback; },
  };
  const context = {
    window, document,
    getComputedStyle: () => ({ rowGap: '4px', marginTop: '0px', marginBottom: '0px' }),
    ResizeObserver: class { constructor(callback) { resized = callback; } observe() {} },
    setInterval: (callback, delay) => { intervals.set(++timerId, { callback, delay }); return timerId; },
    clearInterval: id => intervals.delete(id),
    setTimeout: callback => timeouts.push(callback),
    requestAnimationFrame: callback => callback(),
  };
  vm.runInNewContext(fs.readFileSync('app/static/js/display.js', 'utf8'), context);
  return {
    rows, stage, indicator, categories, window, events,
    visible: () => rows.filter(row => !row.classList.contains('is-hidden')),
    rotate: () => [...intervals.values()].find(timer => timer.delay === 15000).callback(),
    finishFade: () => { while (timeouts.length) timeouts.shift()(); },
    fontsLoaded: () => fontReady(),
    resized: () => resized(),
    rotationTimers: () => [...intervals.values()].filter(timer => timer.delay === 15000).length,
  };
}

test('720p, 1080p, 4K and 4:3 viewports use the same logical page capacity', () => {
  for (const [width, height, scale] of [[1280, 720, 2 / 3], [1920, 1080, 1], [3840, 2160, 2], [1024, 768, 1024 / 1920]]) {
    const screen = kiosk(width, height);
    assert.ok(screen.stage.style.transform.endsWith('scale(' + scale + ')'));
    assert.equal(screen.visible().length, 6);
    assert.equal(screen.indicator.textContent, '1 of 2');
    screen.rotate();
    screen.finishFade();
    assert.equal(screen.visible()[0], screen.rows[6]);
    assert.equal(screen.indicator.textContent, '2 of 2');
    screen.rotate();
    screen.finishFade();
    assert.equal(screen.visible()[0], screen.rows[0]);
  }
});
test('font loading repacks longer rows and retains one rotation timer', () => {
  const screen = kiosk(1920, 1080);
  screen.rows.forEach(row => { row.offsetHeight = 180; });
  screen.fontsLoaded();
  assert.equal(screen.visible().length, 3);
  assert.equal(screen.indicator.textContent, '1 of 4');
  assert.equal(screen.rotationTimers(), 1);
});
test('layout changes during a fade are applied after transition finishes', () => {
  const screen = kiosk(1920, 1080);
  screen.rotate();
  screen.categories.clientHeight = 350;
  screen.resized();
  screen.finishFade();
  assert.equal(screen.visible().length, 3);
  assert.equal(screen.indicator.textContent, '2 of 4');
  assert.equal(screen.rotationTimers(), 1);
});
test('reduced motion changes pages immediately without fading classes', () => {
  const screen = kiosk(1920, 1080, true);
  screen.rotate();
  assert.equal(screen.visible()[0], screen.rows[6]);
  assert.ok(screen.rows.every(row => !row.classList.contains('is-fading-out')));
});
