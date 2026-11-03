/* Shared helpers + tiny global state (no framework, no build step). */
export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const state = { me: null, token: null, decisions: new Map(), moods: null };
export const reduced = () => document.documentElement.dataset.motion === 'reduced';
export const stars = n => n ? '★'.repeat(Math.round(n)) + '☆'.repeat(5 - Math.round(n)) : '☆☆☆☆☆';
export const starLabel = n => n ? `${n} out of 5 stars` : 'not rated yet';
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const sleep = ms => new Promise(r => setTimeout(r, ms));
export const debounce = (fn, ms = 200) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

export async function busy(btn, fn) {
  if (btn) btn.disabled = true;
  try { return await fn(); } finally { if (btn) btn.disabled = false; }
}

let toastTimer;
export function toast(msg) {
  const t = $('#toast'); t.textContent = msg; t.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => t.classList.remove('show'), 2800);
}
/* screen-reader announcements (ARIA live region) */
export function announce(msg) { const l = $('#live'); if (l) { l.textContent = ''; setTimeout(() => { l.textContent = msg; }, 30); } }

export function nav(hash) { if (location.hash.slice(1) === hash) rerender(); else location.hash = hash; }
export function rerender() { window.dispatchEvent(new Event('nr:render')); }

/* snackbar with actions, e.g. "Marked interested  [Undo]" */
let snackTimer;
export function snack(message, buttons = [], ms = 6000) {
  closeSnack();
  const el = document.createElement('div');
  el.className = 'snack'; el.id = 'snack'; el.setAttribute('role', 'status');
  el.innerHTML = `<span>${esc(message)}</span>` + buttons.map((b, i) => `<button class="chip" data-i="${i}">${esc(b.label)}</button>`).join('');
  el.addEventListener('click', e => {
    const b = e.target.closest('button[data-i]'); if (!b) return;
    const spec = buttons[+b.dataset.i]; if (!spec.keep) closeSnack(); spec.onClick?.(b);
  });
  document.body.append(el);
  snackTimer = setTimeout(closeSnack, ms);
  return el;
}
export function closeSnack() { clearTimeout(snackTimer); $('#snack')?.remove(); }

/* generic modal (dialog.modal) */
export function modal(html, { label = 'Dialog' } = {}) {
  const dlg = $('#modal');
  dlg.setAttribute('aria-label', label);
  dlg.innerHTML = `<div class="dlg">${html}</div>`;
  const prev = document.activeElement;
  dlg.onclose = () => { try { prev?.focus(); } catch (e) { /* ignore */ } };
  dlg.onclick = e => { if (e.target === dlg) dlg.close(); };
  if (!dlg.open) dlg.showModal();
  return { el: dlg, close: () => dlg.close() };
}

export function ringHTML(pct, { small = false, label = 'match' } = {}) {
  const C = 2 * Math.PI * 36;
  return `<div class="ring ${small ? 'sm' : ''}" role="img" aria-label="${pct}% ${label}">
    <svg viewBox="0 0 84 84" aria-hidden="true"><circle class="bg" cx="42" cy="42" r="36"/><circle class="fg" cx="42" cy="42" r="36" stroke-dasharray="${C.toFixed(1)}" stroke-dashoffset="${C.toFixed(1)}" data-o="${(C * (1 - pct / 100)).toFixed(1)}"/></svg>
    <b aria-hidden="true">${pct}%</b></div>`;
}
export function animateRings(root = document) {
  requestAnimationFrame(() => requestAnimationFrame(() => $$('.ring .fg', root).forEach(c => { c.style.strokeDashoffset = c.dataset.o; })));
}
export function animateBars(root = document) {
  requestAnimationFrame(() => requestAnimationFrame(() => $$('[data-p]', root).forEach(el => { el.style.setProperty('--p', el.dataset.p); })));
}
export function heartBurst(btn, glyph = '❤') {
  if (reduced()) return;
  for (let i = 0; i < 7; i++) {
    const s = document.createElement('span');
    s.className = 'burst'; s.textContent = glyph; s.setAttribute('aria-hidden', 'true');
    s.style.setProperty('--bx', `${(Math.random() - .5) * 90}px`); s.style.setProperty('--by', `${-30 - Math.random() * 60}px`);
    s.style.animationDelay = `${i * 30}ms`;
    btn.append(s); setTimeout(() => s.remove(), 1000);
  }
}
