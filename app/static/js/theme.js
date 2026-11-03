/* Day / night theme + motion preference (prefers-reduced-motion by default, user override persisted). */
const root = document.documentElement;
const get = k => { try { return localStorage.getItem(k); } catch (e) { return null; } };
const set = (k, v) => { try { localStorage.setItem(k, v); } catch (e) { /* ignore */ } };
const dark = matchMedia('(prefers-color-scheme: dark)');
const rm = matchMedia('(prefers-reduced-motion: reduce)');

export const isDark = () => root.dataset.theme ? root.dataset.theme === 'dark' : dark.matches;
export function initTheme() {
  const t = get('nr_theme'); if (t) root.dataset.theme = t;
  const applyMotion = () => { const m = get('nr_motion'); root.dataset.motion = (m || (rm.matches ? 'reduced' : 'full')); };
  applyMotion(); rm.addEventListener?.('change', applyMotion);
}
export function toggleTheme() { const next = isDark() ? 'light' : 'dark'; root.dataset.theme = next; set('nr_theme', next); return next; }
export function toggleMotion() {
  const next = root.dataset.motion === 'reduced' ? 'full' : 'reduced';
  root.dataset.motion = next; set('nr_motion', next); return next;
}
