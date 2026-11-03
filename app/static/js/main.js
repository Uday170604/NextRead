/* App shell: hash router, navigation, session, boot. */
import { $, esc, state, toast, nav } from './util.js';
import { api, loadToken, saveToken, NetworkError } from './api.js';
import { initTheme, toggleTheme, toggleMotion, isDark } from './theme.js';
import { initDetail, openBook } from './detail.js';
import { loadDecisions } from './actions.js';
import { renderHome } from './home.js';
import { renderBrowse } from './browse.js';
import { renderTaste } from './taste.js';
import { renderLogin, renderSignup, renderProfile } from './auth.js';
import { renderAdmin } from './admin.js';
import { mountDeck } from './deck.js';
import { cardHTML } from './rows.js';

initTheme();
const NAME = 'NextRead';
const ROUTES = {
  home: { title: 'Home', fn: renderHome }, match: { title: 'Book Match', fn: v => mountDeck(v, {}), auth: 1 },
  browse: { title: 'Browse', fn: renderBrowse }, taste: { title: 'My Taste', fn: renderTaste, auth: 1 },
  profile: { title: 'Profile', fn: v => renderProfile(v, onSession), auth: 1 }, admin: { title: 'Admin', fn: renderAdmin, admin: 1 },
  login: { title: 'Log in', fn: v => renderLogin(v, onSession) }, signup: { title: 'Sign up', fn: v => renderSignup(v, onSession) },
};
const NAVS = [['home', 'Home'], ['match', 'Match', 1], ['browse', 'Browse'], ['taste', 'My Taste', 1]];

async function onSession() { await loadDecisions(); renderChrome(); }
function parse() {
  const h = location.hash.slice(1) || 'home', [k, ...rest] = h.split('/');
  return { k, rest };
}
let seq = 0;
async function render() {
  const mySeq = ++seq, { k, rest } = parse(), view = $('#view');
  let key = k;
  if (k === 'book') key = 'home';
  else if (k === 'picks') key = 'picks';
  else if (!ROUTES[k]) key = 'home';
  const r = ROUTES[key] || { title: 'Shared picks' };
  if (r.auth && !state.me) { toast('Please log in first'); history.replaceState(null, '', '#login'); return render(); }
  if (r.admin && state.me?.role !== 'admin') { toast('Admins only'); history.replaceState(null, '', '#home'); return render(); }
  if ((key === 'login' || key === 'signup') && state.me) { history.replaceState(null, '', '#home'); return render(); }
  renderChrome(key);
  document.title = `${r.title} — ${NAME}`;
  view.innerHTML = '<div class="empty"><div class="skel" style="height:260px"></div></div>';
  try {
    if (k === 'picks') await renderPicks(view, rest);
    else if (key === 'match') await mountDeck(view, {});
    else await r.fn(view);
  } catch (e) {
    if (mySeq === seq) view.innerHTML = `<div class="empty" role="alert"><h3>${e instanceof NetworkError ? 'Connection problem' : 'Something went wrong'}</h3><p>${esc(e.message)}</p><button class="btn ghost" id="retry">Try again</button></div>`;
    $('#retry')?.addEventListener('click', render); return;
  }
  if (mySeq !== seq) return;
  const h = $('#view h1, #view h2'); if (h) { h.tabIndex = -1; h.focus({ preventScroll: true }); }
  if (k === 'book' && rest[0]) openBook(+rest[0]);
}

async function renderPicks(view, rest) {
  const ids = (rest[0] || '').split('-').map(Number).filter(Boolean).slice(0, 3), who = decodeURIComponent(rest[1] || 'a friend');
  const books = (await Promise.all(ids.map(i => api('/books/' + i).catch(() => null)))).filter(Boolean);
  view.innerHTML = `<h2 tabindex="-1" style="margin-bottom:6px">${NAME} picks for ${esc(who)}</h2><p class="muted">Three books chosen to match their taste. <a href="#signup">Get your own picks</a>.</p>
    <div class="grid" style="margin-top:20px">${books.map(b => cardHTML(b)).join('') || '<div class="empty">These picks are no longer available.</div>'}</div>`;
  document.title = `${NAME} picks for ${who}`;
}

function renderChrome(active = parse().k) {
  const k = active === 'book' ? 'home' : active;
  const tabs = NAVS.filter(t => !t[3] || state.me);
  const link = (t, cls = '') => `<a href="#${t[0]}" ${k === t[0] ? 'aria-current="page"' : ''}>${t[1]}</a>`;
  $('#nav').innerHTML = tabs.map(t => link(t)).join('') + (state.me ? `<a href="#profile" ${k === 'profile' ? 'aria-current="page"' : ''}>Profile</a>` : '') + (state.me?.role === 'admin' ? `<a href="#admin" ${k === 'admin' ? 'aria-current="page"' : ''}>Admin</a>` : '');
  $('#tabbar').innerHTML = tabs.map(t => link(t, 1)).join('') + (state.me ? `<a href="#profile" ${k === 'profile' ? 'aria-current="page"' : ''}>Me</a>` : `<a href="#login">Log in</a>`);
  $('#who').innerHTML = state.me ? `<span class="muted who-name">${esc(state.me.name)}</span> <button class="btn ghost sm" id="logout">Log out</button>`
    : `<a class="btn ghost sm" href="#login">Log in</a> <a class="btn sm" href="#signup">Sign up</a>`;
  $('#logout')?.addEventListener('click', logout);
  $('#themeBtn').textContent = isDark() ? 'Light' : 'Dark'; $('#themeBtn').setAttribute('aria-label', isDark() ? 'Switch to day theme' : 'Switch to night theme');
  const reduced = document.documentElement.dataset.motion === 'reduced';
  $('#motionBtn').setAttribute('aria-pressed', String(reduced)); $('#motionBtn').title = reduced ? 'Motion reduced (click to enable 3D motion)' : 'Reduce motion';
}
function logout() { saveToken(null); state.me = null; state.decisions = new Map(); renderChrome(); nav('home'); toast('Logged out'); }
function endSession() { saveToken(null); state.me = null; state.decisions = new Map(); renderChrome(); if (!['home', 'browse', 'login', 'signup', 'picks', 'book'].includes(parse().k)) nav('login'); }

window.addEventListener('hashchange', render);
window.addEventListener('nr:render', render);
window.addEventListener('nr:logout', endSession);
window.addEventListener('online', () => $('#offline').hidden = true);
window.addEventListener('offline', () => $('#offline').hidden = false);
$('#themeBtn').onclick = () => { toggleTheme(); renderChrome(); };
$('#motionBtn').onclick = () => { toggleMotion(); renderChrome(); toast(document.documentElement.dataset.motion === 'reduced' ? 'Motion reduced: flat covers, no tilt' : '3D motion on'); render(); };
initDetail();

(async function boot() {
  loadToken();
  if (state.token) { try { state.me = await api('/users/me'); await loadDecisions(); } catch (e) { if (!(e instanceof NetworkError)) { saveToken(null); state.me = null; } } }
  if (!navigator.onLine) $('#offline').hidden = false;
  render();
})();
