// Command palette (Ctrl/Cmd+K): jump to any page or run a common action from the keyboard.
import { el } from './util.js';

export function initPalette(repoUrl) {
  const dlg = el('dialog', { id: 'palette', 'aria-label': 'Command palette', class: 'palette' });
  const input = el('input', { class: 'input', type: 'text', role: 'combobox', 'aria-expanded': 'true', 'aria-controls': 'palette-list', 'aria-autocomplete': 'list', placeholder: 'Go to a page or run an action…', autocomplete: 'off', spellcheck: 'false', maxlength: '60' });
  const list = el('ul', { id: 'palette-list', role: 'listbox', class: 'palette-list' });
  dlg.append(input, list, el('p', { class: 'sub palette-hint' }, '↑ ↓ to move · Enter to run · Esc to close'));
  document.body.appendChild(dlg);

  const items = () => {
    const pages = [...document.querySelectorAll('#nav a[data-route]')].map((a) => ({ label: a.textContent.trim(), group: 'Go to', run: () => a.click() }));
    const acts = [
      { label: 'Toggle light / dark theme', group: 'Action', run: () => document.getElementById('theme-btn').click() },
      { label: 'Enter API key', group: 'Action', run: () => { const b = document.getElementById('key-btn'); if (b && !b.hidden) b.click(); } },
    ];
    if (repoUrl) acts.push({ label: 'Open the source code on GitHub', group: 'Link', run: () => window.open(repoUrl, '_blank', 'noopener') });
    return [...pages, ...acts];
  };

  let shown = [], active = 0;
  function paint() {
    const q = input.value.trim().toLowerCase();
    shown = items().filter((i) => !q || i.label.toLowerCase().includes(q) || i.group.toLowerCase().includes(q));
    active = Math.min(active, Math.max(0, shown.length - 1));
    list.replaceChildren(...(shown.length ? shown.map((it, i) => {
      const li = el('li', { role: 'option', id: `pal-${i}`, 'aria-selected': String(i === active), class: i === active ? 'on' : '' }, el('span', {}, it.label), el('span', { class: 'chip' }, it.group));
      li.addEventListener('click', () => run(it));
      return li;
    }) : [el('li', { class: 'sub' }, 'No match')]));
    input.setAttribute('aria-activedescendant', shown.length ? `pal-${active}` : '');
  }
  function run(it) { dlg.close(); it.run(); }
  function open() { input.value = ''; active = 0; paint(); if (!dlg.open) dlg.showModal(); input.focus(); }

  input.addEventListener('input', () => { active = 0; paint(); });
  input.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') { e.preventDefault(); active = (active + 1) % Math.max(1, shown.length); paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); active = (active - 1 + shown.length) % Math.max(1, shown.length); paint(); }
    else if (e.key === 'Enter' && shown[active]) { e.preventDefault(); run(shown[active]); }
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); dlg.open ? dlg.close() : open(); }
  });
  const btn = el('button', { class: 'icon-btn', type: 'button', 'aria-label': 'Open command palette (Ctrl or Command plus K)', title: 'Command palette (Ctrl/⌘ K)' }, '⌘K');
  btn.addEventListener('click', open);
  const anchor = document.getElementById('theme-btn');
  if (anchor) anchor.before(btn);
}
