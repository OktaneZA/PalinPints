const { test } = require('node:test');
const assert = require('node:assert/strict');
const { packPages } = require('../app/static/js/pagination.js');
const beer = (id, height = 100) => ({ id, height, separator: false });
const heading = (height = 50) => ({ id: 'guest-heading', height, separator: true });
const ids = pages => pages.map(page => page.map(row => row.id));

test('empty menu has no packed rows', () => {
  assert.deepEqual(packPages([], 800, 12, 4), []);
});
test('fits exact available height, including gaps', () => {
  assert.deepEqual(ids(packPages([beer(1), beer(2), beer(3)], 204, 12, 4)), [[1, 2], [3]]);
});
test('respects configured maximum even when more beers would fit', () => {
  assert.deepEqual(ids(packPages([beer(1), beer(2), beer(3)], 1000, 2, 4)), [[1, 2], [3]]);
});
test('long wrapped names move to the next page without losing a beer', () => {
  assert.deepEqual(ids(packPages([beer(1), beer(2, 180), beer(3)], 280, 12, 4)), [[1], [2], [3]]);
});
test('guest heading stays with its first beer at height boundary', () => {
  assert.deepEqual(ids(packPages([beer(1), beer(2), heading(), beer(3)], 300, 12, 4)),
    [[1, 2], ['guest-heading', 3]]);
});
test('guest heading stays with first beer at count boundary', () => {
  assert.deepEqual(ids(packPages([beer(1), beer(2), heading(), beer(3)], 1000, 2, 4)),
    [[1, 2], ['guest-heading', 3]]);
});
test('heading does not consume a beer slot', () => {
  assert.deepEqual(ids(packPages([heading(), beer(1), beer(2)], 1000, 2, 4)),
    [['guest-heading', 1, 2]]);
});
test('oversized row is retained, with no empty pages or infinite loop', () => {
  assert.deepEqual(ids(packPages([beer(1, 1000), beer(2)], 800, 12, 4)), [[1], [2]]);
});
test('mixed menus preserve order and keep every feasible page within bounds', () => {
  for (const limit of [6, 8, 12, 14]) {
    for (const available of [650, 800, 900]) {
      const items = Array.from({ length: 40 }, (_, i) => beer(i, 80 + (i % 4) * 30));
      items.splice(13, 0, heading());
      const pages = packPages(items, available, limit, 4);
      assert.deepEqual(pages.flat(), items);
      for (const page of pages) {
        assert.ok(page.reduce((sum, row) => sum + row.height, 0) + (page.length - 1) * 4 <= available);
        assert.ok(page.filter(row => !row.separator).length <= limit);
        assert.equal(page.at(-1).separator, false);
      }
    }
  }
});
