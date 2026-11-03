/* Admin console: dashboard, books (with cover / pages / mood tags), moderation, users, recommendation analytics. */
import { api } from './api.js';
import { $, $$, esc, state, toast, busy, stars, animateBars } from './util.js';

let adminTab = 'stats';
const TABS = [['stats', 'Dashboard'], ['analytics', 'Recommendation analytics'], ['books', 'Manage books'], ['reviews', 'Moderate reviews'], ['users', 'Users']];

export async function renderAdmin(view) {
  view.innerHTML = `<h2 class="sr" tabindex="-1">Admin</h2><div class="tabs" role="tablist" aria-label="Admin sections">${TABS.map(([k, l]) => `<button role="tab" aria-selected="${k === adminTab}" class="btn ${k === adminTab ? '' : 'ghost'} sm" data-tab="${k}">${l}</button>`).join('')}</div><div id="adm"></div>`;
  $$('[data-tab]', view).forEach(b => b.onclick = () => { adminTab = b.dataset.tab; renderAdmin(view); });
  try { await ({ stats, analytics, books, reviews, users }[adminTab])(); } catch (e) { $('#adm').innerHTML = `<div class="empty" role="alert">${esc(e.message)}</div>`; }
}

async function stats() {
  const s = await api('/admin/stats');
  $('#adm').innerHTML = `<div class="stat"><div><b>${s.users}</b>users</div><div><b>${s.books}</b>books</div><div><b>${s.reviews}</b>ratings</div><div><b>${s.wishlist_items}</b>wishlist items</div><div><b>${s.average_rating ?? '–'}</b>avg rating</div></div>
    <h3>Top rated</h3><div class="tablewrap"><table>${s.top_books.map(b => `<tr><td>${esc(b.title)}</td><td class="stars">${stars(b.avg_rating)} ${b.avg_rating}</td><td>${b.ratings_count} ratings</td></tr>`).join('')}</table></div>
    <h3 style="margin-top:24px">Import from Open Library</h3><p class="muted">Imports titles with cover IDs and page counts where Open Library has them.</p>
    <form class="row" id="olf"><input id="olq" placeholder="e.g. machine learning" required minlength="2" aria-label="Open Library search" style="flex:1"><button class="btn">Import up to 10</button></form>`;
  $('#olf').onsubmit = e => { e.preventDefault(); busy($('#olf button'), async () => { try { const r = await api(`/admin/import/openlibrary?query=${encodeURIComponent($('#olq').value.trim())}&limit=10`, { method: 'POST' }); toast(`Imported ${r.created}, skipped ${r.skipped}`); } catch (err) { toast(err.message); } }); };
}

/* single-hue horizontal bars; counts printed at the end of every bar (no colour-only encoding) */
function barList(items, key = 'count') {
  const max = Math.max(1, ...items.map(i => i[key]));
  return items.length ? `<div class="bars">${items.map(i => `<div class="bar-row" style="grid-template-columns:200px 1fr 40px"><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(i.title)}">${esc(i.title)}</span><div class="track" aria-hidden="true"><i data-p="${i[key] / max}"></i></div><b>${i[key]}</b></div>`).join('')}</div>` : '<p class="muted">No data yet.</p>';
}
async function analytics() {
  const a = await api('/admin/analytics');
  const rate = a.acceptance_rate == null ? '–' : Math.round(a.acceptance_rate * 100) + '%';
  $('#adm').innerHTML = `<div class="stat"><div><b>${rate}</b>acceptance rate</div><div><b>${a.totals.interested}</b>interested</div><div><b>${a.totals.saved}</b>saved</div><div><b>${a.totals.read}</b>already read</div><div><b>${a.totals.not_interested}</b>not for me</div></div>
    <p class="muted">Acceptance rate = (interested + saved + read) ÷ all decisions.</p>
    <div class="grid2"><section class="panel-card"><h3>Most liked books</h3>${barList(a.most_liked)}</section><section class="panel-card"><h3>Most rejected books</h3>${barList(a.most_rejected)}</section>
    <section class="panel-card"><h3>Why people say “not for me”</h3>${barList(Object.entries(a.reject_reasons).map(([k, v]) => ({ title: { too_long: 'Too long', not_my_genre: 'Not my genre', know_story: 'I know the story', none: 'No reason given' }[k] || k, count: v })))}</section></div>`;
  animateBars($('#adm'));
}

async function books() {
  const moods = state.moods || await api('/moods');
  $('#adm').innerHTML = `<form class="form panel-card" id="abf" style="margin:0 0 24px;max-width:none"><h3>Add a book</h3>
    <div class="filters" style="grid-template-columns:1fr 1fr"><div><label for="bt">Title *</label><input id="bt" required maxlength="255"></div><div><label for="ba">Authors * (comma separated)</label><input id="ba" required></div>
    <div><label for="bg">Genres * (comma separated)</label><input id="bg" required></div><div><label for="by">Year</label><input id="by" type="number" min="0" max="2100"></div>
    <div><label for="bc">Cover URL (https)</label><input id="bc" type="url" placeholder="https://covers.openlibrary.org/b/isbn/…-L.jpg"></div><div><label for="bp">Page count</label><input id="bp" type="number" min="1" max="10000"></div></div>
    <fieldset style="border:0;padding:0;margin:10px 0 0"><legend class="muted" style="font-size:.85rem">Mood tags (leave empty to derive them automatically)</legend><div class="chips">${moods.map(m => `<label class="chip"><input type="checkbox" value="${m.key}">${m.emoji} ${esc(m.label)}</label>`).join('')}</div></fieldset>
    <label class="f" for="bd">Description</label><textarea id="bd" rows="2"></textarea><div class="err" id="aberr" role="alert"></div><button class="btn" style="margin-top:6px">Add book</button></form><div id="alist"></div>`;
  $('#abf').onsubmit = e => { e.preventDefault(); const split = s => s.split(',').map(x => x.trim()).filter(Boolean); const tags = $$('#abf fieldset input:checked').map(i => i.value);
    busy($('#abf .btn'), async () => { try {
      await api('/admin/books', { method: 'POST', body: { title: $('#bt').value.trim(), authors: split($('#ba').value), genres: split($('#bg').value), publication_year: +$('#by').value || null, description: $('#bd').value.trim() || null, cover_url: $('#bc').value.trim() || null, page_count: +$('#bp').value || null, mood_tags: tags.length ? tags : null } });
      toast('Book added'); $('#abf').reset(); $('#aberr').textContent = ''; list(); } catch (err) { $('#aberr').textContent = err.message; } }); };
  await list();
}
async function list() {
  const p = await api('/books?limit=100');
  $('#alist').innerHTML = `<p class="muted">Showing ${p.items.length} of ${p.total} books</p><div class="tablewrap"><table><thead><tr><th>Title</th><th>Authors</th><th>Pages</th><th>Moods</th><th></th></tr></thead><tbody>${p.items.map(b => `<tr><td>${esc(b.title)}</td><td>${esc(b.authors.join(', '))}</td><td>${b.page_count ?? '–'}</td><td>${esc(b.mood_tags.join(', '))}</td><td><button class="btn danger sm" data-del="${b.id}" data-t="${esc(b.title)}">Delete</button></td></tr>`).join('')}</tbody></table></div>`;
  $$('[data-del]').forEach(btn => btn.onclick = () => { if (!confirm(`Delete “${btn.dataset.t}” and all its ratings?`)) return; busy(btn, async () => { try { await api('/admin/books/' + btn.dataset.del, { method: 'DELETE' }); toast('Deleted'); list(); } catch (err) { toast(err.message); } }); });
}
async function reviews() {
  const rows = await api('/admin/reviews?limit=100');
  $('#adm').innerHTML = rows.length ? `<div class="tablewrap"><table><thead><tr><th>User</th><th>Book</th><th>Review</th><th></th></tr></thead><tbody>${rows.map(r => `<tr><td>${esc(r.user_name)}<div class="muted">${esc(r.user_email)}</div></td><td>${esc(r.book_title)}<div class="stars">${stars(r.rating)}</div></td><td>${esc(r.comment)} ${r.is_hidden ? '<span class="chip">hidden</span>' : ''}</td>
    <td><button class="btn ${r.is_hidden ? 'ghost' : 'danger'} sm" data-hide="${r.user_id}/${r.book_id}" data-h="${!r.is_hidden}">${r.is_hidden ? 'Unhide' : 'Hide'}</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="empty">Nothing to moderate.</div>';
  $$('[data-hide]').forEach(btn => btn.onclick = () => busy(btn, async () => { try { await api(`/admin/reviews/${btn.dataset.hide}?hidden=${btn.dataset.h}`, { method: 'PATCH' }); toast(btn.dataset.h === 'true' ? 'Review hidden' : 'Review restored'); reviews(); } catch (err) { toast(err.message); } }));
}
async function users() {
  const rows = await api('/admin/users?limit=500');
  $('#adm').innerHTML = `<p class="muted">${rows.length} accounts. Deactivated users cannot log in and their token stops working immediately.</p><div class="tablewrap"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Ratings</th><th>Status</th><th></th></tr></thead><tbody>${rows.map(u => `<tr><td>${esc(u.name)}</td><td>${esc(u.email)}</td><td>${esc(u.role)}</td><td>${u.reviews_count}</td>
    <td>${u.is_active ? 'Active' : '<span class="chip">deactivated</span>'}</td><td>${u.role === 'admin' ? '' : `<button class="btn ${u.is_active ? 'danger' : 'ghost'} sm" data-act="${u.id}" data-on="${!u.is_active}">${u.is_active ? 'Deactivate' : 'Activate'}</button>`}</td></tr>`).join('')}</tbody></table></div>`;
  $$('[data-act]').forEach(btn => btn.onclick = () => { if (btn.dataset.on === 'false' && !confirm('Deactivate this account?')) return; busy(btn, async () => { try { await api(`/admin/users/${btn.dataset.act}/active?active=${btn.dataset.on}`, { method: 'PATCH' }); toast(btn.dataset.on === 'true' ? 'Account activated' : 'Account deactivated'); users(); } catch (err) { toast(err.message); } }); });
}
