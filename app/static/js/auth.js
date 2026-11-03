/* Login, sign-up and profile views. */
import { api, saveToken } from './api.js';
import { $, $$, esc, state, toast, busy, nav } from './util.js';

export function renderLogin(view, onSession) {
  view.innerHTML = `<form class="form panel-card" id="lf"><h2 tabindex="-1">Welcome back</h2>
    <label class="f" for="le">Email</label><input id="le" type="email" required autocomplete="username">
    <label class="f" for="lp">Password</label><input id="lp" type="password" required autocomplete="current-password">
    <div class="err" id="lerr" role="alert"></div><button class="btn" style="width:100%">Log in</button>
    <p class="muted" style="font-size:.85rem;margin-top:14px">No account? <a href="#signup">Sign up</a><br><br>Demo accounts (password <code>Password@123</code>): emma@example.com · john@example.com · prof.rao@example.com · alex@example.com (brand-new reader, try onboarding).<br>Admin: admin@bookrec.local / Admin@12345</p></form>`;
  $('#le').focus();
  $('#lf').onsubmit = e => { e.preventDefault(); busy($('#lf .btn'), async () => { try {
    const r = await api('/auth/login', { method: 'POST', form: { username: $('#le').value.trim(), password: $('#lp').value } });
    saveToken(r.access_token); state.me = r.user; await onSession(); toast('Welcome, ' + state.me.name.split(' ')[0]); nav('home');
  } catch (err) { $('#lerr').textContent = err.message; } }); };
}

export async function renderSignup(view, onSession) {
  view.innerHTML = `<form class="form panel-card" id="sf"><h2 tabindex="-1">Create your account</h2>
    <label class="f" for="sn">Full name</label><input id="sn" required minlength="2" maxlength="100" autocomplete="name">
    <label class="f" for="se">Email</label><input id="se" type="email" required autocomplete="username">
    <label class="f" for="sp">Password (min 8 characters)</label><input id="sp" type="password" required minlength="8" autocomplete="new-password">
    <label class="f" for="sr">I am a…</label><select id="sr"><option>reader</option><option>student</option><option>professor</option></select>
    <p class="muted" style="font-size:.85rem">After signing up we'll ask about your favourite genres and moods, then you'll swipe a few books.</p>
    <div class="err" id="serr" role="alert"></div><button class="btn" style="width:100%">Sign up</button>
    <p class="muted" style="font-size:.85rem;margin-top:12px">Already registered? <a href="#login">Log in</a></p></form>`;
  $('#sn').focus();
  $('#sf').onsubmit = e => { e.preventDefault(); busy($('#sf .btn'), async () => { try {
    const email = $('#se').value.trim(), password = $('#sp').value;
    await api('/auth/register', { method: 'POST', body: { name: $('#sn').value.trim(), email, password, role: $('#sr').value } });
    const r = await api('/auth/login', { method: 'POST', form: { username: email, password } });
    saveToken(r.access_token); state.me = r.user; await onSession(); toast('Account created — welcome!'); nav('home');
  } catch (err) { $('#serr').textContent = err.message; } }); };
}

export async function renderProfile(view, onSession) {
  const [genres, authors] = await Promise.all([api('/genres'), api('/authors')]);
  const me = state.me = await api('/users/me');
  view.innerHTML = `<div class="form panel-card" style="max-width:600px"><h2 tabindex="-1">Profile &amp; preferences</h2>
    <form id="pf"><label class="f" for="pn">Name</label><input id="pn" value="${esc(me.name)}" required minlength="2" maxlength="100" autocomplete="name">
    <label class="f" for="pe">Email</label><input id="pe" value="${esc(me.email)}" disabled>
    <label class="f" for="pr">I am a…</label><select id="pr" ${me.role === 'admin' ? 'disabled' : ''}>${['reader', 'student', 'professor', 'admin'].filter(r => r !== 'admin' || me.role === 'admin').map(r => `<option ${r === me.role ? 'selected' : ''}>${r}</option>`).join('')}</select>
    <label class="f" for="pd">Date of birth ${me.age != null ? `<span class="muted">(age ${me.age})</span>` : ''}</label><input type="date" id="pd" value="${me.date_of_birth || ''}" max="${new Date().toISOString().slice(0, 10)}">
    <label class="f" for="pc">City</label><input id="pc" value="${esc(me.city || '')}" autocomplete="address-level2">
    <button class="btn" style="margin-top:14px" type="submit">Save profile</button></form>
    <h3 style="margin-top:28px">Reading preferences</h3>
    <form id="prf"><fieldset style="border:0;padding:0;margin:0"><legend class="muted" style="font-size:.85rem;margin:10px 0 6px">Favourite genres</legend>
    <div class="chips" id="fg">${genres.map(g => `<label class="chip"><input type="checkbox" value="${esc(g)}" ${me.favorite_genres.includes(g) ? 'checked' : ''}>${esc(g)}</label>`).join('')}</div></fieldset>
    <label class="f" for="fa">Favourite authors (comma separated, must exist in the catalogue)</label><input id="fa" list="authors" value="${esc(me.favorite_authors.join(', '))}">
    <datalist id="authors">${authors.map(a => `<option value="${esc(a)}">`).join('')}</datalist>
    <button class="btn" style="margin-top:14px" type="submit">Update preferences</button></form></div>`;
  $('#pf').onsubmit = e => { e.preventDefault(); busy($('#pf button'), async () => { try {
    state.me = await api('/users/me', { method: 'PUT', body: { name: $('#pn').value.trim(), ...(me.role === 'admin' ? {} : { role: $('#pr').value }), date_of_birth: $('#pd').value || null, city: $('#pc').value.trim() || null } });
    await onSession(); toast('Profile saved'); nav('profile'); } catch (err) { toast(err.message); } }); };
  $('#prf').onsubmit = e => { e.preventDefault(); busy($('#prf button'), async () => { try {
    const known = new Set(authors.map(a => a.toLowerCase())), typed = $('#fa').value.split(',').map(s => s.trim()).filter(Boolean);
    const unknown = typed.filter(a => !known.has(a.toLowerCase()));
    state.me = await api('/users/me/preferences', { method: 'PUT', body: { favorite_genres: $$('#fg input:checked').map(i => i.value), favorite_authors: typed } });
    toast(unknown.length ? `Saved. Not in catalogue, ignored: ${unknown.join(', ')}` : 'Preferences updated'); nav('home'); } catch (err) { toast(err.message); } }); };
}
