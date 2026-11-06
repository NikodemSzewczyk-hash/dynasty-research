(function () {
  'use strict';
  const menu = document.getElementById('menu-toggle');
  const nav = document.getElementById('primary-nav');
  if (menu && nav) {
    menu.addEventListener('click', () => {
      const open = menu.getAttribute('aria-expanded') === 'true';
      menu.setAttribute('aria-expanded', String(!open));
      nav.classList.toggle('nav-open', !open);
    });
    nav.querySelectorAll('a').forEach(a => a.addEventListener('click', () => {
      menu.setAttribute('aria-expanded', 'false');
      nav.classList.remove('nav-open');
    }));
  }

  const search = document.getElementById('paper-search');
  const topic = document.getElementById('topic-filter');
  const year = document.getElementById('year-filter');
  const cards = Array.from(document.querySelectorAll('#paper-results [data-paper]'));
  const resultCount = document.getElementById('result-count');
  const empty = document.getElementById('empty-state');
  const clear = document.getElementById('clear-filters');
  if (!search || !topic || !year) return;

  const years = Array.from(new Set(cards.map(card => card.dataset.year))).sort((a, b) => Number(b) - Number(a));
  years.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    year.appendChild(option);
  });

  function runFilter() {
    const query = search.value.toLocaleLowerCase().trim();
    const activeTopic = topic.value;
    const activeYear = year.value;
    let visibleCount = 0;

    cards.forEach(card => {
      const haystack = [card.dataset.title, card.dataset.authors, card.dataset.summary, card.dataset.source, card.dataset.topics].join(' ');
      const topics = (card.dataset.topics || '').split('|');
      const matches = (!query || haystack.includes(query)) &&
        (!activeTopic || topics.includes(activeTopic)) &&
        (!activeYear || card.dataset.year === activeYear);
      card.hidden = !matches;
      if (matches) visibleCount++;
    });

    if (resultCount) resultCount.textContent = visibleCount + (visibleCount === 1 ? ' paper' : ' papers');
    if (empty) empty.hidden = visibleCount !== 0;
  }
  [search, topic, year].forEach(element => element.addEventListener(element === search ? 'input' : 'change', runFilter));
  if (clear) clear.addEventListener('click', () => {
    search.value = '';
    topic.value = '';
    year.value = '';
    const url = new URL(window.location.href);
    url.searchParams.delete('q');
    window.history.replaceState(null, '', url.pathname + url.search + url.hash);
    runFilter();
    search.focus();
  });
  const query = new URLSearchParams(window.location.search).get('q');
  if (query) search.value = query;
  runFilter();
})();
