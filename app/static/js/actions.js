/* Decisions on books: interested / not_interested / saved / read, with undo and live taste updates. */
import { api } from './api.js';
import { state, toast, snack, modal, nav, esc, announce } from './util.js';

export const REASONS = { too_long: 'Too long', not_my_genre: 'Not my genre', know_story: 'I know the story' };
export const ACTION_LABEL = { interested: 'Interested', not_interested: 'Not for me', saved: 'Saved for later', read: 'Already read' };

export async function loadDecisions() {
  state.decisions = new Map();
  if (!state.me) return;
  try {
    const items = await api('/feedback?limit=500');
    state.decisions = new Map(items.map(i => [i.book.id, { action: i.action, reason: i.reason, rating: i.rating }]));
  } catch (e) { /* non-fatal */ }
}
export const decisionOf = id => state.decisions.get(id)?.action ?? null;

export function requireLogin(why = 'do that') {
  if (state.me) return true;
  toast(`Log in to ${why}`); nav('login'); return false;
}

export async function decide(book, action, { rating = null, reason = null } = {}) {
  const r = await api('/feedback', { method: 'POST', body: { book_id: book.id, action, rating, reason } });
  state.decisions.set(book.id, { action, reason, rating });
  window.dispatchEvent(new CustomEvent('nr:decision', { detail: { book, action, taste: r.taste } }));
  announce(`${ACTION_LABEL[action]}: ${book.title}`);
  return r;
}
export async function undoDecision(book) {
  const r = await api(`/feedback/${book.id}`, { method: 'DELETE' });
  state.decisions.delete(book.id);
  window.dispatchEvent(new CustomEvent('nr:decision', { detail: { book, action: null, taste: r.taste } }));
  announce(`Undid decision for ${book.title}`);
  return r;
}

/* Snackbar after a decision: offers Undo (and, for "not for me", a reason that tunes future picks). */
export function decisionSnack(book, action, { onUndo } = {}) {
  const buttons = [];
  if (action === 'not_interested') {
    for (const [k, label] of Object.entries(REASONS)) {
      buttons.push({ label, onClick: async () => { try { await decide(book, 'not_interested', { reason: k }); toast(`Got it — fewer picks like this (${label.toLowerCase()})`); } catch (e) { toast(e.message); } } });
    }
  }
  buttons.push({ label: 'Undo', onClick: async () => { try { await undoDecision(book); onUndo?.(); } catch (e) { toast(e.message); } } });
  const msg = action === 'not_interested' ? 'Not for me — why?' : `${ACTION_LABEL[action]}: ${book.title.length > 34 ? book.title.slice(0, 33) + '…' : book.title}`;
  return snack(msg, buttons, action === 'not_interested' ? 9000 : 6000);
}

/* Quick star rating. Resolves {rating} (null = skipped) or null when dismissed. */
export function askRating(book, current = 0) {
  return new Promise(resolve => {
    let rating = current, done = false;
    const finish = v => { if (done) return; done = true; resolve(v); };
    const m = modal(`<h2 id="rt">Already read “${esc(book.title)}”?</h2><p class="muted">How was it? Your rating sharpens every future pick.</p>
      <div class="rate" id="rq" role="group" aria-label="Star rating" style="margin:12px 0">${[1, 2, 3, 4, 5].map(i => `<button type="button" data-i="${i}" aria-label="${i} star${i > 1 ? 's' : ''}" aria-pressed="${i <= rating}" class="${i <= rating ? 'on' : ''}">★</button>`).join('')}</div>
      <div class="row"><button class="btn" id="rsave" ${rating ? '' : 'disabled'}>Save rating</button><button class="btn ghost" id="rskip">Read it, skip rating</button></div>`, { label: 'Rate this book' });
    const el = m.el;
    el.addEventListener('close', () => finish(null), { once: true });
    el.querySelector('#rq').addEventListener('click', e => {
      const b = e.target.closest('button[data-i]'); if (!b) return;
      rating = +b.dataset.i;
      el.querySelectorAll('#rq button').forEach(s => { const on = +s.dataset.i <= rating; s.classList.toggle('on', on); s.setAttribute('aria-pressed', on); });
      el.querySelector('#rsave').disabled = false;
    });
    el.querySelector('#rsave').onclick = () => { finish({ rating }); m.close(); };
    el.querySelector('#rskip').onclick = () => { finish({ rating: null }); m.close(); };
    el.querySelector('#rq button')?.focus();
  });
}
