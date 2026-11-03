/* My Taste: genre radar, authors, moods, taste DNA sentence and the four decision lists (with undo). */
import { api } from './api.js';
import { $, $$, esc, state, toast, stars, animateBars, busy } from './util.js';
import { coverHTML } from './cover.js';
import { undoDecision, REASONS } from './actions.js';
import { openShare } from './share.js';
import { meterHTML } from './deck.js';

const TABS = [['interested', 'Interested'], ['saved', 'Saved'], ['read', 'Already read'], ['not_interested', 'Not for me']];

function radarSVG(genres) {
  const g = genres.slice(0, 8), n = g.length, C = 150, R = 100;
  const pt = (i, f) => { const a = -Math.PI / 2 + i * 2 * Math.PI / n; return [C + Math.cos(a) * R * f, C + Math.sin(a) * R * f]; };
  const ring = f => g.map((_, i) => pt(i, f).join(',')).join(' ');
  const shape = g.map((x, i) => pt(i, Math.max(.06, x.score / 100)).join(',')).join(' ');
  const labels = g.map((x, i) => { const [px, py] = pt(i, 1.2); const anchor = Math.abs(px - C) < 8 ? 'middle' : px > C ? 'start' : 'end';
    return `<text x="${px.toFixed(1)}" y="${py.toFixed(1)}" text-anchor="${anchor}" dominant-baseline="middle">${esc(x.name.length > 16 ? x.name.slice(0, 15) + '…' : x.name)}</text>`; }).join('');
  const dots = g.map((x, i) => { const [px, py] = pt(i, Math.max(.06, x.score / 100)); return `<circle class="dot" cx="${px.toFixed(1)}" cy="${py.toFixed(1)}" r="4"><title>${esc(x.name)}: ${x.score}</title></circle>`; }).join('');
  return `<svg class="radar" viewBox="-80 -4 460 308" role="img" aria-label="Genre radar. ${g.map(x => `${x.name} ${x.score} out of 100`).join(', ')}" style="width:100%;max-width:420px;display:block;margin:auto">
    ${[.25, .5, .75, 1].map(f => `<polygon class="grid" points="${ring(f)}"/>`).join('')}${g.map((_, i) => `<line class="grid" x1="${C}" y1="${C}" x2="${pt(i, 1)[0].toFixed(1)}" y2="${pt(i, 1)[1].toFixed(1)}"/>`).join('')}
    <polygon class="shape" points="${shape}"/>${dots}${labels}</svg>`;
}
const barRow = (label, pct, extra = '') => `<div class="bar-row"><span>${label}</span><div class="track" aria-hidden="true"><i data-p="${pct / 100}"></i></div><b>${pct}%</b></div>${extra}`;

export async function renderTaste(view) {
  const t = await api('/users/me/taste');
  const has = t.genres.length > 0;
  view.innerHTML = `<div class="taste-hero"><div><h2 tabindex="-1">My Taste</h2><p class="dna">${esc(t.dna)}</p></div>
      <div style="min-width:260px">${meterHTML(t.learned_pct, t.signals)}</div></div>
    ${has ? `<div class="grid2">
      <section class="panel-card" aria-labelledby="gh"><h3 id="gh">Genres you gravitate to</h3>${t.genres.length >= 3 ? radarSVG(t.genres) : ''}
        <div class="bars" style="margin-top:12px">${t.genres.map(g => barRow(esc(g.name), g.score)).join('')}</div>
        <details style="margin-top:6px"><summary class="muted">View as table</summary><div class="tablewrap"><table><thead><tr><th>Genre</th><th>Books</th><th>Avg rating</th></tr></thead><tbody>${t.genres.map(g => `<tr><td>${esc(g.name)}</td><td>${g.count}</td><td>${g.avg_rating ?? '–'}</td></tr>`).join('')}</tbody></table></div></details></section>
      <div class="stack">
        <section class="panel-card" aria-labelledby="mh2"><h3 id="mh2">Reading moods</h3><div class="bars">${t.moods.filter(m => m.pct > 0).map(m => barRow(`${m.emoji} ${esc(m.label)}`, m.pct)).join('') || '<p class="muted">Like a few books to see your moods.</p>'}</div></section>
        <section class="panel-card" aria-labelledby="ah"><h3 id="ah">Favourite authors</h3>${t.authors.length ? `<ul style="list-style:none;margin:8px 0 0;padding:0;display:flex;flex-direction:column;gap:6px">${t.authors.map(a => `<li class="row"><span>${esc(a.name)}</span><span class="muted">${a.count} book${a.count === 1 ? '' : 's'}${a.avg_rating ? ` · ${a.avg_rating}★` : ''}</span></li>`).join('')}</ul>` : '<p class="muted">No favourites yet.</p>'}</section>
        <section class="panel-card"><h3>Your ratings</h3><div class="row" style="margin-top:6px"><div><div class="stars" style="font-size:1.4rem" role="img" aria-label="Average rating ${t.avg_rating ?? 'none'}">${stars(t.avg_rating)}</div><div class="muted">${t.avg_rating ?? '–'} average across ${t.ratings_count} rating${t.ratings_count === 1 ? '' : 's'}</div></div>
          <button class="btn ghost sm" id="shareTaste">Share my picks</button></div></section></div></div>`
    : `<div class="empty panel-card" style="margin-top:20px"><h3>Nothing to chart yet</h3><p>Swipe a few books or rate ones you've read and your taste profile will appear here.</p><a class="btn" href="#match">Start swiping</a></div>`}
    <div class="tabs" role="tablist" aria-label="Your decisions">${TABS.map(([k, l], i) => `<button class="chip" role="tab" id="tab-${k}" aria-selected="${i === 0}" aria-pressed="${i === 0}" aria-controls="tp" data-t="${k}">${l} (${t.counts[k] ?? 0})</button>`).join('')}</div>
    <div id="tp" role="tabpanel" aria-live="polite"></div>`;
  animateBars(view);
  $('#shareTaste', view)?.addEventListener('click', async () => {
    try { const w = await api('/recommendations/weekly'); openShare({ name: state.me.name.split(' ')[0], picks: w.picks }); } catch (e) { toast(e.message); }
  });
  const load = async k => {
    $$('[data-t]', view).forEach(b => { const on = b.dataset.t === k; b.setAttribute('aria-selected', on); b.setAttribute('aria-pressed', on); });
    const host = $('#tp', view); host.setAttribute('aria-labelledby', `tab-${k}`);
    host.innerHTML = '<div class="skel" style="height:180px"></div>';
    try {
      const items = await api(`/feedback?action=${k}&limit=200`);
      host.innerHTML = items.length ? `<div class="lists">${items.map(i => `<div class="litem" data-id="${i.book.id}">
        <button class="rcard" data-open="${i.book.id}" aria-label="${esc(i.book.title)}">${coverHTML(i.book)}</button>
        <div class="t">${esc(i.book.title)}</div><div class="a">${esc(i.book.authors.join(', '))}</div>
        ${i.rating ? `<div class="stars" role="img" aria-label="${i.rating} stars">${stars(i.rating)}</div>` : ''}${i.reason ? `<span class="chip">${esc(REASONS[i.reason] || i.reason)}</span>` : ''}
        <button class="btn ghost sm" data-undo="${i.book.id}" data-stop="1" style="align-self:flex-start">Undo</button></div>`).join('')}</div>`
        : `<div class="empty">Nothing here yet.</div>`;
      $$('[data-undo]', host).forEach(btn => btn.onclick = () => busy(btn, async () => {
        const item = items.find(x => x.book.id === +btn.dataset.undo);
        try { const r = await undoDecision(item.book); toast(r.rating_kept ? 'Decision removed — your written review was kept' : 'Decision undone — it can show up in picks again'); renderTaste(view); } catch (e) { toast(e.message); }
      }));
    } catch (e) { host.innerHTML = `<div class="empty" role="alert">${esc(e.message)}</div>`; }
  };
  $$('[data-t]', view).forEach(b => b.onclick = () => load(b.dataset.t));
  $('[role=tablist]', view).addEventListener('keydown', e => {
    const tabs = $$('[data-t]', view), i = tabs.indexOf(document.activeElement);
    if (i < 0 || !['ArrowRight', 'ArrowLeft'].includes(e.key)) return;
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; n.focus(); load(n.dataset.t);
  });
  load('interested');
}
