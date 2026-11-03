/* First-run onboarding: 1) genres  2) moods  3) swipe 8 books. Skippable at any point. */
import { api } from './api.js';
import { $, $$, esc, state, toast, nav, busy } from './util.js';
import { mountDeck } from './deck.js';

const GOAL = 8;
export async function startOnboarding(view) {
  const [genres, moods] = await Promise.all([api('/genres'), state.moods ? state.moods : api('/moods')]);
  state.moods = moods;
  const picked = { genres: new Set(), moods: new Set() };
  const dots = n => `<div class="step-dots" aria-label="Step ${n} of 3">${[1, 2, 3].map(i => `<i class="${i <= n ? 'on' : ''}"></i>`).join('')}</div>`;
  const finish = async () => {
    try {
      state.me = await api('/users/me/onboarding', { method: 'POST', body: { favorite_genres: [...picked.genres], favorite_moods: [...picked.moods] } });
    } catch (e) { toast(e.message); }
    toast('You\'re all set — here are your first picks'); nav('home');
  };
  const skip = `<button class="btn ghost sm" id="skip">Skip for now</button>`;
  const step1 = () => {
    view.innerHTML = `<div class="form" style="max-width:640px">${dots(1)}<h2 tabindex="-1">What do you love to read?</h2><p class="muted">Pick a few genres. You can change this any time.</p>
      <div class="chips" id="g" role="group" aria-label="Genres">${genres.map(g => `<button class="chip" aria-pressed="${picked.genres.has(g)}" data-g="${esc(g)}">${esc(g)}</button>`).join('')}</div>
      <div class="row" style="margin-top:20px"><button class="btn" id="n">Next</button>${skip}</div></div>`;
    $('#g', view).onclick = e => { const c = e.target.closest('[data-g]'); if (!c) return; const g = c.dataset.g; picked.genres.has(g) ? picked.genres.delete(g) : picked.genres.add(g); c.setAttribute('aria-pressed', picked.genres.has(g)); };
    $('#n', view).onclick = step2; $('#skip', view).onclick = finish;
  };
  const step2 = () => {
    view.innerHTML = `<div class="form" style="max-width:640px">${dots(2)}<h2 tabindex="-1">What are you in the mood for?</h2><p class="muted">Choose the feelings you chase in a good book.</p>
      <div class="chips" id="m" role="group" aria-label="Moods">${moods.map(m => `<button class="chip" aria-pressed="${picked.moods.has(m.key)}" data-m="${m.key}">${m.emoji} ${esc(m.label)}</button>`).join('')}</div>
      <div class="row" style="margin-top:20px"><div><button class="btn ghost" id="b">Back</button> <button class="btn" id="n">Next</button></div>${skip}</div></div>`;
    $('#m', view).onclick = e => { const c = e.target.closest('[data-m]'); if (!c) return; const k = c.dataset.m; picked.moods.has(k) ? picked.moods.delete(k) : picked.moods.add(k); c.setAttribute('aria-pressed', picked.moods.has(k)); };
    $('#b', view).onclick = step1; $('#skip', view).onclick = finish;
    $('#n', view).onclick = () => busy($('#n', view), async () => {
      try { state.me = await api('/users/me/onboarding', { method: 'POST', body: { favorite_genres: [...picked.genres], favorite_moods: [...picked.moods] } }); } catch (e) { return toast(e.message); }
      step3();
    });
  };
  const step3 = async () => {
    view.innerHTML = `<div style="max-width:1000px;margin:auto">${dots(3)}<div class="row"><h2 tabindex="-1">Swipe ${GOAL} books to teach us your taste</h2>${skip}</div><div id="deckhost" style="margin-top:14px"></div></div>`;
    $('#skip', view).onclick = () => { toast('Skipped — your picks will keep improving as you rate.'); nav('home'); };
    await mountDeck($('#deckhost', view), { goal: GOAL, onDone: () => { toast('Taste profile ready'); nav('home'); } });
  };
  step1();
}
