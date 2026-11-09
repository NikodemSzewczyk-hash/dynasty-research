(function () {
  'use strict';
  const root = document.getElementById('discovery-results');
  if (!root) return;
  const search = document.getElementById('discovery-search');
  const year = document.getElementById('discovery-year');
  const topic = document.getElementById('discovery-topic');
  const source = document.getElementById('discovery-source');
  const status = document.getElementById('discovery-status');
  const sort = document.getElementById('discovery-sort');
  const count = document.getElementById('discovery-count');
  const total = document.getElementById('discovery-total');
  const pilotTotal = document.getElementById('discovery-pilot-total');
  const more = document.getElementById('discovery-more');
  const empty = document.getElementById('discovery-empty');
  const error = document.getElementById('discovery-error');
  let records = [];
  let shown = 0;
  let filtered = [];
  const PAGE_SIZE = 30;

  function el(tag, className, value) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (value !== undefined && value !== null) node.textContent = String(value);
    return node;
  }
  function safeUrl(value, allowLocal) {
    if (allowLocal && /^\/papers\/[a-z0-9-]+\/$/.test(value || '')) return value;
    try {
      const u = new URL(value);
      return u.protocol === 'https:' ? u.href : null;
    } catch (_) { return null; }
  }
  // Status wording is an editorial guardrail: every non-curated record must read as unreviewed.
  const COLLECTION_LABELS = {
    pilot23: 'Unreviewed · title-screened',
    seedlist: 'Unreviewed · hand-compiled list',
  };
  function authorLine(authors) {
    const list = (authors || []).filter(Boolean);
    if (!list.length) return 'Authors not listed.';
    if (list.length > 4) return list[0] + ' et al.';
    if (list.length === 1) return list[0] + '.';
    // RePEc gives "Surname, First": separate such names with semicolons so they stay readable.
    const sep = list.some(name => name.includes(',')) ? '; ' : ', ';
    return list.slice(0, -1).join(sep) + (sep === '; ' ? '; ' : ' and ') + list[list.length - 1] + '.';
  }
  function card(record) {
    const curated = record.review_status === 'curated';
    const article = el('article', 'entry discovery-paper' + (curated ? ' is-curated' : ''));
    article.appendChild(el('div', 'entry-mark', record.year || '—'));
    const body = el('div', 'entry-body');
    const h = el('h3', 'entry-title');
    const url = safeUrl(curated ? record.curated_url : record.url, curated);
    if (url) {
      const link = el('a', '', record.title);
      link.href = url;
      if (!curated) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
      h.appendChild(link);
    } else {
      h.textContent = record.title || 'Untitled record';
    }
    body.appendChild(h);
    const meta = el('p', 'entry-meta', authorLine(record.authors) + ' ');
    meta.appendChild(el('em', '', record.source || 'Source not specified'));
    meta.appendChild(el('span', 'status-label' + (curated ? ' is-curated' : ''),
      curated ? 'Curated summary' : (COLLECTION_LABELS[record.collection] || 'Unreviewed metadata')));
    body.appendChild(meta);
    const notes = [];
    if (!curated) notes.push((record.provider || 'unknown') + ' metadata');
    if (record.collection === 'pilot23') notes.push('verified-source pilot');
    if (record.match_type === 'possible') notes.push('possible other version');
    const subjects = (record.topics || []).slice(0, 3).concat(notes);
    if (subjects.length) body.appendChild(el('p', 'entry-subjects', subjects.join(' · ')));
    if ((record.version_count || 0) > 1 && Array.isArray(record.versions)) {
      const details = el('details', 'discovery-versions');
      details.appendChild(el('summary', '', record.version_count + ' metadata versions (possible same work)'));
      const list = el('ul');
      record.versions.forEach(v => {
        const linkUrl = safeUrl(v.url, false);
        if (!linkUrl) return;
        const item = el('li');
        const a = el('a', '', (v.source || v.provider || 'Source') + (v.doi ? ' · ' + v.doi : ''));
        a.href = linkUrl;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        item.appendChild(a);
        list.appendChild(item);
      });
      details.appendChild(list);
      body.appendChild(details);
    }
    article.appendChild(body);
    return article;
  }
  function sortRecords(rows) {
    const mode = sort.value;
    return rows.sort((a, b) => {
      const byTitle = (a.title || '').localeCompare(b.title || '');
      if (mode === 'newest') return (b.year || 0) - (a.year || 0) || byTitle;
      if (mode === 'oldest') return (a.year || 0) - (b.year || 0) || byTitle;
      if (mode === 'title') return byTitle;
      return (b.score || 0) - (a.score || 0) || (b.year || 0) - (a.year || 0) || byTitle;
    });
  }
  function appendMore() {
    const next = filtered.slice(shown, shown + PAGE_SIZE);
    const fragment = document.createDocumentFragment();
    next.forEach(record => fragment.appendChild(card(record)));
    root.appendChild(fragment);
    shown += next.length;
    more.hidden = shown >= filtered.length;
  }
  function apply() {
    const q = search.value.trim().toLocaleLowerCase();
    const yr = year.value;
    const t = topic.value;
    const s = source.value;
    const st = status.value;
    filtered = sortRecords(records.filter(record => {
      const haystack = [record.title, (record.authors || []).join(' '), record.source, record.doi, (record.topics || []).join(' ')]
        .join(' ').toLocaleLowerCase();
      const ids = record.source_ids || [];
      return (!q || haystack.includes(q)) &&
        (!yr || String(record.year) === yr) &&
        (!t || (record.topics || []).includes(t)) &&
        (!st || record.review_status === st) &&
        (!s || (s === '__other__' ? ids.length === 0 : ids.includes(s)));
    }));
    root.replaceChildren();
    shown = 0;
    empty.hidden = filtered.length !== 0;
    count.textContent = filtered.length.toLocaleString() + (filtered.length === 1 ? ' entry' : ' entries');
    appendMore();
  }
  [search, year, topic, source, status, sort].forEach(control =>
    control.addEventListener(control === search ? 'input' : 'change', apply));
  more.addEventListener('click', appendMore);
  fetch('/data/discovery-index.json', {credentials:'omit'})
    .then(response => { if (!response.ok) throw new Error('No discovery data'); return response.json(); })
    .then(data => {
      if (!Array.isArray(data)) throw new Error('Invalid discovery data');
      records = data.filter(record => record && typeof record.title === 'string' &&
        ((record.review_status === 'pending' && record.evidence_level === 'metadata_only') ||
         (record.review_status === 'curated' && record.evidence_level === 'editorial_summary')));
      total.textContent = records.length.toLocaleString();
      pilotTotal.textContent = records.filter(r => r.collection === 'pilot23').length.toLocaleString();
      const years = [...new Set(records.map(r => r.year).filter(Number.isInteger))]
        .sort((a, b) => b - a);
      years.forEach(y => { const option = el('option', '', y); option.value = String(y); year.appendChild(option); });
      const topics = [...new Set(records.flatMap(r => r.topics || []))].sort();
      topics.forEach(t => { const option = el('option', '', t); option.value = t; topic.appendChild(option); });
      const params = new URLSearchParams(window.location.search);
      const query = params.get('q');
      if (query) search.value = query;
      const requestedStatus = params.get('status');
      if (requestedStatus === 'curated' || requestedStatus === 'pending') status.value = requestedStatus;
      apply();
    })
    .catch(() => {
      count.textContent = 'Discovery not available';
      total.textContent = '—';
      pilotTotal.textContent = '—';
      error.hidden = false;
      more.hidden = true;
    });
})();
