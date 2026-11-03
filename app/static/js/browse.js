/* Browse & search: instant suggestions, did-you-mean, filters for year / rating / pages / mood. */
import { api } from './api.js';
import { $, $$, esc, state, debounce } from './util.js';
import { cardHTML } from './rows.js';
import { openCompare } from './compare.js';
import { openBook } from './detail.js';

let bs = { q: '', genre: '', sort: 'title', minr: '', yf: '', yt: '', pmin: '', pmax: '', mood: '', skip: 0 };
const PAGE = 18;

export async function renderBrowse(view) {
  const [genres, moods] = await Promise.all([api('/genres'), state.moods ? state.moods : api('/moods')]);
  state.moods = moods;
  const sel = (id, label, opts, cur) => `<div><label for="${id}">${label}</label><select id="${id}">${opts.map(([k, l]) => `<option value="${esc(k)}" ${String(k) === String(cur) ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></div>`;
  view.innerHTML = `<div class="row"><h2 tabindex="-1">Browse</h2><button class="btn ghost sm" id="cmp">Compare two books</button></div>
    <form id="ff" role="search" autocomplete="off" style="margin-top:12px">
      <div class="search"><label class="sr" for="q">Search by title, author or genre</label>
        <input id="q" type="search" placeholder="Search title, author, genre or keyword" value="${esc(bs.q)}" role="combobox" aria-expanded="false" aria-controls="sg" aria-autocomplete="list">
        <ul class="sugg" id="sg" role="listbox" hidden></ul></div>
      <div class="filters">
        ${sel('genre', 'Genre', [['', 'All genres'], ...genres.map(g => [g, g])], bs.genre)}
        ${sel('mood', 'Mood', [['', 'Any mood'], ...moods.map(m => [m.key, `${m.emoji} ${m.label}`])], bs.mood)}
        ${sel('minr', 'Min rating', [['', 'Any'], ['3', '3★ & up'], ['3.5', '3.5★ & up'], ['4', '4★ & up'], ['4.5', '4.5★ & up']], bs.minr)}
        <div><label for="yf">Year from</label><input id="yf" type="number" min="0" max="2100" value="${esc(bs.yf)}" placeholder="1900"></div>
        <div><label for="yt">Year to</label><input id="yt" type="number" min="0" max="2100" value="${esc(bs.yt)}" placeholder="2025"></div>
        <div><label for="pmin">Pages from</label><input id="pmin" type="number" min="1" value="${esc(bs.pmin)}" placeholder="0"></div>
        <div><label for="pmax">Pages to</label><input id="pmax" type="number" min="1" value="${esc(bs.pmax)}" placeholder="1500"></div>
        ${sel('sort', 'Sort by', [['title', 'A–Z'], ['rating', 'Top rated'], ['popular', 'Most rated'], ['year', 'Newest']], bs.sort)}
        <div style="display:flex;gap:8px"><button class="btn" type="submit">Search</button><button class="btn ghost" type="button" id="reset">Reset</button></div></div></form>
    <div id="results" aria-live="polite"></div>`;
  $('#cmp', view).onclick = () => openCompare();
  $('#ff', view).addEventListener('submit', e => { e.preventDefault(); closeSug(); apply(); });
  $$('#genre,#mood,#minr,#sort', view).forEach(el => el.addEventListener('change', apply));
  $('#reset', view).onclick = () => { bs = { q: '', genre: '', sort: 'title', minr: '', yf: '', yt: '', pmin: '', pmax: '', mood: '', skip: 0 }; renderBrowse(view); };
  wireSuggest(view);
  await load();
}
function apply() {
  bs = { q: $('#q').value.trim(), genre: $('#genre').value, sort: $('#sort').value, minr: $('#minr').value, yf: $('#yf').value, yt: $('#yt').value,
    pmin: $('#pmin').value, pmax: $('#pmax').value, mood: $('#mood').value, skip: 0 };
  load();
}

async function load() {
  const p = new URLSearchParams({ sort: bs.sort, skip: bs.skip, limit: PAGE });
  const map = { q: 'q', genre: 'genre', minr: 'min_rating', yf: 'year_from', yt: 'year_to', pmin: 'pages_min', pmax: 'pages_max', mood: 'mood' };
  for (const [k, v] of Object.entries(map)) if (bs[k]) p.set(v, bs[k]);
  const host = $('#results');
  host.innerHTML = `<div class="grid">${Array.from({ length: 6 }, () => '<div class="skel cov"></div>').join('')}</div>`;
  try {
    const page = await api('/books?' + p);
    if (page.total && bs.skip >= page.total) { bs.skip = Math.max(0, (Math.ceil(page.total / PAGE) - 1) * PAGE); return load(); }
    const pages = Math.max(1, Math.ceil(page.total / PAGE));
    host.innerHTML = `<p class="muted">${page.total} book${page.total === 1 ? '' : 's'} found</p>
      ${page.did_you_mean ? `<div class="dym">No exact match. Did you mean <button class="chip" id="dym">${esc(page.did_you_mean)}</button>?</div>` : ''}
      ${page.items.length ? `<div class="grid">${page.items.map(b => cardHTML(b)).join('')}</div>` : '<div class="empty"><h3>No matches</h3><p>Try fewer filters or another keyword.</p><button class="btn ghost" id="rs2">Reset filters</button></div>'}
      ${pages > 1 ? `<div class="row" style="margin-top:22px"><button class="btn ghost" id="prev" ${bs.skip <= 0 ? 'disabled' : ''}>← Prev</button><span class="muted">Page ${Math.floor(bs.skip / PAGE) + 1} of ${pages}</span><button class="btn ghost" id="nextp" ${bs.skip + PAGE >= page.total ? 'disabled' : ''}>Next →</button></div>` : ''}`;
    $('#dym', host)?.addEventListener('click', () => { $('#q').value = page.did_you_mean; apply(); });
    $('#rs2', host)?.addEventListener('click', () => $('#reset').click());
    $('#prev', host)?.addEventListener('click', () => { bs.skip -= PAGE; load(); });
    $('#nextp', host)?.addEventListener('click', () => { bs.skip += PAGE; load(); });
  } catch (e) { host.innerHTML = `<div class="empty" role="alert">${esc(e.message)}<br><br><button class="btn ghost" id="rt">Try again</button></div>`; $('#rt', host).onclick = load; }
}

/* ARIA combobox with instant suggestions */
let sugItems = [], sugIdx = -1;
const closeSug = () => { const l = $('#sg'); if (!l) return; l.hidden = true; $('#q').setAttribute('aria-expanded', 'false'); sugIdx = -1; };
function wireSuggest(view) {
  const q = $('#q', view), list = $('#sg', view);
  const paint = () => {
    list.innerHTML = sugItems.map((s, i) => `<li role="option" id="so${i}" aria-selected="${i === sugIdx}" data-i="${i}"><span>${esc(s.text)}</span><span class="k">${s.type}</span></li>`).join('');
    list.hidden = !sugItems.length; q.setAttribute('aria-expanded', String(!!sugItems.length));
    if (sugIdx >= 0) q.setAttribute('aria-activedescendant', `so${sugIdx}`); else q.removeAttribute('aria-activedescendant');
  };
  const pick = s => {
    closeSug();
    if (s.type === 'title' && s.book_id) { openBook(s.book_id); return; }
    if (s.type === 'genre') { $('#genre').value = s.text; q.value = ''; } else q.value = s.text;
    apply();
  };
  q.addEventListener('input', debounce(async () => {
    const v = q.value.trim(); if (!v) { sugItems = []; paint(); return; }
    try { sugItems = await api(`/books/suggest?q=${encodeURIComponent(v)}&limit=8`); } catch (e) { sugItems = []; }
    sugIdx = -1; paint();
  }, 160));
  q.addEventListener('keydown', e => {
    if (!sugItems.length || list.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); sugIdx = (sugIdx + 1) % sugItems.length; paint(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); sugIdx = (sugIdx - 1 + sugItems.length) % sugItems.length; paint(); }
    else if (e.key === 'Enter' && sugIdx >= 0) { e.preventDefault(); pick(sugItems[sugIdx]); }
    else if (e.key === 'Escape') closeSug();
  });
  list.addEventListener('mousedown', e => { const li = e.target.closest('li[data-i]'); if (li) { e.preventDefault(); pick(sugItems[+li.dataset.i]); } });
  q.addEventListener('blur', () => setTimeout(closeSug, 120));
}
