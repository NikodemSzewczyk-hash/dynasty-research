(function () {
  'use strict';
  const menu = document.getElementById('menu-toggle');
  const nav = document.getElementById('primary-nav');
  if (menu && nav) {
    menu.addEventListener('click', () => {
      const isOpen = menu.getAttribute('aria-expanded') === 'true';
      menu.setAttribute('aria-expanded', String(!isOpen));
      nav.classList.toggle('nav-open', !isOpen);
    });
  }
  const search = document.getElementById('paper-search');
  const topic = document.getElementById('topic-filter');
  const year = document.getElementById('year-filter');
  const cards = [...document.querySelectorAll('#paper-results [data-paper]')];
  const resultCount = document.getElementById('result-count');
  const empty = document.getElementById('empty-state');
  if (!search || !topic || !year || !cards.length) return;
  const years = [...new Set(cards.map(c => c.dataset.year))].sort((a,b) => Number(b)-Number(a));
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
    let shown = 0;
    cards.forEach(card => {
      const text = [card.dataset.title, card.dataset.authors, card.dataset.summary, card.dataset.source, card.dataset.topics].join(' ');
      const topics = (card.dataset.topics || '').split('|');
      const visible = (!query || text.includes(query)) && (!activeTopic || topics.includes(activeTopic)) && (!activeYear || card.dataset.year === activeYear);
      card.hidden = !visible;
      if (visible) shown++;
    });
    if (resultCount) resultCount.textContent = shown + (shown === 1 ? ' paper' : ' papers');
    if (empty) empty.hidden = shown !== 0;
  }
  [search, topic, year].forEach(element => element.addEventListener(element === search ? 'input' : 'change', runFilter));
})();
