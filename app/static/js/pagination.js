/* Height-aware packing shared by the kiosk and the Node regression tests. */
(function (root) {
  function packPages(items, availableHeight, maxBeers, gap) {
    const pages = [];
    let page = [], height = 0, beers = 0;
    const flush = () => {
      if (page.length) pages.push(page);
      page = []; height = 0; beers = 0;
    };
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      // Keep a section heading with its first beer, even at a page boundary.
      const group = [item];
      if (item.separator && items[i + 1] && !items[i + 1].separator) {
        group.push(items[++i]);
      }
      const groupHeight = group.reduce((sum, row) => sum + row.height, 0) + gap * (group.length - 1);
      const groupBeers = group.filter(row => !row.separator).length;
      const nextHeight = height + (page.length ? gap : 0) + groupHeight;
      if (page.length && (nextHeight > availableHeight || beers + groupBeers > maxBeers)) flush();
      height += (page.length ? gap : 0) + groupHeight;
      beers += groupBeers;
      page.push(...group);
    }
    flush();
    return pages;
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { packPages };
  else root.packDisplayPages = packPages;
})(globalThis);
