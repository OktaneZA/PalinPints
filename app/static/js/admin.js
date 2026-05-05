(() => {
  // ---- Brewery autocomplete ----------------------------------------------
  const breweryList = document.getElementById('brewery-list');
  if (breweryList) {
    fetch('/admin/api/breweries').then(r => r.json()).then(names => {
      breweryList.innerHTML = names.map(n => `<option value="${escapeAttr(n)}">`).join('');
    }).catch(() => { /* offline ok */ });
  }

  // ---- Sub-style datalist driven by category -----------------------------
  let SUBSTYLES = {};
  const substyleData = document.getElementById('substyle-data');
  if (substyleData) {
    try { SUBSTYLES = JSON.parse(substyleData.textContent || '{}'); } catch (e) {}
  }

  function refreshSubstyleOptions(form) {
    const driver = form.querySelector('[data-substyle-driver]');
    const list = form.querySelector('[data-substyle-options]');
    if (!driver || !list) return;
    const options = SUBSTYLES[driver.value] || [];
    list.innerHTML = options.map(s => `<option value="${escapeAttr(s)}">`).join('');
  }

  document.querySelectorAll('form[data-tap-form]').forEach(form => {
    refreshSubstyleOptions(form);
    const driver = form.querySelector('[data-substyle-driver]');
    if (driver) driver.addEventListener('change', () => refreshSubstyleOptions(form));
  });

  // ---- Untappd multi-result search ---------------------------------------
  document.querySelectorAll('[data-untappd-search]').forEach(btn => {
    btn.addEventListener('click', async ev => {
      const form = ev.target.closest('form[data-tap-form]');
      if (!form) return;
      const status = form.querySelector('[data-untappd-status]');
      const resultsBox = form.querySelector('[data-untappd-results]');
      const beerInput = form.querySelector('[data-field="beer_name"]');
      const breweryInput = form.querySelector('[data-field="brewery"]');
      const query = [breweryInput?.value, beerInput?.value].filter(Boolean).join(' ').trim();

      if (!query) {
        showStatus(status, 'Type a brewery and/or beer name first.', 'error');
        return;
      }

      btn.disabled = true;
      showStatus(status, 'Searching Untappd…', '');
      resultsBox.hidden = true;
      resultsBox.innerHTML = '';

      try {
        const r = await fetch('/admin/api/untappd/search?q=' + encodeURIComponent(query));
        const data = await r.json();

        if (data.error && (!data.results || !data.results.length)) {
          showStatus(status,
            `No matches on Untappd${data.error ? ' (' + data.error + ')' : ''} — fill the fields manually below.`,
            'error');
          return;
        }
        renderResultsPicker(form, status, resultsBox, data.results || []);
      } catch (e) {
        showStatus(status, 'Network error talking to Untappd.', 'error');
      } finally {
        btn.disabled = false;
      }
    });
  });

  function renderResultsPicker(form, status, resultsBox, results) {
    if (!results.length) {
      showStatus(status, 'No matches — fill in manually.', 'error');
      return;
    }
    const items = results.map((hit, i) => `
      <li class="untappd-result" data-idx="${i}">
        <div class="ur-thumb">${hit.thumbnail_url ? `<img src="${escapeAttr(hit.thumbnail_url)}" alt="">` : ''}</div>
        <div class="ur-main">
          <div class="ur-name">${escapeHTML(hit.beer_name || '(no name)')}</div>
          <div class="ur-meta">
            ${hit.brewery ? `<span>${escapeHTML(hit.brewery)}</span>` : ''}
            ${hit.sub_style ? `<span>${escapeHTML(hit.sub_style)}</span>` : ''}
            ${hit.abv != null ? `<span>${hit.abv}% ABV</span>` : ''}
            ${hit.ibu != null ? `<span>${hit.ibu} IBU</span>` : ''}
          </div>
        </div>
        <button type="button" class="btn btn-primary" data-pick="${i}">Use this</button>
      </li>
    `).join('');

    resultsBox.innerHTML = `
      <div class="ur-header">${results.length} result${results.length === 1 ? '' : 's'} from Untappd — pick one to autofill, or close and edit manually.</div>
      <ul class="untappd-result-list">${items}</ul>
      <button type="button" class="btn btn-secondary" data-untappd-close>None match — close</button>
    `;
    resultsBox.hidden = false;
    showStatus(status, '', '');

    resultsBox.querySelectorAll('[data-pick]').forEach(b =>
      b.addEventListener('click', () => applyResult(form, status, resultsBox, results[+b.dataset.pick]))
    );
    resultsBox.querySelector('[data-untappd-close]')?.addEventListener('click', () => {
      resultsBox.hidden = true;
      resultsBox.innerHTML = '';
    });
  }

  async function applyResult(form, status, resultsBox, hit) {
    if (!hit) return;
    showStatus(status, 'Applying…', '');
    resultsBox.hidden = true;
    resultsBox.innerHTML = '';

    // Untappd-driven fields: always overwrite, clearing whatever was there.
    // This prevents stale values (e.g. previous beer's location) lingering
    // when Untappd has no data for the new pick.
    setField(form, 'brewery', hit.brewery);
    setField(form, 'beer_name', hit.beer_name);
    setField(form, 'sub_style', hit.sub_style);
    setField(form, 'abv', hit.abv);
    setField(form, 'ibu', hit.ibu);
    setField(form, 'untappd_slug', hit.untappd_slug);
    // Search results never include location; clear so detail fetch fills it.
    setField(form, 'location', '');

    autoSelectCategoryFromSubstyle(form, hit.sub_style);

    // Detail fetch resolves location + downloads brewery logo, and may
    // refine ABV/IBU/sub_style with values from the beer page.
    if (hit.untappd_slug) {
      try {
        const r = await fetch('/admin/api/untappd/select?slug=' + encodeURIComponent(hit.untappd_slug));
        const detail = await r.json();
        if (detail && !detail.error) {
          if (detail.brewery)   setField(form, 'brewery', detail.brewery);
          if (detail.beer_name) setField(form, 'beer_name', detail.beer_name);
          if (detail.sub_style) setField(form, 'sub_style', detail.sub_style);
          if (detail.abv != null) setField(form, 'abv', detail.abv);
          if (detail.ibu != null) setField(form, 'ibu', detail.ibu);
          if (detail.location)  setField(form, 'location', detail.location);
        }
      } catch (e) { /* basic fields already applied; swallow */ }
    }
    showStatus(status, 'Filled from Untappd. Add prices and Save.', 'success');
  }

  // Always overwrites the field, including clearing it when value is null/empty.
  function setField(form, name, value) {
    const el = form.querySelector(`[data-field="${name}"]`);
    if (!el) return;
    el.value = (value == null) ? '' : value;
  }

  function autoSelectCategoryFromSubstyle(form, substyle) {
    // Always re-evaluate when an Untappd result is applied — the previous
    // category may belong to the previous beer on this row.
    const driver = form.querySelector('[data-substyle-driver]');
    if (!driver || !substyle) return;
    const lc = substyle.toLowerCase();
    for (const [cat, options] of Object.entries(SUBSTYLES)) {
      if (options.some(o => o.toLowerCase() === lc)) {
        driver.value = cat;
        refreshSubstyleOptions(form);
        return;
      }
    }
    // Loose match — Untappd's sub-style strings often contain a clear keyword.
    // Order matters: more-specific keywords first, so "Belgian Strong Pale
    // Ale" wins Belgian over IPA, and "Lambic" wins Sour over its style hints.
    const guesses = [
      [/saison|tripel|dubbel|quadrupel|witbier|trappist|farmhouse|belgian|bi[èe]re\s+de\s+garde/i, 'Belgian & Farmhouse'],
      [/sour|wild|gose|lambic|brett|berliner|flanders/i, 'Sour & Wild Ales'],
      [/stout|porter/i, 'Stout & Porter'],
      [/\bipa\b|pale\s+ale|blonde\s+ale|cream\s+ale/i, 'IPA & Pale Ales'],
      [/lager|pilsner|helles|bock|m[äa]rzen|k[öo]lsch|altbier|schwarz/i, 'Lager & Pilsner'],
    ];
    for (const [re, cat] of guesses) {
      if (re.test(lc)) { driver.value = cat; refreshSubstyleOptions(form); return; }
    }
    driver.value = 'Historical & Specialty';
    refreshSubstyleOptions(form);
  }

  function fillField(form, name, value) {
    if (value == null || value === '') return;
    const el = form.querySelector(`[data-field="${name}"]`);
    if (el) el.value = value;
  }

  function showStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = 'untappd-status' + (kind ? ' ' + kind : '');
  }

  function escapeAttr(s) {
    return String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  }
  function escapeHTML(s) { return escapeAttr(s); }
})();
