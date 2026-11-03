import { state } from './util.js';

const KEY = 'nr_token';
export function loadToken() {
  try {
    state.token = localStorage.getItem(KEY);
    if (!state.token) {                     // one-time migration from the previous product name
      const old = localStorage.getItem('bn_token');
      if (old) { state.token = old; localStorage.setItem(KEY, old); }
    }
    localStorage.removeItem('bn_token');
  } catch (e) { /* storage unavailable */ }
}
export function saveToken(t) {
  state.token = t;
  try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
}

export class NetworkError extends Error {}

export async function api(path, { method = 'GET', body, form } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = 'Bearer ' + state.token;
  let payload;
  if (form) payload = new URLSearchParams(form);
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let res;
  try { res = await fetch(path, { method, headers, body: payload }); }
  catch (e) { throw new NetworkError(navigator.onLine === false ? 'You are offline. Reconnect and try again.' : 'Cannot reach the server. Is it running?'); }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (res.status === 401 && state.token && !form) { window.dispatchEvent(new Event('nr:logout')); throw new Error('Your session expired. Please log in again.'); }
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => (x.loc?.slice(-1)[0] ? x.loc.slice(-1)[0] + ': ' : '') + x.msg).join('; ') : (d || res.statusText));
  }
  return data;
}
