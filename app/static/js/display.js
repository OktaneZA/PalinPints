(() => {
  const body = document.body;
  const beersPerPage = parseInt(body.dataset.beersPerPage || '12', 10);
  const rotationMs = (parseInt(body.dataset.rotationInterval || '15', 10)) * 1000;
  const pollMs = 5000;
  const STAGE_W = 1920, STAGE_H = 1080;
  const stage = document.querySelector('.stage');

  const FADE_MS = 250;
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fadeMs = reducedMotion ? 0 : FADE_MS;

  function rescale() {
    if (!stage) return;
    const userScale = parseFloat(body.dataset.displayScale || '1') || 1;
    const fit = Math.min(window.innerWidth / STAGE_W, window.innerHeight / STAGE_H);
    const scale = fit * userScale;
    const tx = Math.max(0, (window.innerWidth - STAGE_W * scale) / 2);
    const ty = Math.max(0, (window.innerHeight - STAGE_H * scale) / 2);
    stage.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
  }

  let currentVersion = body.dataset.version || '';
  let currentPage = 0;
  let pageCount = 1;
  let rotateTimer = null;
  let transitioning = false;

  const rows = () => Array.from(document.querySelectorAll('.beer-row, .tap-separator'));
  const indicator = document.getElementById('pageIndicator');
  const clockNowEl = document.getElementById('clockNow');

  function fmtDateTime(d) {
    const date = d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
    const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    return `${date}  ${time}`;
  }
  function tickClock() {
    if (clockNowEl) clockNowEl.textContent = fmtDateTime(new Date());
  }

  // Pack elements into pages, refusing to place a separator on the last
  // slot of a page (push it to the next page so it never orphans).
  function computePages() {
    const all = rows();
    const pageOf = new Map();
    let page = 0, slot = 0;
    for (const el of all) {
      const isSep = el.classList.contains('tap-separator');
      if (slot >= beersPerPage) { page++; slot = 0; }
      if (isSep && slot === beersPerPage - 1) { page++; slot = 0; }
      pageOf.set(el, page);
      slot++;
    }
    return { all, pageOf, count: Math.max(1, page + 1) };
  }

  function applyPage(pageMap) {
    const { all, pageOf } = pageMap || computePages();
    all.forEach((el) => {
      el.classList.toggle('is-hidden', pageOf.get(el) !== currentPage);
    });
    if (indicator) indicator.textContent = pageCount > 1 ? `${currentPage + 1} of ${pageCount}` : '';
  }

  function paginate() {
    const pm = computePages();
    pageCount = pm.count;
    if (currentPage >= pageCount) currentPage = 0;
    applyPage(pm);
  }

  function transitionToPage(targetPage) {
    if (transitioning) return;
    const pm = computePages();
    pageCount = pm.count;
    if (targetPage >= pageCount) targetPage = 0;
    if (targetPage === currentPage) return;

    if (fadeMs === 0) {
      currentPage = targetPage;
      applyPage(pm);
      return;
    }

    transitioning = true;
    const visible = Array.from(document.querySelectorAll(
      '.beer-row:not(.is-hidden), .tap-separator:not(.is-hidden)'
    ));
    visible.forEach((el) => el.classList.add('is-fading-out'));

    setTimeout(() => {
      currentPage = targetPage;
      applyPage(pm);
      // Now-hidden rows: drop the fading class so they don't carry
      // opacity:0 into a future appearance.
      document.querySelectorAll('.is-fading-out').forEach((el) => {
        el.classList.remove('is-fading-out');
      });
      // Newly visible rows: pin to opacity 0 (no transition) for one
      // frame, then drop the class so they transition back to 1.
      const newVisible = Array.from(document.querySelectorAll(
        '.beer-row:not(.is-hidden), .tap-separator:not(.is-hidden)'
      ));
      newVisible.forEach((el) => el.classList.add('is-pre-enter'));
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          newVisible.forEach((el) => el.classList.remove('is-pre-enter'));
          setTimeout(() => { transitioning = false; }, fadeMs);
        });
      });
    }, fadeMs);
  }

  function startRotation() {
    if (rotateTimer) clearInterval(rotateTimer);
    if (pageCount <= 1) return;
    rotateTimer = setInterval(() => {
      const next = (currentPage + 1) % pageCount;
      transitionToPage(next);
    }, rotationMs);
  }

  async function pollState() {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      if (data.version_hash && data.version_hash !== currentVersion) {
        // Server state changed — easiest correct rerender is a reload.
        // Fade the stage out first so the white flash of the reload is
        // covered by the body's theme background instead of the live UI.
        if (fadeMs === 0) {
          window.location.reload();
          return;
        }
        body.classList.add('is-leaving');
        setTimeout(() => window.location.reload(), fadeMs);
      }
    } catch (e) { /* offline; keep showing cached page */ }
  }

  rescale();
  window.addEventListener('resize', rescale);
  paginate();
  startRotation();
  tickClock();
  setInterval(tickClock, 1000);
  setInterval(pollState, pollMs);
})();
