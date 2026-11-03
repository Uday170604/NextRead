/* Netflix-style rows: horizontal snap rails, lazily hydrated, keyboard navigable. */
import { esc, $, $$, reduced, state, animateRings, ringHTML } from './util.js';
import { coverHTML } from './cover.js';
import { decisionOf } from './actions.js';

const GLYPH = { interested: '❤', saved: '+', read: '✓', not_interested: '✕' };

/* item = RecommendationOut ({book, match_pct, tag...}) or a plain BookOut */
export function cardHTML(item, { extra = '', tagOverride } = {}) {
  const rec = item.book ? item : { book: item };
  const b = rec.book;
  const badge = rec.personalised ? `${rec.match_pct}%` : (b.avg_rating ? `★ ${b.avg_rating}` : '');
  const d = state.me ? decisionOf(b.id) : null;
  const tag = tagOverride ?? rec.tag ?? '';
  const label = `${b.title} by ${(b.authors || []).join(', ')}.${rec.personalised ? ` ${rec.match_pct}% match.` : ''}${rec.reason ? ' ' + rec.reason : ''}`;
  return `<button class="rcard" data-open="${b.id}" aria-label="${esc(label)}">
    <div style="position:relative">${coverHTML(b)}${badge ? `<span class="mt" aria-hidden="true">${badge}</span>` : ''}${d ? `<span class="chip state" aria-hidden="true">${GLYPH[d]}</span>` : ''}</div>
    <div class="cap"><div class="t">${esc(b.title)}</div><div class="a">${esc((b.authors || []).join(', '))}</div>
    ${tag ? `<div class="tag">${esc(tag)}</div>` : ''}${extra}</div></button>`;
}

export function railHTML(items, opts = {}) {
  return `<div class="rail-wrap"><button class="rail-nav l" aria-label="Scroll left" tabindex="-1">‹</button>
    <div class="rail" role="list" tabindex="-1">${items.map(i => `<div role="listitem" style="display:contents">${cardHTML(i, opts)}</div>`).join('')}</div>
    <button class="rail-nav r" aria-label="Scroll right" tabindex="-1">›</button></div>`;
}

export function skeletonRail(n = 7) {
  return `<div class="rail" aria-hidden="true">${Array.from({ length: n }, () => `<div class="rcard"><div class="skel cov"></div><div class="skel line"></div><div class="skel line" style="width:45%"></div></div>`).join('')}</div>`;
}

/* arrows + roving focus on every rail inside root */
export function wireRails(root) {
  $$('.rail-wrap', root).forEach(w => {
    if (w._wired) return; w._wired = true;
    const rail = $('.rail', w);
    const go = dir => rail.scrollBy({ left: dir * rail.clientWidth * .85, behavior: reduced() ? 'auto' : 'smooth' });
    $('.rail-nav.l', w).onclick = () => go(-1); $('.rail-nav.r', w).onclick = () => go(1);
    rail.addEventListener('keydown', e => {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      const cards = $$('.rcard', rail), i = cards.indexOf(document.activeElement); if (i < 0) return;
      const next = cards[i + (e.key === 'ArrowRight' ? 1 : -1)]; if (!next) return;
      e.preventDefault(); next.focus(); next.scrollIntoView({ inline: 'nearest', block: 'nearest', behavior: reduced() ? 'auto' : 'smooth' });
    });
  });
}

/* Render each row as a skeleton and hydrate it only when it nears the viewport. */
export function mountRows(container, rows) {
  container.innerHTML = '';
  const io = 'IntersectionObserver' in window ? new IntersectionObserver((entries) => {
    entries.forEach(en => { if (en.isIntersecting) { io.unobserve(en.target); hydrate(en.target); } });
  }, { rootMargin: '400px 0px' }) : null;
  const hydrate = sec => {
    const row = rows[+sec.dataset.i];
    $('.slot', sec).innerHTML = railHTML(row.items);
    wireRails(sec); animateRings(sec);
  };
  rows.forEach((row, i) => {
    const sec = document.createElement('section');
    sec.dataset.i = i; sec.setAttribute('aria-labelledby', `row-${row.id}`);
    sec.innerHTML = `<div class="section-head"><h2 id="row-${row.id}" style="font-size:1.4rem">${esc(row.title)}</h2><p class="muted">${esc(row.subtitle)}</p></div><div class="slot">${skeletonRail()}</div>`;
    container.append(sec);
    if (io && i > 0) io.observe(sec); else hydrate(sec);
  });
}
export { ringHTML };
