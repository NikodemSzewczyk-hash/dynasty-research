(function () {
  'use strict';
  const root = document.getElementById('discovery-results');
  if (!root) return;
  const search = document.getElementById('discovery-search');
  const year = document.getElementById('discovery-year');
  const sort = document.getElementById('discovery-sort');
  const count = document.getElementById('discovery-count');
  const total = document.getElementById('discovery-total');
  const more = document.getElementById('discovery-more');
  const empty = document.getElementById('discovery-empty');
  const error = document.getElementById('discovery-error');
  let records = [];
  let shown = 0;
  let filtered = [];
  const PAGE_SIZE = 30;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }
  function safeUrl(value) {
    try {
      const u = new URL(value);
      return u.protocol === 'https:' ? u.href : null;
    } catch (_) { return null; }
  }
  function card(record) {
    const article = el('article', 'paper-card discovery-paper');
    const mark = el('div', 'paper-index');
    mark.appendChild(el('span', 'index-mark'));
    mark.setAttribute('aria-hidden', 'true');
    article.appendChild(mark);
    const body = el('div', 'paper-content');
    const top = el('div', 'paper-topline');
    top.appendChild(el('span', 'discovery-label', 'UNREVIEWED METADATA'));
    top.appendChild(el('span', 'paper-divider', '/'));
    top.appendChild(el('span', '', record.source || 'Source not specified'));
    body.appendChild(top);
    const h = el('h3');
    const url = safeUrl(record.url);
    if (url) {
      const link = el('a', '', record.title);
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      h.appendChild(link);
    } else {
      h.textContent = record.title || 'Untitled record';
    }
    body.appendChild(h);
    body.appendChild(el('p', 'paper-authors', (record.authors || []).join(', ') || 'Authors not listed'));
    body.appendChild(el('p', 'paper-takeaway', 'Bibliographic record only. No full-text review or editorial interpretation has been completed.'));
    const tags = el('div', 'tag-row');
    tags.appendChild(el('span', 'tag', record.provider === 'crossref' ? 'Crossref metadata' : 'OpenAlex metadata'));
    if (record.match_type === 'possible') tags.appendChild(el('span', 'tag', 'Possible other version'));
    body.appendChild(tags);
    article.appendChild(body);
    const aside = el('div', 'paper-aside');
    aside.appendChild(el('span', 'paper-year', record.year || '—'));
    if (url) {
      const arrow = el('a', 'paper-arrow', '↗');
      arrow.href = url;
      arrow.target = '_blank';
      arrow.rel = 'noopener noreferrer';
      arrow.setAttribute('aria-label', 'Open source: ' + record.title);
      aside.appendChild(arrow);
    }
    article.appendChild(aside);
    return article;
  }
  function sortRecords(rows) {
    const mode = sort.value;
    return rows.sort((a, b) => {
      if (mode === 'newest') return (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title);
      if (mode === 'oldest') return (a.year || 0) - (b.year || 0) || a.title.localeCompare(b.title);
      if (mode === 'title') return a.title.localeCompare(b.title);
      return (b.score || 0) - (a.score || 0) || (b.year || 0) - (a.year || 0);
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
    filtered = sortRecords(records.filter(record => {
      const haystack = [record.title, (record.authors || []).join(' '), record.source, record.doi]
        .join(' ').toLocaleLowerCase();
      return (!q || haystack.includes(q)) && (!yr || String(record.year) === yr);
    }));
    root.replaceChildren();
    shown = 0;
    empty.hidden = filtered.length !== 0;
    count.textContent = filtered.length + (filtered.length === 1 ? ' candidate' : ' candidates');
    appendMore();
  }
  [search, year, sort].forEach(control => control.addEventListener(control === search ? 'input' : 'change', apply));
  more.addEventListener('click', appendMore);
  fetch('/data/discovery-index.json', {credentials:'omit'})
    .then(response => { if (!response.ok) throw new Error('No discovery data'); return response.json(); })
    .then(data => {
      if (!Array.isArray(data)) throw new Error('Invalid discovery data');
      records = data.filter(record => record && typeof record.title === 'string' &&
        record.evidence_level === 'metadata_only' && record.review_status === 'pending');
      total.textContent = records.length.toLocaleString();
      const years = [...new Set(records.map(r => r.year).filter(Number.isInteger))]
        .sort((a, b) => b - a);
      years.forEach(y => {
        const option = el('option', '', y);
        option.value = String(y);
        year.appendChild(option);
      });
      apply();
    })
    .catch(() => {
      count.textContent = 'Discovery not available';
      total.textContent = '—';
      error.hidden = false;
      more.hidden = true;
    });
})();
