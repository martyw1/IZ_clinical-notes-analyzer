'use strict';
const filter = document.getElementById('filter');
if (filter) {
  const items = [...document.querySelectorAll('.filter-item')];
  const results = document.getElementById('results');
  const update = () => {
    const query = filter.value.trim().toLocaleLowerCase();
    let visible = 0;
    for (const item of items) {
      item.hidden = !item.textContent.toLocaleLowerCase().includes(query);
      if (!item.hidden) visible++;
    }
    results.textContent = `${visible} of ${items.length} entries${visible === 0 ? ' — try another search.' : ''}`;
  };
  filter.addEventListener('input', update);
  update();
}
