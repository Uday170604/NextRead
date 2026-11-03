/* "Book Match": a Tinder-style swipe deck. Right = interested, left = not for me, up = already read,
   down/button = save for later. Every decision is sent to the backend and the cards underneath re-rank live. */
import { api } from './api.js';
import { $, $$, esc, state, toast, reduced, ringHTML, animateRings, announce, sleep } from './util.js';
import { coverHTML } from './cover.js';
import { decide, undoDecision, decisionSnack, askRating, ACTION_LABEL } from './actions.js';

const THRESH = 110;
const MILESTONE = p => p < 25 ? 'Just getting to know you' : p < 60 ? 'Getting sharper' : p < 85 ? 'Your taste is taking shape' : 'We know your taste well';

export function meterHTML(pct, signals) {
  return `<div class="meter" id="meter"><div class="row"><b>Your taste profile: <span id="mpct">${pct}</span>% learned</b><span class="muted" id="msig">${signals} decision${signals === 1 ? '' : 's'}</span></div>
    <div class="meter-bar" role="progressbar" aria-label="Taste profile learned" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct}"><i style="--p:${pct / 100}"></i></div>
    <div class="muted" id="mnote" style="font-size:.85rem">${MILESTONE(pct)}</div></div>`;
}
export function setMeter(root, taste) {
  const m = $('#meter', root); if (!m || !taste) return;
  $('#mpct', m).textContent = taste.learned_pct; $('#msig', m).textContent = `${taste.signals} decision${taste.signals === 1 ? '' : 's'}`;
  $('.meter-bar', m).setAttribute('aria-valuenow', taste.learned_pct); $('.meter-bar i', m).style.setProperty('--p', taste.learned_pct / 100);
  $('#mnote', m).textContent = MILESTONE(taste.learned_pct);
}

/* host: element to render into. cfg.goal: stop after N decisions (onboarding). cfg.onDone: called when goal reached. */
export async function mountDeck(host, cfg = {}) {
  const st = { queue: [], seq: 0, decided: 0, recent: [], busy: false };
  host.innerHTML = `<div class="match"><div>
      <div class="deck" id="deck" tabindex="0" role="group" aria-roledescription="card stack" aria-label="Book match deck. Right arrow: interested. Left arrow: not for me. Up arrow: already read. Down arrow: save for later. Enter: open details."></div>
      <div class="deck-btns" role="group" aria-label="Decide on the top card">
        <button class="act" data-d="not_interested" aria-label="Not for me" title="Not for me (←)">✕</button>
        <button class="act" data-d="read" aria-label="Already read it" title="Already read (↑)">✓</button>
        <button class="act" data-d="saved" aria-label="Save for later" title="Save for later (↓)">+</button>
        <button class="act love" data-d="interested" aria-label="Interested" title="Interested (→)">❤</button></div>
      <p class="keys">Swipe or use the arrow keys · ← not for me · → interested · ↑ already read · ↓ save</p></div>
    <div class="stack" id="side"><div id="metermount"></div>
      ${cfg.goal ? `<div class="meter"><b id="goalc">0 of ${cfg.goal}</b> <span class="muted">cards swiped — the more you swipe, the better your first picks.</span></div>` : ''}
      <div class="panel-card"><h3 style="margin-bottom:6px">How the deck works</h3><p class="muted" style="margin:0">Every swipe re-ranks the cards underneath. “Not for me” hides a book for good and nudges similar ones down; you can say why. Nothing is permanent — undo any time.</p></div>
      <div id="recent"></div></div></div>`;
  const deck = $('#deck', host);

  const render = () => {
    deck.innerHTML = '';
    if (!st.queue.length) {
      deck.innerHTML = `<div class="empty panel-card" style="position:absolute;inset:0;display:grid;place-content:center"><h3>You've decided on everything</h3><p>Nothing left to swipe. See what you've learned about your taste.</p><a class="btn" href="#taste">Open My Taste</a></div>`;
      $$('.deck-btns .act', host).forEach(b => b.disabled = true); return;
    }
    $$('.deck-btns .act', host).forEach(b => b.disabled = false);
    st.queue.slice(0, 3).reverse().forEach((rec, ri, arr) => {
      const i = arr.length - 1 - ri, b = rec.book;
      const el = document.createElement('div');
      el.className = 'dcard'; el.dataset.id = b.id;
      el.style.zIndex = 10 - i;
      el.style.transform = `translateY(${i * 12}px) scale(${1 - i * .045})`;
      if (i) el.setAttribute('aria-hidden', 'true');
      el.innerHTML = `<span class="stamp yes">INTERESTED</span><span class="stamp no">NOT FOR ME</span><span class="stamp read">READ IT</span>
        ${coverHTML(b)}<div class="row" style="align-items:flex-start;flex-wrap:nowrap"><div><h3>${esc(b.title)}</h3><div class="muted" style="font-size:.9rem">${esc(b.authors.join(', '))}</div></div>
        ${rec.personalised ? ringHTML(rec.match_pct, { small: true }) : `<span class="chip">${rec.algorithm === 'exploration' ? 'New territory' : 'Popular'}</span>`}</div>
        <div class="chips">${b.genres.slice(0, 3).map(g => `<span class="chip">${esc(g)}</span>`).join('')}${b.avg_rating ? `<span class="chip stars">★ ${b.avg_rating}</span>` : ''}${b.page_count ? `<span class="chip">${b.page_count} pp</span>` : ''}</div>
        <div class="why">${esc(rec.reason)}</div>`;
      deck.append(el);
      if (i === 0) attachDrag(el);
    });
    animateRings(deck);
  };

  function attachDrag(el) {
    let sx = 0, sy = 0, dx = 0, dy = 0, drag = false, moved = 0;
    const stamps = { yes: $('.stamp.yes', el), no: $('.stamp.no', el), read: $('.stamp.read', el) };
    el.addEventListener('pointerdown', e => { if (st.busy || e.button > 0) return; drag = true; sx = e.clientX; sy = e.clientY; moved = 0; el.classList.add('dragging'); el.setPointerCapture(e.pointerId); });
    el.addEventListener('pointermove', e => {
      if (!drag) return;
      dx = e.clientX - sx; dy = e.clientY - sy; moved = Math.max(moved, Math.abs(dx), Math.abs(dy));
      el.style.transform = `translate(${dx}px,${dy}px) rotate(${dx / 18}deg)`;
      const up = dy < -40 && Math.abs(dy) > Math.abs(dx);
      stamps.yes.style.opacity = !up && dx > 0 ? Math.min(1, dx / THRESH) : 0;
      stamps.no.style.opacity = !up && dx < 0 ? Math.min(1, -dx / THRESH) : 0;
      stamps.read.style.opacity = up ? Math.min(1, -dy / THRESH) : 0;
    });
    const end = e => {
      if (!drag) return; drag = false; el.classList.remove('dragging');
      try { el.releasePointerCapture(e.pointerId); } catch (err) { /* ignore */ }
      const up = dy < -THRESH && Math.abs(dy) > Math.abs(dx);
      if (moved < 6) { Object.values(stamps).forEach(s => s.style.opacity = 0); el.style.transform = ''; el.dispatchEvent(new CustomEvent('tap')); return; }
      if (up) { snapBack(el); decideTop('read'); }
      else if (dx > THRESH) decideTop('interested', { fromDrag: true });
      else if (dx < -THRESH) decideTop('not_interested', { fromDrag: true });
      else snapBack(el);
      dx = dy = 0;
    };
    el.addEventListener('pointerup', end); el.addEventListener('pointercancel', end);
    el.addEventListener('tap', () => { const id = st.queue[0]?.book.id; if (id) { const t = document.createElement('button'); t.dataset.open = id; t.hidden = true; el.append(t); t.click(); t.remove(); } });
  }
  function snapBack(el) {
    el.style.transform = ''; Object.values({ a: $('.stamp.yes', el), b: $('.stamp.no', el), c: $('.stamp.read', el) }).forEach(s => s && (s.style.opacity = 0));
  }

  async function flyOff(dir) {
    const el = $('.dcard[data-id]', deck) && $$('.dcard', deck).find(c => c.style.zIndex === '10'); if (!el) return;
    if (reduced()) { el.remove(); return; }
    const X = innerWidth, map = { interested: [X, -40, 25], not_interested: [-X, -40, -25], saved: [0, 700, 0], read: [0, -700, 0] };
    const [tx, ty, rot] = map[dir];
    el.style.transition = 'transform .38s cubic-bezier(.4,.1,.6,1), opacity .38s'; el.style.transform = `translate(${tx}px,${ty}px) rotate(${rot}deg)`; el.style.opacity = '0';
    await sleep(300);
  }

  async function decideTop(action) {
    if (st.busy || !st.queue.length) return;
    const rec = st.queue[0], book = rec.book;
    let extra = {};
    if (action === 'read') {
      const r = await askRating(book); if (!r) return;      // dismissed -> card stays
      extra = r;
    }
    st.busy = true;
    try {
      const [resp] = await Promise.all([decide(book, action, extra), flyOff(action)]);
      st.queue.shift(); st.decided++; st.recent.unshift({ book, action });
      setMeter(host, resp.taste); renderRecent(); render();
      if (cfg.goal) { const gc = $('#goalc', host); if (gc) gc.textContent = `${Math.min(st.decided, cfg.goal)} of ${cfg.goal}`; }
      decisionSnack(book, action, { onUndo: () => undo(rec) });
      announce(`${ACTION_LABEL[action]}: ${book.title}. ${st.queue.length} cards left.`);
      if (cfg.goal && st.decided >= cfg.goal) { cfg.onDone?.(); return; }
      refill();
    } catch (e) {
      toast(e.message); render();           // restore the card
    } finally { st.busy = false; }
  }
  async function undo(rec) {
    st.queue = [rec, ...st.queue.filter(r => r.book.id !== rec.book.id)];
    st.decided = Math.max(0, st.decided - 1); st.recent = st.recent.filter(r => r.book.id !== rec.book.id);
    render(); renderRecent(); refill(); const t = await api('/users/me/taste').catch(() => null); if (t) setMeter(host, t);
  }

  /* Re-rank: ask the engine for a fresh deck that excludes the card on top, keep that card, replace the rest. */
  async function refill(initial = false) {
    const seq = ++st.seq;
    const top = st.queue[0];
    try {
      const d = await api(`/recommendations/deck?limit=8${top ? `&exclude=${top.book.id}` : ''}`);
      if (seq !== st.seq) return;                       // a newer swipe superseded this response
      st.queue = [...(top ? [top] : []), ...d.cards.filter(c => c.book.id !== top?.book.id)];
      setMeter(host, d.taste); render();
    } catch (e) { if (initial) host.innerHTML = `<div class="empty" role="alert">${esc(e.message)}<br><br><button class="btn ghost" id="retry">Try again</button></div>`, $('#retry', host)?.addEventListener('click', () => mountDeck(host, opts)); }
  }

  function renderRecent() {
    $('#recent', host).innerHTML = st.recent.length ? `<div class="panel-card"><h3 style="margin-bottom:8px">Just decided</h3><ul style="list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px">
      ${st.recent.slice(0, 5).map(r => `<li class="row" style="flex-wrap:nowrap"><span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"><span aria-hidden="true">${{ interested: '❤', not_interested: '✕', saved: '+', read: '✓' }[r.action]}</span> ${esc(r.book.title)}</span>
      <button class="btn ghost sm" data-undo="${r.book.id}">Undo</button></li>`).join('')}</ul></div>` : '';
    $$('[data-undo]', host).forEach(b => b.onclick = async () => {
      const r = st.recent.find(x => x.book.id === +b.dataset.undo); if (!r) return;
      try { await undoDecision(r.book); await undo({ book: r.book, reason: '', personalised: false, match_pct: 0, algorithm: 'popularity' }); } catch (e) { toast(e.message); }
    });
  }

  $$('.deck-btns [data-d]', host).forEach(b => b.onclick = () => decideTop(b.dataset.d));
  deck.addEventListener('keydown', e => {
    const m = { ArrowRight: 'interested', ArrowLeft: 'not_interested', ArrowUp: 'read', ArrowDown: 'saved' }[e.key];
    if (m) { e.preventDefault(); decideTop(m); }
    else if (e.key === 'Enter' && st.queue[0]) { const t = document.createElement('button'); t.dataset.open = st.queue[0].book.id; deck.append(t); t.click(); t.remove(); }
  });
  $('#metermount', host).innerHTML = meterHTML(0, 0);
  await refill(true);
  deck.focus({ preventScroll: true });
}
