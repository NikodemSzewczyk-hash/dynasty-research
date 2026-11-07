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
  function card(record) {
    const article = el('article', 'paper-card discovery-paper');
    const mark = el('div', 'paper-index');
    mark.appendChild(el('span', 'index-mark'));
    mark.setAttribute('aria-hidden', 'true');
    article.appendChild(mark);
    const body = el('div', 'paper-content');
    const top = el('div', 'paper-topline');
    const curated = record.review_status === 'curated';
    const pilot = record.collection === 'pilot23';
    top.appendChild(el('span', 'discovery-label' + (curated ? ' is-curated' : ''), curated ? 'CURATED SUMMARY' : (pilot ? 'TITLE-SCREENED / UNREVIEWED' : 'UNREVIEWED METADATA')));
    top.appendChild(el('span', 'paper-divider', '/'));
    top.appendChild(el('span', '', record.source || 'Source not specified'));
    body.appendChild(top);
    const h = el('h3');
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
    body.appendChild(el('p', 'paper-authors', (record.authors || []).join(', ') || 'Authors not listed'));
    body.appendChild(el('p', 'paper-takeaway', curated ?
      'Editorially selected research. Open the curated archive for the summary.' :
      'Bibliographic metadata only. Title relevance has not been checked against the full paper.'));
    const tags = el('div', 'tag-row');
    (record.topics || []).slice(0, 2).forEach(t => tags.appendChild(el('span', 'tag', t)));
    if (!curated) tags.appendChild(el('span', 'tag', (record.provider || 'unknown').toUpperCase() + ' metadata'));
    if (pilot) tags.appendChild(el('span', 'tag', 'Verified-source pilot'));
    if (record.match_type === 'possible') tags.appendChild(el('span', 'tag', 'Possible other version'));
    body.appendChild(tags);
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
    const aside = el('div', 'paper-aside');
    aside.appendChild(el('span', 'paper-year', record.year || '—'));
    if (url) {
      const arrow = el('a', 'paper-arrow', '↗');
      arrow.href = url;
      if (!curated) { arrow.target = '_blank'; arrow.rel = 'noopener noreferrer'; }
      arrow.setAttribute('aria-label', curated ? 'Read curated summary: ' + record.title : 'Open metadata source: ' + record.title);
      aside.appendChild(arrow);
    }
    article.appendChild(aside);
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
      const query = new URLSearchParams(window.location.search).get('q');
      if (query) search.value = query;
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
