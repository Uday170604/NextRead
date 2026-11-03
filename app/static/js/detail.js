/* Recommendation detail panel (NOT a reader): cover, facts, why-we-picked-this, similar books, where to get it. */
import { api } from './api.js';
import { $, $$, esc, state, stars, starLabel, toast, busy, animateBars, reduced, heartBurst, nav } from './util.js';
import { coverHTML } from './cover.js';
import { railHTML, wireRails } from './rows.js';
import { decide, undoDecision, decisionOf, decisionSnack, askRating, requireLogin } from './actions.js';
import { openCompare } from './compare.js';

const dlg = () => $('#detail');
let lastFocus = null;

// Any element with data-open="<bookId>" opens the panel (cards, rows, tables...).
document.addEventListener('click', e => {
  const c = e.target.closest('[data-open]');
  if (c && !e.target.closest('[data-stop]')) { e.preventDefault(); openBook(+c.dataset.open, c); }
});
document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches?.('[data-open]:not(button)')) { e.preventDefault(); openBook(+e.target.dataset.open, e.target); }
});

function flip(srcCover, dstCover, host) {
  if (reduced() || !srcCover || !dstCover) return;
  const a = srcCover.getBoundingClientRect(), b = dstCover.getBoundingClientRect();
  if (!a.width || !b.width) return;
  const ghost = srcCover.cloneNode(true);
  ghost.classList.add('ghost-cover');
  ghost.style.cssText += `;left:${b.left}px;top:${b.top}px;width:${b.width}px;margin:0`;
  host.append(ghost); dstCover.style.opacity = '0';
  const done = () => { dstCover.style.opacity = ''; ghost.remove(); };
  try {
    ghost.animate([{ transform: `translate(${a.left - b.left}px,${a.top - b.top}px) scale(${a.width / b.width})` }, { transform: 'none' }],
      { duration: 420, easing: 'cubic-bezier(.2,.8,.2,1)' }).finished.then(done, done);
  } catch (e) { done(); }
}

const enc = encodeURIComponent;
function getLinks(b) {
  const q = enc(`${b.title} ${b.authors[0] || ''}`);
  return [
    ['Open Library', b.isbn ? `https://openlibrary.org/isbn/${enc(b.isbn)}` : `https://openlibrary.org/search?q=${q}`],
    ['Google Books', `https://www.google.com/search?tbm=bks&q=${q}`],
    ['Find in a library (WorldCat)', `https://search.worldcat.org/search?q=${q}`],
  ];
}

export async function openBook(id, srcEl = null) {
  const d = dlg();
  const first = !d.open;
  if (first) lastFocus = document.activeElement;
  let b, reviews, similar, explain = null;
  try {
    [b, reviews, similar] = await Promise.all([api('/books/' + id), api(`/books/${id}/reviews`), api(`/books/${id}/similar?limit=8`)]);
    if (state.me) explain = await api(`/recommendations/${id}/explain`).catch(() => null);
  } catch (e) { return toast(e.message); }
  let myRating = b.my_rating || 0;
  const dec = () => decisionOf(id) || (b.in_wishlist ? 'saved' : null);
  const act = (k, glyph, label, cls = '') => `<button class="act ${cls}" data-act="${k}" aria-pressed="${dec() === k}">${glyph} ${label}</button>`;

  d.innerHTML = `<div class="dlg" id="dbody"><button class="icon-btn close" id="dclose" aria-label="Close details">✕</button>
    <div class="d-top"><div>${coverHTML(b)}</div><div>
      <h2 id="dtitle" tabindex="-1">${esc(b.title)}</h2>
      <div class="muted" style="margin:4px 0 8px">${esc(b.authors.join(', '))}</div>
      <div class="stars" role="img" aria-label="Community rating ${starLabel(b.avg_rating)}">${stars(b.avg_rating)} <span class="muted">${b.avg_rating ?? '–'} · ${b.ratings_count} rating${b.ratings_count === 1 ? '' : 's'}</span></div>
      <div class="chips" style="margin-top:10px">${b.genres.map(g => `<span class="chip">${esc(g)}</span>`).join('')}</div>
      <div class="facts">${b.publication_year ? `<span>${b.publication_year}</span>` : ''}${b.publisher ? `<span>${esc(b.publisher)}</span>` : ''}${b.page_count ? `<span>${b.page_count} pages</span>` : ''}</div>
    </div></div>
    ${state.me ? `<div class="actions" role="group" aria-label="Your decision" style="margin:6px 0 16px">${act('interested', '❤', 'Interested', 'love')}${act('not_interested', '✕', 'Not for me')}${act('saved', '+', 'Save for later')}${act('read', '✓', 'Already read')}</div>`
      : `<p class="muted"><a href="#login" data-nav="login">Log in</a> to say what you think of this book and get picks that learn from you.</p>`}
    <p>${esc(b.description || 'No description available.')}</p>
    ${b.mood_tags.length ? `<div class="chips" aria-label="Moods">${b.mood_tags.map(m => `<span class="chip">${esc(moodLabel(m))}</span>`).join('')}</div>` : ''}
    ${whySection(explain)}
    <h3 style="margin:22px 0 8px">Where to get it</h3>
    <div class="links">${getLinks(b).map(([l, u]) => `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(l)} ↗</a>`).join('')}</div>
    <p class="muted" style="font-size:.8rem;margin-top:6px">Links only — NextRead never shows book content.</p>
    ${state.me ? `<h3 style="margin:22px 0 4px">Your rating &amp; review</h3><div class="rate" id="rate" role="group" aria-label="Your star rating">${[1, 2, 3, 4, 5].map(i => `<button type="button" data-i="${i}" aria-label="${i} star${i > 1 ? 's' : ''}" aria-pressed="${i <= myRating}" class="${i <= myRating ? 'on' : ''}">★</button>`).join('')}</div>
      <label class="f" for="cmt">Review (optional)</label><textarea id="cmt" rows="3" maxlength="2000" placeholder="What did you think?"></textarea>
      <div class="row" style="margin-top:10px"><div><button class="btn" id="saveRev">Save rating</button> ${b.my_rating ? '<button class="btn ghost" id="delRev">Delete my review</button>' : ''}</div></div>` : ''}
    <div class="row" style="margin:22px 0 6px"><h3>Similar books</h3><button class="btn ghost sm" id="cmp">Compare with another book</button></div>
    ${similar.length ? railHTML(similar) : '<p class="muted">No close matches yet.</p>'}
    <h3 style="margin:22px 0 4px">Reviews</h3>
    ${reviews.filter(r => r.comment).map(r => `<div class="review"><div class="row"><b>${esc(r.user_name)}</b><span class="stars" role="img" aria-label="${starLabel(r.rating)}">${stars(r.rating)}</span></div><div>${esc(r.comment)}</div></div>`).join('') || '<p class="muted">No written reviews yet.</p>'}
  </div>`;

  const body = $('#dbody', d);
  $('#dclose', d).onclick = () => d.close();
  wireRails(body); animateBars(body);
  $$('[data-nav]', body).forEach(a => a.onclick = e => { e.preventDefault(); d.close(); nav(a.dataset.nav); });
  $('#cmp', body).onclick = () => { d.close(); openCompare(id); };

  if (state.me) {
    const mine = reviews.find(r => r.user_id === state.me.id); if (mine) $('#cmt', body).value = mine.comment || '';
    const refreshActs = () => $$('[data-act]', body).forEach(x => x.setAttribute('aria-pressed', String(dec() === x.dataset.act)));
    $$('[data-act]', body).forEach(btn => btn.onclick = () => busy(btn, async () => {
      const k = btn.dataset.act;
      try {
        if (dec() === k) { await undoDecision(b); b.in_wishlist = false; toast('Decision undone'); refreshActs(); return; }
        let opts = {};
        if (k === 'read') { const r = await askRating(b, myRating); if (!r) return; opts = r; if (r.rating) { myRating = r.rating; syncStars(); } }
        await decide(b, k, opts); b.in_wishlist = k === 'saved';
        if (k === 'interested') heartBurst(btn);
        refreshActs(); decisionSnack(b, k, { onUndo: refreshActs });
      } catch (e) { toast(e.message); }
    }));
    const syncStars = () => $$('#rate button', body).forEach(s => { const on = +s.dataset.i <= myRating; s.classList.toggle('on', on); s.setAttribute('aria-pressed', on); });
    $$('#rate button', body).forEach(btn => btn.onclick = () => { myRating = +btn.dataset.i; syncStars(); });
    $('#saveRev', body).onclick = e => { if (!myRating) return toast('Pick a star rating first'); busy(e.target, async () => {
      try { await api(`/books/${id}/review`, { method: 'PUT', body: { rating: myRating, comment: $('#cmt', body).value.trim() || null } });
        state.decisions.set(id, { action: 'read', rating: myRating }); toast('Rating saved — your picks just got sharper'); window.dispatchEvent(new Event('nr:ratings-changed')); openBook(id); } catch (err) { toast(err.message); } }); };
    const del = $('#delRev', body); if (del) del.onclick = e => { if (!confirm('Delete your rating and review for this book?')) return; busy(e.target, async () => {
      try { await api(`/books/${id}/review`, { method: 'DELETE' }); state.decisions.delete(id); toast('Review deleted'); openBook(id); } catch (err) { toast(err.message); } }); };
  }

  const reveal = () => { const t = $('#dtitle', d); t?.focus({ preventScroll: true }); };
  if (first) {
    d.classList.toggle('noanim', !!srcEl && !reduced());
    d.showModal();
    flip(srcEl?.querySelector?.('.cover') || (srcEl?.classList?.contains('cover') ? srcEl : null), $('.d-top .cover', d), d);
  }
  reveal();
}

function moodLabel(k) { return state.moods?.find(m => m.key === k)?.label ?? k; }

function whySection(x) {
  if (!state.me) return '';
  if (!x) return '';
  const pct = v => Math.round(v * 100);
  return `<h3 style="margin:22px 0 4px">Why we picked this for you</h3>
    <div class="row" style="align-items:flex-start"><p style="margin:6px 0"><b style="font:700 1.6rem var(--serif)">${x.match_pct}%</b> <span class="muted">match</span> — ${esc(x.reason)}</p></div>
    <div class="bars" role="list" aria-label="Score breakdown">${x.breakdown.map(r => `<div class="bar-row" role="listitem"><span>${esc(r.label)}</span>
      <div class="track" aria-hidden="true"><i data-p="${r.value}"></i></div><b aria-label="${pct(r.value)} percent">${pct(r.value)}%</b></div>`).join('')}</div>
    <p class="muted" style="font-size:.85rem">${esc(x.summary)}</p>
    ${x.mood_matches.length ? `<p class="muted" style="font-size:.85rem">Moods: ${x.mood_matches.map(m => `${esc(m.label)} (${esc(m.signals.join('; '))})`).join(' · ')}</p>` : ''}`;
}

export function initDetail() {
  const d = dlg();
  d.addEventListener('click', e => { if (e.target === d) d.close(); });
  d.addEventListener('close', () => { d.classList.remove('noanim'); try { lastFocus?.focus(); } catch (e) { /* ignore */ } if (location.hash.startsWith('#book/')) history.replaceState(null, '', '#home'); });
}
