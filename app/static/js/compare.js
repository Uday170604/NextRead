/* Compare two books side by side. */
import { api } from './api.js';
import { esc, $, modal, stars, toast } from './util.js';
import { coverHTML } from './cover.js';

export async function openCompare(aId = null) {
  let list;
  try { list = (await api('/books?limit=100&sort=title')).items; } catch (e) { return toast(e.message); }
  const opts = sel => list.map(b => `<option value="${b.id}" ${b.id === sel ? 'selected' : ''}>${esc(b.title)}</option>`).join('');
  const m = modal(`<div class="row"><h2>Compare two books</h2><button class="btn ghost sm" data-close>Close</button></div>
    <div class="row" style="margin:14px 0"><div style="flex:1;min-width:200px"><label class="f" for="ca">Book A</label><select id="ca">${opts(aId ?? list[0]?.id)}</select></div>
    <div style="flex:1;min-width:200px"><label class="f" for="cb">Book B</label><select id="cb">${opts(list.find(b => b.id !== (aId ?? list[0]?.id))?.id)}</select></div></div>
    <div id="cres" aria-live="polite"></div>`, { label: 'Compare books' });
  $('[data-close]', m.el).onclick = () => m.close();
  const run = async () => {
    const a = +$('#ca', m.el).value, b = +$('#cb', m.el).value, out = $('#cres', m.el);
    if (a === b) { out.innerHTML = '<p class="muted">Pick two different books.</p>'; return; }
    out.innerHTML = '<div class="skel" style="height:220px"></div>';
    try {
      const r = await api(`/books/compare?a=${a}&b=${b}`);
      const col = (bk, k) => `<div class="col"><div class="${r.better_fit === k ? 'winner' : ''}" style="max-width:150px;margin:0 auto 12px">${coverHTML(bk)}</div>
        <h3>${esc(bk.title)}</h3><div class="muted">${esc(bk.authors.join(', '))}</div>
        <div class="stars" role="img" aria-label="${bk.avg_rating ?? 'no'} stars">${stars(bk.avg_rating)} <span class="muted">${bk.avg_rating ?? '–'}</span></div>
        <div class="muted">${bk.page_count ? bk.page_count + ' pages' : 'pages n/a'}${bk.publication_year ? ' · ' + bk.publication_year : ''}</div>
        ${r.fit[k] != null ? `<div class="fit">${r.fit[k]}%<div class="muted" style="font:500 .75rem var(--sans)">fits you</div></div>` : ''}</div>`;
      out.innerHTML = `<div class="compare">${col(r.a, 'a')}${col(r.b, 'b')}</div>
        <div class="stack" style="margin-top:16px">
        <div><b>In common:</b> ${[...r.shared_genres, ...r.shared_authors, ...r.shared_moods.map(x => x + ' mood')].map(x => `<span class="chip">${esc(x)}</span>`).join(' ') || '<span class="muted">nothing obvious — a real either/or.</span>'}</div>
        <p style="font:italic 1.1rem var(--serif);border-left:3px solid var(--accent);padding-left:12px">${esc(r.why)}</p></div>`;
    } catch (e) { out.innerHTML = `<div class="err" role="alert">${esc(e.message)}</div>`; }
  };
  $('#ca', m.el).onchange = run; $('#cb', m.el).onchange = run; run();
}
