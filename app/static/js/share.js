/* Shareable recommendation card: drawn on a canvas, exported as PNG, plus a copy-link button. */
import { modal, toast, $ } from './util.js';
import { paletteFor } from './cover.js';

const SERIF = '"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif', SANS = 'system-ui,-apple-system,"Segoe UI",sans-serif';

function wrap(ctx, text, maxW) {
  const lines = []; let line = '';
  for (const w of String(text).split(/\s+/)) {
    const t = line ? line + ' ' + w : w;
    if (ctx.measureText(t).width > maxW && line) { lines.push(line); line = w; } else line = t;
  }
  if (line) lines.push(line); return lines;
}
const rr = (ctx, x, y, w, h, r) => { ctx.beginPath(); ctx.roundRect ? ctx.roundRect(x, y, w, h, r) : ctx.rect(x, y, w, h); };

function loadImg(url) {
  return new Promise(res => {
    if (!url) return res(null);
    const im = new Image(); im.crossOrigin = 'anonymous';
    const t = setTimeout(() => res(null), 3500);
    im.onload = () => { clearTimeout(t); res(im.naturalWidth > 2 ? im : null); };
    im.onerror = () => { clearTimeout(t); res(null); };
    im.src = url;
  });
}

function drawCover(ctx, b, img, x, y, w, h) {
  const [g1, g2, ink] = paletteFor(b);
  ctx.save(); ctx.shadowColor = 'rgba(0,0,0,.35)'; ctx.shadowBlur = 24; ctx.shadowOffsetY = 12;
  rr(ctx, x, y, w, h, 8); ctx.fillStyle = g2; ctx.fill(); ctx.restore();
  ctx.save(); rr(ctx, x, y, w, h, 8); ctx.clip();
  if (img) ctx.drawImage(img, x, y, w, h);
  else {
    const g = ctx.createLinearGradient(x, y, x + w, y + h); g.addColorStop(0, g1); g.addColorStop(1, g2);
    ctx.fillStyle = g; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = ink; ctx.textBaseline = 'top'; ctx.font = `700 ${w * .13}px ${SERIF}`;
    wrap(ctx, b.title, w * .72).slice(0, 5).forEach((l, i) => ctx.fillText(l, x + w * .14, y + h * .09 + i * w * .14));
    ctx.font = `600 ${w * .065}px ${SANS}`; ctx.fillText((b.authors || []).slice(0, 2).join(' & '), x + w * .14, y + h * .86, w * .78);
  }
  const sh = ctx.createLinearGradient(x, 0, x + w * .1, 0); sh.addColorStop(0, 'rgba(255,255,255,.2)'); sh.addColorStop(.3, 'rgba(0,0,0,.28)'); sh.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = sh; ctx.fillRect(x, y, w * .1, h); ctx.restore();
}

export async function renderShareCanvas(canvas, { name, picks }) {
  const W = 1080, H = 1350, ctx = canvas.getContext('2d'); canvas.width = W; canvas.height = H;
  const bg = ctx.createLinearGradient(0, 0, W, H); bg.addColorStop(0, '#f8f3ea'); bg.addColorStop(1, '#e9d8c4');
  ctx.fillStyle = bg; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#5b3a29'; ctx.fillRect(0, 0, W, 14);
  ctx.fillStyle = '#2a2118'; ctx.textBaseline = 'alphabetic';
  ctx.font = `700 64px ${SERIF}`; wrap(ctx, `NextRead picks for ${name}`, W - 140).forEach((l, i) => ctx.fillText(l, 70, 130 + i * 74));
  ctx.font = `500 28px ${SANS}`; ctx.fillStyle = '#685447'; ctx.fillText(`Matched to my taste · ${new Date().toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' })}`, 70, 250);
  const imgs = await Promise.all(picks.slice(0, 3).map(p => loadImg(p.book.cover_url)));
  picks.slice(0, 3).forEach((p, i) => {
    const y = 310 + i * 330, cw = 170, ch = 255;
    drawCover(ctx, p.book, imgs[i], 70, y, cw, ch);
    ctx.fillStyle = '#2a2118'; ctx.font = `700 42px ${SERIF}`;
    wrap(ctx, p.book.title, 620).slice(0, 2).forEach((l, k) => ctx.fillText(l, 290, y + 50 + k * 50));
    ctx.fillStyle = '#685447'; ctx.font = `500 28px ${SANS}`; ctx.fillText((p.book.authors || []).slice(0, 2).join(' & '), 290, y + 150, 640);
    if (p.personalised) { ctx.fillStyle = '#5b3a29'; ctx.font = `700 34px ${SANS}`; ctx.fillText(`${p.match_pct}% match`, 290, y + 205); }
    ctx.fillStyle = '#685447'; ctx.font = `italic 26px ${SERIF}`;
    wrap(ctx, p.reason || '', 700).slice(0, 2).forEach((l, k) => ctx.fillText(l, 290, y + 240 + k * 32));
  });
  ctx.fillStyle = '#2a2118'; ctx.font = `700 34px ${SERIF}`; ctx.fillText('NextRead', 70, H - 60);
  ctx.fillStyle = '#685447'; ctx.font = `500 24px ${SANS}`; ctx.fillText('What should I read next?', 220, H - 60);
}

export function shareLink(picks, name) {
  return `${location.origin}${location.pathname}#picks/${picks.slice(0, 3).map(p => p.book.id).join('-')}/${encodeURIComponent(name)}`;
}

export async function openShare({ name, picks }) {
  const link = shareLink(picks, name);
  const m = modal(`<div class="row"><h2>Share your picks</h2><button class="btn ghost sm" data-close>Close</button></div>
    <canvas id="shc" style="width:100%;border-radius:12px;margin:12px 0;border:1px solid var(--line)" role="img" aria-label="Preview of your shareable picks card"></canvas>
    <div class="row"><button class="btn" id="shdl">Download PNG</button><button class="btn ghost" id="shcopy">Copy link</button><button class="btn ghost" id="shnative" hidden>Share…</button></div>`, { label: 'Share your picks' });
  $('[data-close]', m.el).onclick = () => m.close();
  const canvas = $('#shc', m.el);
  await renderShareCanvas(canvas, { name, picks });
  const blob = () => new Promise(r => { try { canvas.toBlob(r, 'image/png'); } catch (e) { r(null); } });
  $('#shdl', m.el).onclick = async () => {
    const b = await blob(); if (!b) return toast('Could not export the image (a cover blocked canvas export).');
    const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'nextread-picks.png'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  };
  $('#shcopy', m.el).onclick = async () => { try { await navigator.clipboard.writeText(link); toast('Link copied'); } catch (e) { prompt('Copy this link', link); } };
  if (navigator.share) {
    const n = $('#shnative', m.el); n.hidden = false;
    n.onclick = async () => { const b = await blob(); const data = { title: `NextRead picks for ${name}`, url: link }; if (b && navigator.canShare?.({ files: [new File([b], 'picks.png', { type: 'image/png' })] })) data.files = [new File([b], 'picks.png', { type: 'image/png' })]; try { await navigator.share(data); } catch (e) { /* cancelled */ } };
  }
}
