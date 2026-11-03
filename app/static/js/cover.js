/* Covers: real Open Library images with a designed typographic fallback, plus the realistic 3D hardcover. */
import { esc, reduced, clamp } from './util.js';

// [gradient 1, gradient 2, ink]
const PALETTE = {
  'science fiction': ['#0f4c75', '#0a1f3d', '#e8f4ff'], 'fantasy': ['#5b2a86', '#2a1248', '#ffe9b0'],
  'mystery': ['#2d2f3a', '#14151c', '#f0d9a8'], 'thriller': ['#7a1620', '#2b0a0e', '#ffe3e0'],
  'horror': ['#222', '#4a0b12', '#f5d0d0'], 'romance': ['#c4476b', '#7d1f45', '#fff0f3'],
  'young adult': ['#e8745a', '#b83b6b', '#fff5ee'], 'classic': ['#6b5a3a', '#33291a', '#f6ebd0'],
  'historical fiction': ['#7b4a2d', '#3a2010', '#fbe9d3'], 'fiction': ['#2f6f6b', '#143b3a', '#e6fbf7'],
  'non-fiction': ['#3d6b4f', '#1c3a2b', '#eaf7ee'], 'science': ['#1d7c8c', '#0b3b46', '#e3fbff'],
  'history': ['#8a5a2b', '#47290f', '#fdeed7'], 'psychology': ['#5a4b9b', '#2a2158', '#efeaff'],
  'biography': ['#a0522d', '#4e2412', '#ffe9dc'], 'business': ['#c26a0a', '#6b3a00', '#fff1dc'],
  'self-help': ['#e0a21a', '#a35c0b', '#2b1700'], 'computer science': ['#264653', '#0e1f27', '#d8f3ff'],
  'programming': ['#264653', '#0e1f27', '#d8f3ff'], 'mathematics': ['#3a3f9b', '#171a52', '#e5e7ff'],
  'textbook': ['#34495e', '#17212b', '#e8eef4'], 'philosophy': ['#7a5c3a', '#2e2112', '#f7ecd9'],
  'dystopian': ['#3c4a52', '#10181d', '#e0f0ff'], 'artificial intelligence': ['#1d2b64', '#0b1030', '#dbe2ff'],
};
const DEFAULTS = [['#4a5568', '#1a202c', '#edf2f7'], ['#6b4f3a', '#2b1d12', '#f8ead9'], ['#375a7f', '#14243a', '#e4f0ff'], ['#7a4e6d', '#331f2d', '#fbe8f5']];

export function paletteFor(b) {
  for (const g of b.genres || []) { const p = PALETTE[g.toLowerCase()]; if (p) return p; }
  let h = 0; for (const c of b.title || '') h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return DEFAULTS[h % DEFAULTS.length];
}
export const coverVars = b => { const [a, c, i] = paletteFor(b); return `--g1:${a};--g2:${c};--gi:${i}`; };

/* A cover is always readable: the typographic fallback sits underneath, the image fades in over it. */
export function coverHTML(b, cls = '') {
  const img = b.cover_url ? `<img src="${esc(b.cover_url)}" alt="" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : '';
  return `<div class="cover ${cls}" style="${coverVars(b)}" aria-hidden="true" data-cover="${b.id ?? ''}">
    <div class="fb"><div><div class="fb-title">${esc(b.title)}</div><div class="fb-rule"></div><div class="fb-author">${esc((b.authors || []).slice(0, 2).join(' & '))}</div></div>
    <div class="fb-genre">${esc((b.genres || [])[0] || '')}</div></div>${img}</div>`;
}
// img load/error events do not bubble -> capture them once for every cover on the page
document.addEventListener('load', e => {
  const im = e.target; if (!(im instanceof HTMLImageElement) || !im.closest('.cover')) return;
  if (im.naturalWidth <= 2) { im.remove(); return; }       // Open Library 1x1 "no cover" pixel
  im.classList.add('loaded'); im.parentElement.classList.add('ok');
}, true);
document.addEventListener('error', e => { const im = e.target; if (im instanceof HTMLImageElement && im.closest('.cover')) im.remove(); }, true);

/* ---------- realistic 3D hardcover ---------- */
export function book3dHTML(b) {
  return `<div class="scene" style="${coverVars(b)}" data-scene>
    <div class="floater"><div class="book">
      <div class="face front">${coverHTML(b)}</div><div class="face back"></div><div class="face spine"></div>
      <div class="face pages"></div><div class="face edge-t"></div><div class="face edge-b"></div></div></div>
    <div class="shadow"></div></div>`;
}

const BASE_RY = -26, BASE_RX = 4;
let gyroOn = false;
export const gyroNeedsPermission = () => typeof DeviceOrientationEvent !== 'undefined' && typeof DeviceOrientationEvent.requestPermission === 'function';

/* Tilt follows the cursor (or the gyroscope on phones). Disabled entirely under reduced motion. */
export function attachTilt(scene) {
  if (!scene || reduced()) return;
  const book = scene.querySelector('.book'); if (!book) return;
  let tx = 0, ty = 0, cx = 0, cy = 0, raf = 0;
  const set = (nx, ny) => { tx = clamp(nx, -1, 1); ty = clamp(ny, -1, 1); if (!raf) raf = requestAnimationFrame(tick); };
  const tick = () => {
    raf = 0;
    if (!scene.isConnected) { window.removeEventListener('pointermove', onMove); window.removeEventListener('deviceorientation', onOrient); return; }
    cx += (tx - cx) * .12; cy += (ty - cy) * .12;
    book.style.transform = `rotateX(${(BASE_RX - cy * 16).toFixed(2)}deg) rotateY(${(BASE_RY + cx * 24).toFixed(2)}deg)`;
    scene.style.setProperty('--sx', `${(-cx * 22).toFixed(1)}px`); scene.style.setProperty('--ss', (1 + Math.abs(cx) * .12).toFixed(3));
    if (Math.abs(tx - cx) > .002 || Math.abs(ty - cy) > .002) raf = requestAnimationFrame(tick);
  };
  const onMove = e => {
    if (e.pointerType === 'touch') return;
    const r = scene.getBoundingClientRect();
    set((e.clientX - (r.left + r.width / 2)) / (innerWidth * .45), (e.clientY - (r.top + r.height / 2)) / (innerHeight * .45));
  };
  const onOrient = e => { if (e.gamma == null) return; set(clamp(e.gamma, -35, 35) / 35, clamp((e.beta ?? 45) - 45, -35, 35) / 35); };
  window.addEventListener('pointermove', onMove, { passive: true });
  if (gyroOn || (typeof DeviceOrientationEvent !== 'undefined' && !gyroNeedsPermission() && matchMedia('(pointer:coarse)').matches)) window.addEventListener('deviceorientation', onOrient, { passive: true });
  scene._enableGyro = () => window.addEventListener('deviceorientation', onOrient, { passive: true });
}
export async function enableGyro(scene) {
  try {
    if (gyroNeedsPermission()) { const r = await DeviceOrientationEvent.requestPermission(); if (r !== 'granted') return false; }
    gyroOn = true; scene?._enableGyro?.(); return true;
  } catch (e) { return false; }
}
