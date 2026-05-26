(() => {
  // ---- Brewery autocomplete (datalist on Brewery input) -------------------
  const breweryList = document.getElementById('brewery-list');
  if (breweryList) {
    fetch('/admin/api/breweries').then(r => r.json()).then(names => {
      breweryList.innerHTML = names.map(n => `<option value="${escapeAttr(n)}">`).join('');
    }).catch(() => { /* offline ok */ });
  }

  // ---- Sub-style datalist driven by category ------------------------------
  let SUBSTYLES = {};
  const substyleData = document.getElementById('substyle-data');
  if (substyleData) {
    try { SUBSTYLES = JSON.parse(substyleData.textContent || '{}'); } catch (e) {}
  }

  function refreshSubstyleOptions(block) {
    const driver = block.querySelector('[data-substyle-driver]');
    const list = block.querySelector('[data-substyle-options]');
    if (!driver || !list) return;
    const options = SUBSTYLES[driver.value] || [];
    list.innerHTML = options.map(s => `<option value="${escapeAttr(s)}">`).join('');
  }

  // Each tap is a [data-tap-block] section inside the master taps form.
  const tapBlocks = document.querySelectorAll('[data-tap-block]');
  tapBlocks.forEach(block => {
    refreshSubstyleOptions(block);
    const driver = block.querySelector('[data-substyle-driver]');
    if (driver) driver.addEventListener('change', () => refreshSubstyleOptions(block));
  });

  // ---- Web search multi-result picker -------------------------------------
  document.querySelectorAll('[data-web-search]').forEach(btn => {
    btn.addEventListener('click', async ev => {
      const block = ev.target.closest('[data-tap-block]');
      if (!block) return;
      const status = block.querySelector('[data-web-search-status]');
      const resultsBox = block.querySelector('[data-web-search-results]');
      const beerInput = block.querySelector('[data-field="beer_name"]');
      const breweryInput = block.querySelector('[data-field="brewery"]');
      const query = [breweryInput?.value, beerInput?.value].filter(Boolean).join(' ').trim();

      if (!query) {
        showStatus(status, 'Type a brewery and/or beer name first.', 'error');
        return;
      }

      btn.disabled = true;
      showStatus(status, 'Searching the web…', '');
      resultsBox.hidden = true;
      resultsBox.innerHTML = '';

      try {
        const r = await fetch('/admin/api/web-search/search?q=' + encodeURIComponent(query));
        const data = await r.json();

        if (data.error && (!data.results || !data.results.length)) {
          showStatus(status,
            `No matches found${data.error ? ' (' + data.error + ')' : ''} — fill the fields manually below.`,
            'error');
          return;
        }
        renderResultsPicker(block, status, resultsBox, data.results || []);
      } catch (e) {
        showStatus(status, 'Network error during web search.', 'error');
      } finally {
        btn.disabled = false;
      }
    });
  });

  function renderResultsPicker(block, status, resultsBox, results) {
    if (!results.length) {
      showStatus(status, 'No matches — fill in manually.', 'error');
      return;
    }
    const items = results.map((hit, i) => `
      <li class="web-search-result" data-idx="${i}">
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
      <div class="ur-header">${results.length} result${results.length === 1 ? '' : 's'} found — pick one to autofill, or close and edit manually.</div>
      <ul class="web-search-result-list">${items}</ul>
      <button type="button" class="btn btn-secondary" data-web-search-close>None match — close</button>
    `;
    resultsBox.hidden = false;
    showStatus(status, '', '');

    resultsBox.querySelectorAll('[data-pick]').forEach(b =>
      b.addEventListener('click', () => applyResult(block, status, resultsBox, results[+b.dataset.pick]))
    );
    resultsBox.querySelector('[data-web-search-close]')?.addEventListener('click', () => {
      resultsBox.hidden = true;
      resultsBox.innerHTML = '';
    });
  }

  async function applyResult(block, status, resultsBox, hit) {
    if (!hit) return;
    showStatus(status, 'Applying…', '');
    resultsBox.hidden = true;
    resultsBox.innerHTML = '';

    setField(block, 'brewery', hit.brewery);
    setField(block, 'beer_name', hit.beer_name);
    setField(block, 'sub_style', hit.sub_style);
    setField(block, 'abv', hit.abv);
    setField(block, 'ibu', hit.ibu);
    setField(block, 'source_slug', hit.source_slug);
    setField(block, 'library_external_id', '');
    setField(block, 'location', '');
    // Clear any previous beer image — replaced by the new download below if
    // the selected hit has its own icon.
    setField(block, 'image_override_path', '');

    autoSelectCategoryFromSubstyle(block, hit.sub_style);

    if (hit.source_slug) {
      try {
        const params = new URLSearchParams({ slug: hit.source_slug });
        if (hit.thumbnail_url) params.set('thumbnail_url', hit.thumbnail_url);
        const r = await fetch('/admin/api/web-search/select?' + params.toString());
        const detail = await r.json();
        if (detail && !detail.error) {
          if (detail.brewery)   setField(block, 'brewery', detail.brewery);
          if (detail.beer_name) setField(block, 'beer_name', detail.beer_name);
          if (detail.sub_style) setField(block, 'sub_style', detail.sub_style);
          if (detail.abv != null) setField(block, 'abv', detail.abv);
          if (detail.ibu != null) setField(block, 'ibu', detail.ibu);
          if (detail.location)  setField(block, 'location', detail.location);
          if (detail.beer_image_local) setField(block, 'image_override_path', detail.beer_image_local);
        }
      } catch (e) { /* basic fields already applied; swallow */ }
    }
    showStatus(status, 'Filled from web search. Add prices and Save.', 'success');
  }

  function setField(scope, name, value) {
    const el = scope.querySelector(`[data-field="${name}"]`);
    if (!el) return;
    if (el.type === 'checkbox') {
      el.checked = !!value;
    } else {
      el.value = (value == null) ? '' : value;
    }
    // Programmatic assignment doesn't trigger 'input' on its own — the
    // unsaved-changes guard listens for it, so dispatch explicitly.
    el.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function autoSelectCategoryFromSubstyle(block, substyle) {
    const driver = block.querySelector('[data-substyle-driver]');
    if (!driver || !substyle) return;
    const lc = substyle.toLowerCase();
    for (const [cat, options] of Object.entries(SUBSTYLES)) {
      if (options.some(o => o.toLowerCase() === lc)) {
        setDriver(driver, cat, block);
        return;
      }
    }
    const guesses = [
      [/saison|tripel|dubbel|quadrupel|witbier|trappist|farmhouse|belgian|bi[èe]re\s+de\s+garde/i, 'Belgian & Farmhouse'],
      [/sour|wild|gose|lambic|brett|berliner|flanders/i, 'Sour & Wild Ales'],
      [/stout|porter/i, 'Stout & Porter'],
      [/\bipa\b|pale\s+ale|blonde\s+ale|cream\s+ale/i, 'IPA & Pale Ales'],
      [/lager|pilsner|helles|bock|m[äa]rzen|k[öo]lsch|altbier|schwarz/i, 'Lager & Pilsner'],
    ];
    for (const [re, cat] of guesses) {
      if (re.test(lc)) { setDriver(driver, cat, block); return; }
    }
    setDriver(driver, 'Historical & Specialty', block);
  }

  function setDriver(driver, cat, block) {
    driver.value = cat;
    driver.dispatchEvent(new Event('change', { bubbles: true }));
    refreshSubstyleOptions(block);
  }

  function showStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = 'web-search-status' + (kind ? ' ' + kind : '');
  }

  function escapeAttr(s) {
    return String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  }
  function escapeHTML(s) { return escapeAttr(s); }

  // ---- Beer-library typeahead on the Beer-name field ----------------------
  // Suggests beers from the local library as the user types. Selecting one
  // populates brewery, beer_name, style_category, sub_style, abv, ibu,
  // location and stores the external_id in a hidden field so future syncs
  // can re-resolve / show a "from library" badge.
  document.querySelectorAll('[data-bl-typeahead]').forEach(initLibraryTypeahead);

  function initLibraryTypeahead(input) {
    const block = input.closest('[data-tap-block]');
    if (!block) return;
    const dropdown = block.querySelector('[data-bl-typeahead-dropdown]');
    if (!dropdown) return;

    let debounceTimer = null;
    let activeIndex = -1;
    let currentResults = [];

    const hide = () => { dropdown.hidden = true; dropdown.innerHTML = ''; activeIndex = -1; };

    const render = (results) => {
      currentResults = results;
      if (!results.length) {
        dropdown.innerHTML = '<div class="bl-typeahead-empty">No matches in the local library — use “Search the web” or fill manually.</div>';
        dropdown.hidden = false;
        return;
      }
      dropdown.innerHTML = results.map((r, i) => `
        <div class="bl-typeahead-item" data-idx="${i}" tabindex="-1">
          <div class="bl-typeahead-main">
            <div class="bl-typeahead-name">${escapeHTML(r.beer_name || '(unnamed)')}
              ${r.is_home_brewery ? '<span class="bl-badge bl-badge-home">Home</span>' : ''}
              ${r.local_overridden ? '<span class="bl-badge bl-badge-override">Local edit</span>' : ''}
            </div>
            <div class="bl-typeahead-meta">
              ${r.brewery ? `<span>${escapeHTML(r.brewery)}</span>` : ''}
              ${r.sub_style ? `<span>${escapeHTML(r.sub_style)}</span>` : ''}
              ${r.abv != null ? `<span>${r.abv}% ABV</span>` : ''}
              ${r.ibu != null ? `<span>${r.ibu} IBU</span>` : ''}
            </div>
          </div>
        </div>
      `).join('');
      dropdown.hidden = false;
      dropdown.querySelectorAll('.bl-typeahead-item').forEach(el => {
        el.addEventListener('mousedown', (e) => {
          e.preventDefault();
          pick(currentResults[+el.dataset.idx]);
        });
      });
    };

    const fetchResults = async (q) => {
      try {
        const r = await fetch('/admin/api/beer-library/search?q=' + encodeURIComponent(q) + '&limit=10');
        const data = await r.json();
        render(data.results || []);
      } catch { hide(); }
    };

    const pick = (rec) => {
      if (!rec) return;
      setField(block, 'beer_name', rec.beer_name);
      setField(block, 'brewery', rec.brewery);
      setField(block, 'sub_style', rec.sub_style);
      setField(block, 'abv', rec.abv);
      setField(block, 'ibu', rec.ibu);
      setField(block, 'location', rec.location);
      setField(block, 'source_slug', rec.untappd_slug || '');
      setField(block, 'library_external_id', rec.external_id);
      const driver = block.querySelector('[data-substyle-driver]');
      if (driver && rec.style_category) {
        setDriver(driver, rec.style_category, block);
      } else if (rec.sub_style) {
        autoSelectCategoryFromSubstyle(block, rec.sub_style);
      }
      const status = block.querySelector('[data-tap-row-status]');
      if (status) {
        status.textContent = `Filled from Beer library: ${rec.brewery || ''} — ${rec.beer_name || ''}.`;
        status.classList.add('success');
      }
      hide();
    };

    input.addEventListener('input', () => {
      const q = input.value.trim();
      // Typing in beer name implies user is no longer using the prior
      // library-linked record — clear the external_id so a manual edit
      // doesn't keep a stale link.
      setField(block, 'library_external_id', '');
      if (debounceTimer) clearTimeout(debounceTimer);
      if (!q) { hide(); return; }
      debounceTimer = setTimeout(() => fetchResults(q), 180);
    });

    input.addEventListener('focus', () => {
      const q = input.value.trim();
      if (q) fetchResults(q);
    });

    input.addEventListener('keydown', (e) => {
      if (dropdown.hidden) return;
      const items = dropdown.querySelectorAll('.bl-typeahead-item');
      if (!items.length) return;
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIndex = (activeIndex + 1) % items.length;
        items.forEach((el, i) => el.classList.toggle('is-active', i === activeIndex));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIndex = (activeIndex - 1 + items.length) % items.length;
        items.forEach((el, i) => el.classList.toggle('is-active', i === activeIndex));
      } else if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault();
        pick(currentResults[activeIndex]);
      } else if (e.key === 'Escape') {
        hide();
      }
    });

    input.addEventListener('blur', () => {
      // Slight delay so a click on a dropdown item lands before we hide.
      setTimeout(hide, 120);
    });
  }

  // ---- Master "Save all taps" button --------------------------------------
  const tapsForm = document.querySelector('[data-taps-form]');
  const saveAllBtn = document.querySelector('[data-taps-save-all]');
  const saveAllStatus = document.querySelector('[data-taps-save-status]');

  // Unsaved-changes guard for the Taps page — warn before reload / close /
  // navigation when any field has been edited. Cleared when the bulk save
  // succeeds, or when the user submits an intentional form action (Clear
  // tap, per-tap image upload).
  let tapsDirty = false;
  const markTapsClean = () => { tapsDirty = false; };
  if (tapsForm) {
    const markDirty = () => { tapsDirty = true; };
    tapsForm.addEventListener('input', markDirty);
    tapsForm.addEventListener('change', markDirty);
    document.querySelectorAll('form').forEach(f => {
      if (f !== tapsForm) f.addEventListener('submit', markTapsClean);
    });
    window.addEventListener('beforeunload', (e) => {
      if (!tapsDirty) return;
      e.preventDefault();
      e.returnValue = '';
    });
  }

  if (tapsForm && saveAllBtn) {
    // Prevent native form submission — we serialize in JS.
    tapsForm.addEventListener('submit', (e) => e.preventDefault());
    saveAllBtn.addEventListener('click', async () => {
      saveAllBtn.disabled = true;
      const orig = saveAllBtn.textContent;
      saveAllBtn.textContent = 'Saving…';
      setSaveStatus('', '');
      // Clear per-tap row markers from any previous save.
      document.querySelectorAll('[data-tap-block]').forEach(b => {
        b.classList.remove('has-error');
        const s = b.querySelector('[data-tap-row-status]');
        if (s) { s.textContent = ''; s.className = 'tap-row-status'; }
      });

      const taps = Array.from(document.querySelectorAll('[data-tap-block]')).map(serializeTapBlock);

      try {
        const r = await fetch('/admin/taps/save-all', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ taps }),
        });
        const data = await r.json();
        if (!r.ok) {
          setSaveStatus(data.error || 'Save failed.', 'error');
        } else {
          setSaveStatus(data.message || 'Saved.', data.rejected && data.rejected.length ? 'error' : 'success');
          if (!(data.rejected && data.rejected.length)) markTapsClean();
          (data.rejected || []).forEach(rej => {
            const block = document.querySelector(`[data-tap-block][data-tap="${rej.tap_number}"]`);
            if (!block) return;
            block.classList.add('has-error');
            const s = block.querySelector('[data-tap-row-status]');
            if (s) {
              s.textContent = `Not saved — missing: ${rej.errors.join(', ')}.`;
              s.classList.add('error');
            }
          });
        }
      } catch (e) {
        setSaveStatus('Network error — taps not saved.', 'error');
      } finally {
        saveAllBtn.disabled = false;
        saveAllBtn.textContent = orig;
      }
    });
  }

  function serializeTapBlock(block) {
    const tapNumber = parseInt(block.dataset.tap, 10);
    const get = (name) => block.querySelector(`[name="${name}"]`);
    const checked = (name) => { const el = get(name); return !!(el && el.checked); };
    const value = (name) => { const el = get(name); return el ? el.value : ''; };
    return {
      tap_number: tapNumber,
      active: checked('active'),
      brewery: value('brewery'),
      beer_name: value('beer_name'),
      style_category: value('style_category'),
      sub_style: value('sub_style'),
      abv: value('abv'),
      ibu: value('ibu'),
      location: value('location'),
      price_third: value('price_third'),
      price_half: value('price_half'),
      price_pint: value('price_pint'),
      price_takeaway: value('price_takeaway'),
      price_third_enabled: checked('price_third_enabled'),
      price_half_enabled: checked('price_half_enabled'),
      price_pint_enabled: checked('price_pint_enabled'),
      price_takeaway_enabled: checked('price_takeaway_enabled'),
      source_slug: value('source_slug'),
      library_external_id: value('library_external_id'),
      image_override_path: value('image_override_path'),
    };
  }

  function setSaveStatus(text, kind) {
    if (!saveAllStatus) return;
    saveAllStatus.textContent = text;
    saveAllStatus.className = 'sticky-save-status' + (kind ? ' ' + kind : '');
  }

  // ---- Master save: Specials ---------------------------------------------
  wireMasterSave({
    formSel: '[data-specials-form]',
    btnSel: '[data-specials-save-all]',
    statusSel: '[data-specials-save-status]',
    rowSel: '[data-special-row]',
    endpoint: '/admin/specials/save-all',
    payloadKey: 'specials',
    serializeRow: (row) => ({
      id: parseInt(row.dataset.id, 10),
      title: row.querySelector('[name="title"]')?.value || '',
      description: row.querySelector('[name="description"]')?.value || '',
      price: row.querySelector('[name="price"]')?.value || '',
      active: !!row.querySelector('[name="active"]')?.checked,
    }),
    labelSingular: 'special',
  });

  // ---- Master save: Events -----------------------------------------------
  wireMasterSave({
    formSel: '[data-events-form]',
    btnSel: '[data-events-save-all]',
    statusSel: '[data-events-save-status]',
    rowSel: '[data-event-row]',
    endpoint: '/admin/events/save-all',
    payloadKey: 'events',
    serializeRow: (row) => ({
      id: parseInt(row.dataset.id, 10),
      name: row.querySelector('[name="name"]')?.value || '',
      event_date: row.querySelector('[name="event_date"]')?.value || '',
      location: row.querySelector('[name="location"]')?.value || '',
      url: row.querySelector('[name="url"]')?.value || '',
      active: !!row.querySelector('[name="active"]')?.checked,
    }),
    labelSingular: 'event',
  });

  function wireMasterSave({ formSel, btnSel, statusSel, rowSel, endpoint,
                            payloadKey, serializeRow, labelSingular }) {
    const form = document.querySelector(formSel);
    const btn = document.querySelector(btnSel);
    const status = document.querySelector(statusSel);
    if (!form || !btn) return;

    form.addEventListener('submit', (e) => e.preventDefault());
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      const orig = btn.textContent;
      btn.textContent = 'Saving…';
      setStickyStatus(status, '', '');
      form.querySelectorAll(rowSel).forEach(r => {
        r.classList.remove('has-error');
        const s = r.querySelector('[data-row-status]');
        if (s) { s.textContent = ''; s.className = 'row-status'; }
      });

      const rows = Array.from(form.querySelectorAll(rowSel)).map(serializeRow);
      try {
        const r = await fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ [payloadKey]: rows }),
        });
        const data = await r.json();
        if (!r.ok) {
          setStickyStatus(status, data.error || 'Save failed.', 'error');
        } else {
          setStickyStatus(status, data.message || 'Saved.',
                          data.rejected && data.rejected.length ? 'error' : 'success');
          (data.rejected || []).forEach(rej => {
            const row = form.querySelector(`${rowSel}[data-id="${rej.id}"]`);
            if (!row) return;
            row.classList.add('has-error');
            const s = row.querySelector('[data-row-status]');
            if (s) {
              s.textContent = `Not saved — ${rej.errors.join(', ')}.`;
              s.classList.add('error');
            }
          });
        }
      } catch {
        setStickyStatus(status, `Network error — ${labelSingular}s not saved.`, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = orig;
      }
    });
  }

  function setStickyStatus(el, text, kind) {
    if (!el) return;
    el.textContent = text;
    el.className = 'sticky-save-status' + (kind ? ' ' + kind : '');
  }

  // ---- Beer-library admin page --------------------------------------------
  const blSyncBtn = document.querySelector('[data-bl-sync-now]');
  const blLastSync = document.querySelector('[data-bl-last-sync]');
  const blLastStatus = document.querySelector('[data-bl-last-status]');
  const blStickyStatus = document.querySelector('[data-bl-sync-status]');

  if (blSyncBtn) {
    blSyncBtn.addEventListener('click', async () => {
      blSyncBtn.disabled = true;
      const orig = blSyncBtn.textContent;
      blSyncBtn.textContent = 'Queued — running…';
      setStickyStatus(blStickyStatus, 'Sync running…', '');
      try {
        await fetch('/admin/api/beer-library/sync', { method: 'POST' });
        await pollSyncStatus({ untilFinishedAfter: Date.now() });
        // Status changed; reload to show updated rows.
        window.location.reload();
      } catch {
        blSyncBtn.textContent = 'Sync failed';
        setStickyStatus(blStickyStatus, 'Sync failed — see status above.', 'error');
        setTimeout(() => { blSyncBtn.disabled = false; blSyncBtn.textContent = orig; }, 2000);
      }
    });
  }

  async function pollSyncStatus({ untilFinishedAfter }) {
    // Poll up to 15s waiting for last_sync_at to advance past untilFinishedAfter (sec)
    const deadline = Date.now() + 15000;
    const startSec = Math.floor(untilFinishedAfter / 1000);
    while (Date.now() < deadline) {
      try {
        const r = await fetch('/admin/api/beer-library/status');
        const data = await r.json();
        if (data.last_sync_at && data.last_sync_at >= startSec) {
          if (blLastSync) blLastSync.textContent = data.last_sync_at;
          if (blLastStatus) blLastStatus.textContent = data.last_sync_status || '—';
          return;
        }
      } catch {}
      await new Promise(res => setTimeout(res, 700));
    }
  }

  // Inline edit toggles on the library page.
  document.querySelectorAll('[data-bl-edit]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      const row = ev.target.closest('tr');
      const editRow = row && row.nextElementSibling;
      if (editRow && editRow.matches('[data-bl-edit-row]')) {
        editRow.hidden = !editRow.hidden;
      }
    });
  });
  document.querySelectorAll('[data-bl-cancel]').forEach(btn => {
    btn.addEventListener('click', (ev) => {
      const editRow = ev.target.closest('[data-bl-edit-row]');
      if (editRow) editRow.hidden = true;
    });
  });

  document.querySelectorAll('[data-bl-edit-form]').forEach(form => {
    form.addEventListener('submit', async (ev) => {
      ev.preventDefault();
      const editRow = form.closest('[data-bl-edit-row]');
      const headRow = editRow ? editRow.previousElementSibling : null;
      const externalId = headRow && headRow.dataset.externalId;
      if (!externalId) return;
      const statusEl = form.querySelector('[data-bl-edit-status]');
      const data = {};
      ['beer_name', 'brewery', 'style_category', 'sub_style', 'location',
       'description', 'abv', 'ibu'].forEach(n => {
        const el = form.querySelector(`[name="${n}"]`);
        if (el) data[n] = el.value;
      });
      data.is_home_brewery = !!form.querySelector('[name="is_home_brewery"]')?.checked;

      if (statusEl) { statusEl.textContent = 'Saving…'; statusEl.className = 'bl-edit-status'; }
      try {
        const r = await fetch(`/admin/api/beer-library/${encodeURIComponent(externalId)}/edit`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
        const result = await r.json();
        if (!r.ok) {
          if (statusEl) { statusEl.textContent = result.error || 'Save failed.'; statusEl.classList.add('error'); }
        } else {
          if (statusEl) { statusEl.textContent = 'Saved — refreshing…'; statusEl.classList.add('success'); }
          setTimeout(() => window.location.reload(), 400);
        }
      } catch {
        if (statusEl) { statusEl.textContent = 'Network error.'; statusEl.classList.add('error'); }
      }
    });
  });

  document.querySelectorAll('[data-bl-reset]').forEach(btn => {
    btn.addEventListener('click', async (ev) => {
      const row = ev.target.closest('tr');
      const externalId = row && row.dataset.externalId;
      if (!externalId) return;
      if (!confirm('Reset this beer to the external source values? Your local edits will be lost.')) return;
      btn.disabled = true;
      const orig = btn.textContent;
      btn.textContent = 'Resyncing…';
      const startedAt = Date.now();
      try {
        const r = await fetch(`/admin/api/beer-library/${encodeURIComponent(externalId)}/reset`, { method: 'POST' });
        if (!r.ok) {
          btn.disabled = false;
          btn.textContent = orig;
          return;
        }
        // Reset clears the override and wakes the sync worker; wait for the
        // next sync pass to finish before reloading so the row shows fresh
        // source values rather than the cleared-but-not-resynced state.
        await pollSyncStatus({ untilFinishedAfter: startedAt });
        window.location.reload();
      } catch {
        btn.disabled = false;
        btn.textContent = orig;
      }
    });
  });

  // (Settings auto-locate handler lives in settings.html's inline script.)

  // ---- DB backup + restore (Settings page) --------------------------------
  const backupNowBtn = document.querySelector('[data-backup-now]');
  const backupRestoreBtn = document.querySelector('[data-backup-restore]');
  const backupStatus = document.querySelector('[data-backup-status]');
  const backupModifiedEl = document.querySelector('[data-backup-modified]');
  const backupSizeEl = document.querySelector('[data-backup-size]');

  const setBackupStatus = (text, kind) => {
    if (!backupStatus) return;
    backupStatus.textContent = text;
    backupStatus.className = 'backup-status' + (kind ? ' ' + kind : '');
  };

  const fmtDateTime = (epochSec) => {
    if (!epochSec) return '';
    const d = new Date(epochSec * 1000);
    return d.toLocaleString();
  };

  // Hydrate the timestamp into a readable date on page load.
  if (backupModifiedEl && /^\d+$/.test(backupModifiedEl.textContent.trim())) {
    const epoch = parseInt(backupModifiedEl.textContent.trim(), 10);
    backupModifiedEl.textContent = fmtDateTime(epoch);
  }

  if (backupNowBtn) {
    backupNowBtn.addEventListener('click', async () => {
      backupNowBtn.disabled = true;
      const orig = backupNowBtn.textContent;
      backupNowBtn.textContent = 'Backing up…';
      setBackupStatus('Running backup…', '');
      try {
        const r = await fetch('/admin/api/backup/now', { method: 'POST' });
        const data = await r.json();
        if (r.ok && data.ok) {
          if (backupModifiedEl) backupModifiedEl.textContent = fmtDateTime(data.modified_at);
          if (backupSizeEl) backupSizeEl.textContent = data.size_bytes;
          if (backupRestoreBtn) backupRestoreBtn.disabled = false;
          setBackupStatus('Backup saved.', 'success');
        } else {
          setBackupStatus('Backup failed: ' + (data.error || r.statusText), 'error');
        }
      } catch (e) {
        setBackupStatus('Network error during backup.', 'error');
      } finally {
        backupNowBtn.disabled = false;
        backupNowBtn.textContent = orig;
      }
    });
  }

  if (backupRestoreBtn) {
    backupRestoreBtn.addEventListener('click', async () => {
      // First warning.
      const ok1 = confirm(
        'RESTORE FROM BACKUP\n\n' +
        'This will REPLACE the current database with the last backup.\n' +
        'All changes made since the backup was taken will be lost:\n' +
        '  • tap edits\n  • settings changes\n  • beer library edits\n  • specials / events\n\n' +
        'The current database will be copied to data/palipints.db.pre-restore\n' +
        'as a one-time safety net.\n\n' +
        'Are you sure you want to continue?'
      );
      if (!ok1) return;

      // Second confirmation — type RESTORE.
      const typed = prompt(
        'Final confirmation.\n\n' +
        'Type RESTORE (in capitals) to confirm. Anything else cancels.'
      );
      if ((typed || '').trim().toUpperCase() !== 'RESTORE') {
        setBackupStatus('Restore cancelled.', '');
        return;
      }

      backupRestoreBtn.disabled = true;
      const orig = backupRestoreBtn.textContent;
      backupRestoreBtn.textContent = 'Restoring…';
      setBackupStatus('Restoring database…', '');
      try {
        const r = await fetch('/admin/api/backup/restore', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ confirm: 'RESTORE' }),
        });
        const data = await r.json();
        if (r.ok && data.ok) {
          setBackupStatus('Restored — reloading page…', 'success');
          setTimeout(() => window.location.reload(), 1200);
        } else {
          setBackupStatus('Restore failed: ' + (data.error || r.statusText), 'error');
          backupRestoreBtn.disabled = false;
          backupRestoreBtn.textContent = orig;
        }
      } catch (e) {
        setBackupStatus('Network error during restore.', 'error');
        backupRestoreBtn.disabled = false;
        backupRestoreBtn.textContent = orig;
      }
    });
  }
})();
