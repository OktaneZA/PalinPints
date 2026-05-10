(() => {
  const body = document.body;
  const beersPerPage = parseInt(body.dataset.beersPerPage || '12', 10);
  const rotationMs = (parseInt(body.dataset.rotationInterval || '15', 10)) * 1000;
  const pollMs = 5000;
  const STAGE_W = 1920, STAGE_H = 1080;
  const stage = document.querySelector('.stage');

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

  const rows = () => Array.from(document.querySelectorAll('.beer-row'));
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

  function paginate() {
    const all = rows();
    pageCount = Math.max(1, Math.ceil(all.length / beersPerPage));
    if (currentPage >= pageCount) currentPage = 0;
    all.forEach((row, i) => {
      const onThisPage = Math.floor(i / beersPerPage) === currentPage;
      row.classList.toggle('is-hidden', !onThisPage);
    });
    if (indicator) indicator.textContent = pageCount > 1 ? `${currentPage + 1} of ${pageCount}` : '';
  }

  function startRotation() {
    if (rotateTimer) clearInterval(rotateTimer);
    if (pageCount <= 1) return;
    rotateTimer = setInterval(() => {
      currentPage = (currentPage + 1) % pageCount;
      paginate();
    }, rotationMs);
  }

  async function pollState() {
    try {
      const r = await fetch('/api/state', { cache: 'no-store' });
      if (!r.ok) return;
      const data = await r.json();
      if (data.version_hash && data.version_hash !== currentVersion) {
        // Server state changed — easiest correct rerender is a reload.
        window.location.reload();
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
