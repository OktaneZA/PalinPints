(() => {
  document.querySelectorAll('[data-untappd-search]').forEach(btn => {
    btn.addEventListener('click', async (ev) => {
      const form = ev.target.closest('form[data-tap-form]');
      if (!form) return;
      const status = form.querySelector('[data-untappd-status]');
      const beerInput = form.querySelector('[data-field="beer_name"]');
      const breweryInput = form.querySelector('[data-field="brewery"]');
      const query = [breweryInput?.value, beerInput?.value].filter(Boolean).join(' ').trim();
      if (!query) {
        status.textContent = 'Enter a brewery and beer name first.';
        status.className = 'untappd-status error';
        return;
      }
      btn.disabled = true;
      status.textContent = 'Searching Untappd…';
      status.className = 'untappd-status';
      try {
        const r = await fetch('/admin/api/untappd/search?q=' + encodeURIComponent(query));
        const data = await r.json();
        if (data.error) {
          status.textContent = 'Untappd: ' + data.error;
          status.className = 'untappd-status error';
        } else {
          fillField(form, 'beer_name', data.beer_name);
          fillField(form, 'brewery', data.brewery);
          fillField(form, 'sub_style', data.sub_style);
          if (data.abv != null) fillField(form, 'abv', data.abv);
          if (data.ibu != null) fillField(form, 'ibu', data.ibu);
          fillField(form, 'location', data.location);
          fillField(form, 'untappd_slug', data.untappd_slug);
          status.textContent = 'Untappd autofill applied. Review and save.';
          status.className = 'untappd-status success';
        }
      } catch (e) {
        status.textContent = 'Network error talking to Untappd.';
        status.className = 'untappd-status error';
      } finally {
        btn.disabled = false;
      }
    });
  });

  function fillField(form, name, value) {
    if (value == null || value === '') return;
    const el = form.querySelector(`[data-field="${name}"]`);
    if (el) el.value = value;
  }
})();
