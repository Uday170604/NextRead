/* Home: hero "Your next read", mood picker, weekly picks, Netflix-style rows. */
import { api } from './api.js';
import { $, $$, esc, state, toast, stars, ringHTML, animateRings, heartBurst, nav, sleep, reduced } from './util.js';
import { coverHTML, book3dHTML, attachTilt, enableGyro, gyroNeedsPermission } from './cover.js';
import { decide, decisionSnack, askRating, requireLogin } from './actions.js';
import { cardHTML, railHTML, wireRails, mountRows, skeletonRail } from './rows.js';
import { openShare } from './share.js';
import { startOnboarding } from './onboarding.js';

let heroSeen = [];

export async function renderHome(view) {
  if (!state.me) return renderLanding(view);
  const taste = await api('/users/me/taste');
  if (taste.needs_onboarding) return startOnboarding(view);
  view.innerHTML = `<h2 class="sr" tabindex="-1">Home</h2><section id="hero" aria-label="Your next read"></section>
    <section aria-labelledby="mh"><div class="section-head" style="margin-top:26px"><h2 id="mh" style="font-size:1.4rem">In the mood for…</h2><p class="muted">Pick one or two — we re-rank with plain, visible rules.</p></div>
    <div class="moods" id="moods" role="group" aria-label="Moods"></div><div id="moodres" class="mood-results" aria-live="polite"></div></section>
    <div id="weekly"></div><div id="rows">${skeletonRail()}</div>`;
  loadHero();
  initMoods();
  const [rows, weekly] = await Promise.all([api('/recommendations/rows'), api('/recommendations/weekly').catch(() => null)]);
  if (weekly) renderWeekly(weekly);
  mountRows($('#rows', view), rows);
}

/* ---------------- hero ---------------- */
async function loadHero(swap = false) {
  const host = $('#hero'); if (!host) return;
  let rec;
  try { rec = await api(`/recommendations/featured${heroSeen.length ? `?exclude=${heroSeen.join(',')}` : ''}`); }
  catch (e) {
    if (heroSeen.length) { heroSeen = []; return loadHero(swap); }
    host.innerHTML = `<div class="empty"><h3>You've decided on every book</h3><p>${esc(e.message)}</p><a class="btn" href="#taste">See your taste</a></div>`; return;
  }
  const b = rec.book;
  const html = `<div class="hero" id="herobox"><div>${book3dHTML(b)}
      <div style="text-align:center"><button class="chip tilt-btn ${gyroNeedsPermission() ? 'show' : ''}" id="tiltBtn">Enable tilt</button></div></div>
    <div><div class="kicker">Start with this one</div><h1 id="htitle">${esc(b.title)}</h1><div class="by">by ${esc(b.authors.join(', '))}${b.publication_year ? `, ${b.publication_year}` : ''}</div>
      <div class="hero-meta">${rec.personalised ? `<div>${ringHTML(rec.match_pct)}<small class="muted" style="display:block;text-align:center;font-size:.7rem">match</small></div>` : ''}
        <div><div class="stars" role="img" aria-label="Community rating ${b.avg_rating ?? 'none'}">${stars(b.avg_rating)} <b>${b.avg_rating ?? '–'}</b></div><div class="muted" style="font-size:.85rem">${b.ratings_count} ratings${b.page_count ? ` · ${b.page_count} pages` : ''}</div></div></div>
      <p class="reason">${esc(rec.reason)}</p>
      <div class="chips">${b.genres.map(g => `<span class="chip">${esc(g)}</span>`).join('')}</div>
      <div class="actions" role="group" aria-label="What do you think of ${esc(b.title)}?">
        <button class="act love" data-h="interested">❤ Interested</button><button class="act" data-h="not_interested">✕ Not for me</button>
        <button class="act" data-h="saved">Save for later</button><button class="act" data-h="read">✓ Already read it</button></div>
      <div class="actions" style="margin-top:10px"><button class="btn ghost" id="another">Show me another</button><button class="btn ghost" data-open="${b.id}">Why this pick? Details</button></div></div></div>`;
  const apply = () => {
    host.innerHTML = html; const box = $('#herobox', host);
    animateRings(host); attachTilt($('[data-scene]', host));
    $('#tiltBtn', host)?.addEventListener('click', async e => { if (await enableGyro($('[data-scene]', host))) e.target.hidden = true; });
    $('#another', host).onclick = () => next(b.id);
    $$('[data-h]', host).forEach(btn => btn.onclick = () => choose(btn, b));
    if (swap && !reduced()) { box.classList.add('entering'); requestAnimationFrame(() => requestAnimationFrame(() => box.classList.remove('entering'))); }
  };
  if (swap && !reduced() && $('#herobox', host)) { $('#herobox', host).classList.add('leaving'); await sleep(280); }
  apply();
}
async function next(currentId) { heroSeen.push(currentId); loadHero(true); }
async function choose(btn, b) {
  const action = btn.dataset.h;
  try {
    let opts = {};
    if (action === 'read') { const r = await askRating(b); if (!r) return; opts = r; }
    await decide(b, action, opts);
    if (action === 'interested') heartBurst(btn);
    decisionSnack(b, action, { onUndo: () => { heroSeen = heroSeen.filter(i => i !== b.id); loadHero(true); } });
    await sleep(action === 'interested' ? 650 : 150);
    loadHero(true);
  } catch (e) { toast(e.message); }
}

/* ---------------- moods ---------------- */
async function initMoods() {
  const box = $('#moods'); if (!box) return;
  if (!state.moods) state.moods = await api('/moods').catch(() => []);
  let sel = [];
  box.innerHTML = state.moods.map(m => `<button class="chip" data-m="${m.key}" aria-pressed="false" title="${esc(m.blurb)}">${m.emoji} ${esc(m.label)}</button>`).join('');
  box.onclick = async e => {
    const c = e.target.closest('[data-m]'); if (!c) return;
    const k = c.dataset.m;
    sel = sel.includes(k) ? sel.filter(x => x !== k) : [...sel, k].slice(-2);
    $$('[data-m]', box).forEach(x => x.setAttribute('aria-pressed', String(sel.includes(x.dataset.m))));
    const out = $('#moodres');
    if (!sel.length) { out.innerHTML = ''; return; }
    out.innerHTML = `<div style="margin-top:14px">${skeletonRail(5)}</div>`;
    try {
      const recs = await api(`/recommendations/mood?moods=${sel.join(',')}&limit=12`);
      out.innerHTML = recs.length ? `<p class="mood-note">Score = 60% mood fit (genre, keywords, length) + 40% your usual match. Each card says which signals fired.</p>${railHTML(recs, { })}`
        : `<div class="empty">Nothing left that fits this combination. Try one mood, or a different pair.</div>`;
      if (recs.length) {
        $$('.rcard', out).forEach((c, i) => { const cap = $('.cap', c); cap.insertAdjacentHTML('beforeend', `<div class="reason-s">${esc(recs[i].mood_signals?.[0]?.split(': ').slice(1).join(': ') || recs[i].reason)}</div>`); });
        wireRails(out); animateRings(out);
      }
    } catch (err) { out.innerHTML = `<div class="empty" role="alert">${esc(err.message)}</div>`; }
  };
}

/* ---------------- weekly card ---------------- */
function renderWeekly(w) {
  const host = $('#weekly'); if (!host) return;
  host.innerHTML = `<section class="weekly" aria-labelledby="wh"><div><div style="opacity:.75;font-size:.85rem">${esc(w.week_label)}</div><h3 id="wh">Your picks, ${esc(w.name)}</h3>
    <div class="wstats"><div><b>${w.rated}</b><span>rated</span></div><div><b>${w.interested}</b><span>interested</span></div><div><b>${w.saved}</b><span>saved</span></div><div><b>${w.passed}</b><span>passed</span></div>
    <div><b>${w.taste.learned_pct}%</b><span>taste learned</span></div></div>
    ${w.top_genre ? `<p style="margin:12px 0 0;opacity:.85">You're leaning towards <b>${esc(w.top_genre)}</b>. Here's what we'd read next:</p>` : ''}
    <div class="actions"><button class="btn" id="wshare" style="background:var(--paper);color:var(--ink)">Share these picks</button></div></div>
    <div class="covers">${w.picks.map(p => `<button data-open="${p.book.id}" aria-label="${esc(p.book.title)}, ${p.match_pct}% match">${cardCover(p.book)}</button>`).join('')}</div></section>`;
  $('#wshare', host).onclick = () => openShare({ name: state.me.name.split(' ')[0], picks: w.picks });
}
const cardCover = b => coverHTML(b, 'sm');

/* ---------------- logged-out landing ---------------- */
async function renderLanding(view) {
  const recs = await api('/recommendations/trending?limit=12');
  const top = recs[0].book;
  view.innerHTML = `<h2 class="sr" tabindex="-1">Welcome</h2><div class="hero"><div>${book3dHTML(top)}</div>
    <div><div class="kicker" style="color:var(--accent);font-weight:600">What should I read next?</div><h1 style="font-size:clamp(2.2rem,5vw,3.8rem)">Find a book worth staying up for.</h1>
    <p class="reason">Swipe, rate and tell us your mood. NextRead learns your taste and shows you why every book is a match.</p>
    <div class="actions"><a class="btn" href="#signup">Create a free account</a><a class="btn ghost" href="#login">Log in</a></div>
    <p class="muted" style="margin-top:14px;font-size:.9rem">Right now readers love <button class="chip" data-open="${top.id}">${esc(top.title)}</button></p></div></div>
    <div class="section-head"><h2 style="font-size:1.4rem">Trending now</h2><p class="muted">Log in for picks tailored to you</p></div>${railHTML(recs)}`;
  attachTilt($('[data-scene]', view)); wireRails(view);
}
