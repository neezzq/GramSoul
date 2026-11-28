/* GramSoul web — the same account, characters and chats as the Android app, for iPhone
   (Safari → «Поделиться» → «На экран „Домой“») and any browser.
   Talks to the same API on the same origin. User text is only ever inserted with
   textContent / text nodes (never innerHTML). */
'use strict';

const WEB_VERSION = '1.6';

// ------------------------------------------------------------------ helpers
const $ = (sel, root = document) => root.querySelector(sel);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'text') el.textContent = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (k === 'value') el.value = v;
      else el.setAttribute(k, v === true ? '' : String(v));
    }
  }
  for (const kid of kids.flat(3)) {
    if (kid == null || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

// append that flattens arrays and skips null/false (native append would print them)
function put(parent, ...kids) {
  parent.append(...kids.flat(3).filter((k) => k != null && k !== false));
  return parent;
}
function fill(parent, ...kids) {
  parent.replaceChildren();
  return put(parent, ...kids);
}

// small inline icons (no external files)
const ICONS = {
  back: 'M15 18l-6-6 6-6',
  book: 'M4 5a2 2 0 012-2h13v16H6a2 2 0 00-2 2zM4 5v16',
  face: 'M12 21a9 9 0 100-18 9 9 0 000 18zM9 10h.01M15 10h.01M8.5 14.5c1 1.2 2.2 1.8 3.5 1.8s2.5-.6 3.5-1.8',
  chat: 'M21 12a8 8 0 01-11.6 7.1L4 20l1.1-4.6A8 8 0 1121 12z',
  people: 'M16 19v-1a4 4 0 00-4-4H6a4 4 0 00-4 4v1M9 10a3 3 0 100-6 3 3 0 000 6zM22 19v-1a4 4 0 00-3-3.9M16 4.1a3 3 0 010 5.8',
  user: 'M20 21v-1a5 5 0 00-5-5H9a5 5 0 00-5 5v1M12 12a4 4 0 100-8 4 4 0 000 8z',
  send: 'M5 12h14M13 6l6 6-6 6',
  camera: 'M4 8h3l2-3h6l2 3h3v11H4zM12 17a4 4 0 100-8 4 4 0 000 8z',
  bulb: 'M9 18h6M10 21h4M12 3a6 6 0 00-3.5 10.9c.6.5 1 1.2 1 2.1h5c0-.9.4-1.6 1-2.1A6 6 0 0012 3z',
  cloud: 'M7 18h10a4 4 0 00.6-7.95A6 6 0 006.2 9.1 4.5 4.5 0 007 18z',
  chip: 'M7 7h10v10H7zM10 3v4M14 3v4M10 17v4M14 17v4M3 10h4M3 14h4M17 10h4M17 14h4',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  edit: 'M4 20h4L19 9l-4-4L4 16zM14 6l4 4',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  search: 'M11 18a7 7 0 110-14 7 7 0 010 14zM21 21l-5-5',
  forward: 'M5 6l7 6-7 6M12 6l7 6-7 6',
  magic: 'M5 19L19 5M15 4l1 2 2 1-2 1-1 2-1-2-2-1 2-1zM6 6l.5 1 1 .5-1 .5L6 9l-.5-1-1-.5 1-.5z',
  refresh: 'M20 11a8 8 0 10-2.3 5.7M20 4v7h-7',
  sparkle: 'M11 3l1.7 4.8L17.5 9.5l-4.8 1.7L11 16l-1.7-4.8L4.5 9.5l4.8-1.7zM18.5 14v5M16 16.5h5',
  image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15.5 8.5h.01',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13',
  speaker: 'M4 9h4l5-4v14l-5-4H4zM16.5 8.5a5 5 0 010 7M19 6a8.5 8.5 0 010 12',
  stop: 'M7 7h10v10H7z',
  play: 'M8 5v14l11-7z',
  globe: 'M12 21a9 9 0 100-18 9 9 0 000 18zM3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9s1.3-6.5 3.8-9z',
  sliders: 'M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0M14 4v4M8 10v4M16 16v4',
};
function icon(name, size = 24) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', size);
  svg.setAttribute('height', size);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.9');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', ICONS[name]);
  svg.append(p);
  return svg;
}

function uuid() {
  if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(b, (x) => x.toString(16).padStart(2, '0')).join('');
}

const COLORS = ['#8E6BBF', '#4E9F8F', '#C27B4A', '#5A7EC2', '#B45C7E', '#7D9A4B'];
function hashStr(s) { let x = 0; for (const c of s || '') x = (x * 31 + c.charCodeAt(0)) | 0; return Math.abs(x); }
const colorFor = (name) => COLORS[hashStr(name) % COLORS.length];
const GRADS = [['#7A1E52', '#2A0F22'], ['#4B2A7A', '#160F25'], ['#8A3A2A', '#221010'], ['#1F5468', '#0D1A22'], ['#6B5A1E', '#1E1A0C']];
const gradFor = (name) => { const g = GRADS[hashStr(name) % GRADS.length]; return `linear-gradient(180deg, ${g[0]}, ${g[1]})`; };

// "*улыбается* Привет" → italic action + plain speech. paragraphs: every action / spoken part on its own line
function richText(text, paragraphs) {
  const frag = document.createDocumentFragment();
  const parts = [];
  let i = 0;
  text = text || '';
  while (i < text.length) {
    const s = text.indexOf('*', i);
    const e = s >= 0 ? text.indexOf('*', s + 1) : -1;
    if (s < 0 || e < 0) { parts.push([false, text.slice(i)]); break; }
    parts.push([false, text.slice(i, s)]);
    parts.push([true, text.slice(s + 1, e)]);
    i = e + 1;
  }
  if (paragraphs) {
    let first = true;
    for (const [act, raw] of parts) {
      for (const piece of raw.split('\n')) {
        const t = piece.trim();
        if (!t || /^[.,;:!?—–-]+$/.test(t)) continue;
        if (!first) frag.append('\n');
        first = false;
        frag.append(act ? h('em', null, t) : t);
      }
    }
  } else {
    for (const [act, raw] of parts) frag.append(act ? h('em', null, raw) : raw);
  }
  return frag;
}

let toastTimer;
function toast(msg) {
  let t = $('#toast');
  if (!t) { t = h('div', { id: 'toast', class: 'toast glass' }); document.body.append(t); }
  t.textContent = msg;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 3200);
}

function sheet(title, ...content) {
  const scrim = h('div', { class: 'scrim' });
  const box = h('div', { class: 'sheet' }, title ? h('h3', null, title) : null, ...content);
  scrim.append(box);
  scrim.addEventListener('click', (e) => { if (e.target === scrim) scrim.remove(); });
  document.body.append(scrim);
  return { el: box, close: () => scrim.remove() };
}

function confirmSheet(title, text, okText, danger) {
  return new Promise((resolve) => {
    const s = sheet(title, h('p', { class: 'muted' }, text),
      h('div', { class: 'row', style: 'margin-top:14px' },
        h('button', { class: 'btn ghost grow', onclick: () => { s.close(); resolve(false); } }, 'Отмена'),
        h('button', { class: 'btn grow ' + (danger ? 'danger' : 'primary'), id: 'confirm-ok', onclick: () => { s.close(); resolve(true); } }, okText)));
  });
}

// ------------------------------------------------------------------ session & API
const store = {
  get token() { try { return localStorage.getItem('gs_token'); } catch (_) { return null; } },
  set token(v) { try { if (v) localStorage.setItem('gs_token', v); else localStorage.removeItem('gs_token'); } catch (_) {} },
  get me() { try { return JSON.parse(localStorage.getItem('gs_me') || 'null'); } catch (_) { return null; } },
  set me(v) { try { if (v) localStorage.setItem('gs_me', JSON.stringify(v)); else localStorage.removeItem('gs_me'); } catch (_) {} },
};

class ApiError extends Error {
  constructor(status, code, message) { super(message); this.status = status; this.code = code; }
}

function sessionLost() {
  store.token = null;
  store.me = null;
  sessionStorage.setItem('gs_lost', '1');
  location.hash = '#/login';
}

async function api(path, opts = {}) {
  const { method = 'GET', body, form, signal, raw } = opts;
  const headers = {};
  const token = store.token;
  if (token) headers.Authorization = 'Bearer ' + token;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  let r;
  try {
    r = await fetch(path, { method, headers, body: payload, signal, cache: 'no-store' });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiError(0, 'network', 'Нет связи с сервером. Проверь интернет.');
  }
  if (raw && r.ok) return r.blob();
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (_) { data = null; }
  if (!r.ok) {
    const d = data && data.detail && typeof data.detail === 'object' ? data.detail : null;
    if (r.status === 401 && token) sessionLost();
    let msg = d && d.message;
    if (!msg) msg = r.status === 429 ? 'Слишком часто. Подожди немного.'
      : r.status >= 500 ? 'Сервер временно недоступен. Попробуй ещё раз.'
        : (r.status === 404 || r.status === 405) ? 'Сервер ещё не обновлён до этой версии.' : 'Ошибка ' + r.status;
    throw new ApiError(r.status, (d && d.code) || 'http_' + r.status, msg);
  }
  return data;
}

// images need the session header, so they are fetched and shown as blob: URLs
const imgCache = new Map();
function authImage(path) {
  if (imgCache.has(path)) return imgCache.get(path);
  const p = fetch(path, { headers: { Authorization: 'Bearer ' + store.token } }).then(async (r) => {
    if (!r.ok) throw new Error('image ' + r.status);
    return URL.createObjectURL(await r.blob());
  });
  imgCache.set(path, p);
  p.catch(() => imgCache.delete(path));
  return p;
}
function authImg(path, alt) {
  const el = h('img', { alt: alt || '' });
  if (path) authImage(path).then((u) => { el.src = u; el.classList.add('loaded'); }).catch(() => {});
  return el;
}
function avatar(name, path, size = 40, extra) {
  const el = h('div', { class: 'avatar', style: `width:${size}px;height:${size}px;font-size:${Math.round(size * 0.42)}px;background:${colorFor(name)}` },
    ((name || '?').trim()[0] || '?').toUpperCase());
  if (path) el.append(authImg(path, name));
  if (extra) el.append(extra);
  return el;
}
const userAvatarPath = (u) => (u && u.avatar_image_id ? `/v1/users/${u.id}/avatar?v=${u.avatar_image_id}` : null);
const personaAvatarPath = (p) => (p && p.avatar_image_id ? `/v1/personas/${p.id}/avatar?v=${p.avatar_image_id}` : null);

// shrink photos before upload (and turn iPhone HEIC into JPEG)
async function prepareImage(file, maxSide = 1280) {
  try {
    const bmp = await createImageBitmap(file);
    const k = Math.min(1, maxSide / Math.max(bmp.width, bmp.height));
    const c = document.createElement('canvas');
    c.width = Math.round(bmp.width * k);
    c.height = Math.round(bmp.height * k);
    c.getContext('2d').drawImage(bmp, 0, 0, c.width, c.height);
    return await new Promise((res) => c.toBlob((b) => res(b || file), 'image/jpeg', 0.86));
  } catch (_) {
    return file;
  }
}
async function uploadImage(file, maxSide) {
  const fd = new FormData();
  fd.append('file', await prepareImage(file, maxSide), 'image.jpg');
  return api('/v1/images', { method: 'POST', form: fd });
}
function pickFile() {
  return new Promise((resolve) => {
    const inp = h('input', { type: 'file', accept: 'image/*', style: 'display:none' });
    inp.addEventListener('change', () => { resolve(inp.files && inp.files[0]); inp.remove(); });
    document.body.append(inp);
    inp.click();
  });
}

function errorBox(msg, retry) {
  return h('div', { class: 'card center', style: 'margin-top:20px' },
    h('div', { class: 'muted' }, msg),
    retry ? h('button', { class: 'link accent', onclick: retry }, 'Повторить') : null);
}

const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
function installHint() {
  if (!isIOS || isStandalone()) return null;
  return h('div', { class: 'install glass', id: 'install-hint' },
    h('b', null, 'GramSoul как приложение на iPhone'), h('br'),
    'В Safari нажми «Поделиться» ', h('b', null, '⬆︎'), ' → «На экран „Домой“». Откроется на весь экран, со своей иконкой.');
}

// ------------------------------------------------------------------ inbox badges
const badges = { chats: 0, friends: 0 };
let inboxStarted = false;
async function refreshBadges() {
  try {
    const f = await api('/v1/friends');
    badges.friends = (f.incoming || []).length;
    badges.chats = (f.invites || []).length;
    document.querySelectorAll('[data-badge]').forEach((b) => {
      const n = badges[b.dataset.badge] || 0;
      b.textContent = n;
      b.classList.toggle('hidden', n === 0);
    });
  } catch (_) {}
}
async function inboxLoop() {
  if (inboxStarted) return;
  inboxStarted = true;
  let v = -1;
  while (store.token) {
    try {
      const r = await api(`/v1/inbox/wait?since=${v}&wait=${v < 0 ? 0 : 25}`);
      if (r.version !== v) { v = r.version; refreshBadges(); }
    } catch (e) {
      await sleep(5000);
    }
  }
  inboxStarted = false;
}

// ------------------------------------------------------------------ layout
const TABS = [['characters', 'Персонажи', 'face'], ['chats', 'Чаты', 'chat'], ['friends', 'Друзья', 'people'], ['profile', 'Профиль', 'user']];
function tabPage(root, current, title, subtitle) {
  const page = h('div', { class: 'page' });
  if (title) page.append(h('div', { class: 'large-title' }, title));
  if (subtitle) page.append(h('div', { class: 'subtitle' }, subtitle));
  const bar = h('nav', { class: 'tabbar glass' }, TABS.map(([id, label, ic]) => {
    const n = id === 'chats' ? badges.chats : id === 'friends' ? badges.friends : 0;
    return h('button', { class: 'tab' + (id === current ? ' on' : ''), id: 'tab-' + id, onclick: () => { location.hash = '#/' + id; } },
      icon(ic), label,
      (id === 'chats' || id === 'friends') ? h('span', { class: 'badge' + (n ? '' : ' hidden'), 'data-badge': id }, n) : null);
  }));
  root.append(page, bar);
  return page;
}
function subPage(root, title, backHash, actions) {
  const page = h('div', { class: 'page', style: 'padding-bottom:calc(var(--safe-b) + 32px)' });
  const bar = h('div', { class: 'topbar' },
    h('button', { class: 'icon-btn', id: 'back', 'aria-label': 'Назад', onclick: () => { if (history.length > 1) history.back(); else location.hash = backHash; } }, icon('back')),
    h('div', { class: 'grow title ellipsis' }, title || ''),
    ...(actions || []));
  page.append(bar);
  root.append(page);
  return page;
}

// ------------------------------------------------------------------ login
const NICK_RE = /^[A-Za-z0-9_.А-яЁё]+$/;
function nickError(n) {
  n = n.trim();
  if (!n) return null;
  if (n.length < 3) return 'Ник должен быть не короче 3 символов.';
  if (n.length > 20) return 'Ник должен быть не длиннее 20 символов.';
  if (n.includes(' ')) return 'В нике не должно быть пробелов. Можно «_» и «.».';
  if (!NICK_RE.test(n)) return 'Можно только буквы (латиница или кириллица), цифры, «_» и «.».';
  if (/^[_.]+$/.test(n)) return 'Ник не может состоять только из «_» и «.».';
  return null;
}

function afterLogin(res) {
  store.token = res.token;
  store.me = res.user;
  location.hash = res.user && res.user.has_password === false ? '#/set-password' : '#/characters';
}

function screenLogin(root) {
  if (store.token) { location.hash = '#/characters'; return; }
  let mode = 'login'; // login | register | code
  const nick = h('input', { class: 'field', id: 'nick', placeholder: 'Ник', autocapitalize: 'off', autocomplete: 'username', spellcheck: 'false', maxlength: 24 });
  const pw = h('input', { class: 'field', id: 'password', type: 'password', placeholder: 'Пароль', autocomplete: 'current-password', maxlength: 128 });
  const pw2 = h('input', { class: 'field hidden', id: 'password2', type: 'password', placeholder: 'Пароль ещё раз', autocomplete: 'new-password', maxlength: 128 });
  const code = h('input', { class: 'field hidden', id: 'code', placeholder: 'Код переноса, например ABCD-EFGH', autocapitalize: 'characters', autocomplete: 'off', maxlength: 12 });
  const hint = h('div', { class: 'hint' });
  const err = h('div', { class: 'error', id: 'login-error' });
  const btn = h('button', { class: 'btn primary wide', id: 'login', type: 'submit', disabled: true }, 'Войти');
  const seg = h('div', { class: 'seg' });
  const codeLink = h('button', { class: 'link', type: 'button', id: 'transfer-toggle' });
  const lost = sessionStorage.getItem('gs_lost');
  sessionStorage.removeItem('gs_lost');
  const update = () => {
    const e = nickError(nick.value);
    pw.classList.toggle('hidden', mode === 'code');
    pw2.classList.toggle('hidden', mode !== 'register');
    code.classList.toggle('hidden', mode !== 'code');
    pw.setAttribute('autocomplete', mode === 'register' ? 'new-password' : 'current-password');
    btn.textContent = mode === 'register' ? 'Создать аккаунт' : 'Войти';
    codeLink.textContent = mode === 'code' ? '← Вход по паролю' : 'Вход по коду переноса';
    seg.classList.toggle('hidden', mode === 'code');
    hint.textContent = e || (mode === 'register' ? 'Ник: 3–20 символов, буквы, цифры, «_» и «.». Пароль — не короче 8 символов.'
      : mode === 'code' ? 'Ник и код из профиля на другом устройстве (код действует 10 минут).' : '');
    hint.style.color = e ? 'var(--error)' : '';
    let ok = nick.value.trim() && !e;
    if (mode === 'login') ok = ok && pw.value.length > 0;
    if (mode === 'register') ok = ok && pw.value.length >= 8 && pw2.value.length > 0;
    if (mode === 'code') ok = ok && code.value.replace(/[^A-Za-z0-9]/g, '').length >= 8;
    btn.disabled = !ok;
  };
  const drawSeg = () => seg.replaceChildren(...[['login', 'Вход'], ['register', 'Регистрация']].map(([m, l]) =>
    h('button', { type: 'button', id: 'mode-' + m, class: mode === m ? 'on' : '', onclick: () => { mode = m; err.textContent = ''; drawSeg(); update(); } }, l)));
  drawSeg();
  [nick, pw, pw2, code].forEach((x) => x.addEventListener('input', () => { err.textContent = ''; update(); }));
  codeLink.addEventListener('click', () => { mode = mode === 'code' ? 'login' : 'code'; err.textContent = ''; drawSeg(); update(); });
  const form = h('form', null, seg, nick, pw, pw2, code, hint, err, btn, codeLink);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (btn.disabled) return;
    if (mode === 'register' && pw.value !== pw2.value) { err.textContent = 'Пароли не совпадают.'; return; }
    btn.disabled = true;
    err.textContent = '';
    try {
      const n = nick.value.trim();
      const res = mode === 'code' ? await api('/v1/login/transfer', { method: 'POST', body: { nick: n, code: code.value.trim() } })
        : mode === 'register' ? await api('/v1/register', { method: 'POST', body: { nick: n, password: pw.value } })
          : await api('/v1/login', { method: 'POST', body: { nick: n, password: pw.value } });
      afterLogin(res);
    } catch (ex) {
      err.textContent = ex.code === 'nick_taken' ? 'Ник занят. Если это твой ник — открой «Вход».' : ex.message;
    } finally {
      update();
    }
  });
  root.append(h('div', { class: 'login' },
    h('img', { class: 'logo', src: 'logo.png', alt: 'GramSoul' }),
    h('div', { class: 'muted center', style: 'margin-top:2px' }, 'Ролевые чаты с ИИ-персонажами вместе с друзьями'),
    lost ? h('div', { class: 'card', style: 'margin-top:20px;font-size:14px' }, 'Сессия на этом устройстве закончилась. Войди по нику и паролю.') : null,
    form,
    installHint(),
    h('div', { class: 'faint small', style: 'margin-top:16px' }, 'GramSoul Web ' + WEB_VERSION)));
  update();
}

// accounts made before passwords existed must choose one before going on
function screenSetPassword(root) {
  const pw = h('input', { class: 'field', id: 'new-password', type: 'password', placeholder: 'Новый пароль', autocomplete: 'new-password', maxlength: 128 });
  const pw2 = h('input', { class: 'field', id: 'new-password2', type: 'password', placeholder: 'Ещё раз', autocomplete: 'new-password', maxlength: 128 });
  const err = h('div', { class: 'error' });
  const btn = h('button', { class: 'btn primary wide', id: 'set-password', type: 'submit', disabled: true }, 'Сохранить пароль');
  const upd = () => { btn.disabled = pw.value.length < 8 || !pw2.value; };
  [pw, pw2].forEach((x) => x.addEventListener('input', () => { err.textContent = ''; upd(); }));
  const form = h('form', null, pw, pw2, h('div', { class: 'hint' }, 'Не короче 6 символов.'), err, btn);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (pw.value !== pw2.value) { err.textContent = 'Пароли не совпадают.'; return; }
    btn.disabled = true;
    try {
      const r = await api('/v1/me/password', { method: 'POST', body: { password: pw.value } });
      store.me = r.user;
      location.hash = '#/characters';
    } catch (ex) { err.textContent = ex.message; upd(); }
  });
  root.append(h('div', { class: 'login' },
    h('img', { class: 'logo small', src: 'logo.png', alt: 'GramSoul' }),
    h('div', { style: 'font-size:24px;font-weight:700;margin-top:6px' }, 'Придумай пароль'),
    h('div', { class: 'muted center', style: 'margin-top:8px;line-height:1.5' },
      'Теперь в GramSoul вход по нику и паролю — так ты зайдёшь в свой аккаунт с любого устройства. ',
      'Ник: ', h('b', null, (store.me && store.me.nick) || '')),
    form));
}

// ------------------------------------------------------------------ characters
function personaCard(p) {
  const name = p.name || 'Без имени';
  const card = h('button', { class: 'pcard', 'data-name': name, style: `background:${gradFor(name)}`, onclick: () => { location.hash = '#/persona/' + p.id; } });
  const path = personaAvatarPath(p);
  if (path) card.append(authImg(path, name));
  else card.append(h('div', { class: 'pcard-letter' }, name[0].toUpperCase()));
  card.append(h('div', { class: 'pcard-shade' }),
    h('div', { class: 'pcard-text' }, h('div', { class: 'pcard-name ellipsis' }, name), p.description ? h('div', { class: 'pcard-desc' }, p.description) : null));
  if (p.status === 'draft') card.append(h('span', { class: 'pill pcard-pill' }, 'Черновик'));
  else if (p.mine && p.visibility === 'private') card.append(h('span', { class: 'pill lilac pcard-pill' }, 'Личный'));
  return card;
}

// ------------------------------------------------------------------ voice-over
// one <audio> for the whole app; it is «unlocked» inside the tap so iPhone lets it play after the download
const PLAYER = { el: null, key: null };
const SILENT_MP3 = 'data:audio/mpeg;base64,' + btoa(String.fromCharCode(0xFF, 0xFB, 0x90, 0x64) + '\0'.repeat(413));
function voiceState() { document.dispatchEvent(new Event('voice-state')); }
function audioEl() {
  if (!PLAYER.el) {
    PLAYER.el = new Audio();
    PLAYER.el.addEventListener('ended', () => { PLAYER.key = null; voiceState(); });
  }
  return PLAYER.el;
}
function stopVoice() { if (PLAYER.el) PLAYER.el.pause(); PLAYER.key = null; voiceState(); }
async function playVoice(key, path, body) {
  const a = audioEl();
  if (PLAYER.key === key || PLAYER.key === 'loading:' + key) { stopVoice(); return; }
  try { a.src = SILENT_MP3; a.play().catch(() => {}); } catch (_) {}
  PLAYER.key = 'loading:' + key;
  voiceState();
  try {
    const blob = await api(path, { method: 'POST', body, raw: true });
    if (PLAYER.key !== 'loading:' + key) return;  // stopped meanwhile
    a.src = URL.createObjectURL(blob);
    PLAYER.key = key;
    voiceState();
    await a.play();
  } catch (e) {
    if (e && e.name === 'NotAllowedError') toast('Нажми ещё раз, чтобы послушать');
    else if (e && e.name !== 'AbortError') toast(e.message || 'Не удалось воспроизвести озвучку');
    PLAYER.key = null;
    voiceState();
  }
}
let VOICES = null;
async function voiceOptions() {
  if (!VOICES) {
    try { VOICES = await api('/v1/voices'); } catch (_) { VOICES = { available: false, voices: [], manners: [], timbres: [] }; }
  }
  return VOICES;
}
/** Voice of a character for the voice-over: a voice, a manner of speaking and a timbre, and a sample. */
function voiceFields(init, idPrefix) {
  const sel = h('select', { class: 'field', id: idPrefix + '-voice' }, h('option', { value: '' }, 'Авто'));
  const manner = h('input', { class: 'field', id: idPrefix + '-manner', maxlength: 200, placeholder: 'например: дерзко и насмешливо', value: init.voice_manner || '' });
  const timbre = h('input', { class: 'field', id: idPrefix + '-timbre', maxlength: 200, placeholder: 'например: низкий, с хрипотцой', value: init.voice_timbre || '' });
  const mChips = h('div', { class: 'chips', style: 'margin-top:6px' });
  const tChips = h('div', { class: 'chips', style: 'margin-top:6px' });
  const note = h('div', { class: 'hint' });
  const key = 'preview-' + idPrefix;
  const play = h('button', { class: 'btn ghost small', id: idPrefix + '-preview', type: 'button', style: 'margin-top:10px' }, icon('play', 18), 'Прослушать голос');
  play.addEventListener('click', () => playVoice(key, '/v1/voice/preview',
    { voice: sel.value, manner: manner.value.trim(), timbre: timbre.value.trim() }));
  const onState = () => {
    if (!document.body.contains(play)) { document.removeEventListener('voice-state', onState); return; }
    play.lastChild.textContent = PLAYER.key === key ? 'Стоп' : PLAYER.key === 'loading:' + key ? 'Загружаю…' : 'Прослушать голос';
  };
  document.addEventListener('voice-state', onState);
  voiceOptions().then((o) => {
    for (const v of o.voices) sel.append(h('option', { value: v.id }, v.label));
    sel.value = init.voice || '';
    const chipsFor = (box, list, input) => box.replaceChildren(...list.map((t) => h('button', { type: 'button', class: 'chip', onclick: () => { input.value = t; } }, t)));
    chipsFor(mChips, o.manners, manner);
    chipsFor(tChips, o.timbres, timbre);
    if (!o.available) { note.textContent = 'Озвучка пока не настроена на сервере.'; play.disabled = true; }
  });
  const el = h('div', { class: 'card voice-card', style: 'margin-top:14px' },
    h('div', { style: 'font-weight:600' }, 'Голос для озвучки'),
    h('label', { class: 'lbl' }, 'Голос'), sel,
    h('label', { class: 'lbl' }, 'Манера речи'), manner, mChips,
    h('label', { class: 'lbl' }, 'Тембр'), timbre, tChips, note, play);
  return { el, value: () => ({ voice: sel.value, voice_manner: manner.value.trim(), voice_timbre: timbre.value.trim() }) };
}

function createSheet() {
  const s = sheet('Что создать?',
    h('button', { class: 'list-item', id: 'create-persona-item', onclick: () => { s.close(); location.hash = '#/persona-edit'; } }, icon('face'),
      h('div', { class: 'grow' }, h('div', { class: 't' }, 'Персонажа'), h('div', { class: 's' }, 'Один герой для личного чата'))),
    h('button', { class: 'list-item', id: 'create-story-item', onclick: () => { s.close(); location.hash = '#/story-edit'; } }, icon('book'),
      h('div', { class: 'grow' }, h('div', { class: 't' }, 'Историю'), h('div', { class: 's' }, 'Мир, несколько персонажей, место и первая сцена — можно играть с другом'))),
    h('button', { class: 'list-item', id: 'create-quick-item', onclick: () => { s.close(); quickStorySheet(); } }, icon('forward'),
      h('div', { class: 'grow' }, h('div', { class: 't' }, 'Быструю историю'), h('div', { class: 's' }, 'Один персонаж и первая реплика — за минуту'))));
}

/** The quick story: a character, how they talk and the first line; the rest is filled in by the server. */
function quickStorySheet() {
  const name = h('input', { class: 'field', id: 'q-name', maxlength: 40, placeholder: 'Имя персонажа' });
  const pers = autoGrow(h('textarea', { class: 'field', id: 'q-pers', rows: 2, maxlength: 1500, placeholder: 'Характер: тихая, упрямая, боится темноты…' }), 140);
  const speech = h('input', { class: 'field', id: 'q-speech', maxlength: 1000, placeholder: 'Манера речи: коротко, полушёпотом…' });
  const line = autoGrow(h('textarea', { class: 'field', id: 'q-line', rows: 2, maxlength: 1500, placeholder: '*Он поднимает взгляд* — Ты всё-таки пришёл.' }), 140);
  const err = h('div', { class: 'error' });
  const go = h('button', { class: 'btn primary wide', id: 'q-create', style: 'margin-top:12px' }, 'Создать и открыть');
  go.addEventListener('click', async () => {
    if (!name.value.trim()) { err.textContent = 'Напиши имя персонажа.'; return; }
    go.disabled = true;
    try {
      const r = await api('/v1/stories/quick', { method: 'POST', body: { name: name.value.trim(), personality: pers.value.trim(), speech_style: speech.value.trim(), start_line: line.value.trim() } });
      sh.close();
      location.hash = '#/story/' + r.story.id;
    } catch (e) { err.textContent = e.message; go.disabled = false; }
  });
  const sh = sheet('Быстрая история', name, h('label', { class: 'lbl' }, 'Характер'), pers, h('label', { class: 'lbl' }, 'Манера речи'), speech,
    h('label', { class: 'lbl' }, 'Первая реплика'), line, err, go);
  name.focus();
}

function storyCover(st) {
  const iid = st.cover_image_id || st.avatar_image_id;
  return iid ? `/v1/stories/${st.id}/images/${iid}` : null;
}
function storyItem(st) {
  return h('button', { class: 'list-item story-item', 'data-story': st.title, onclick: () => { location.hash = '#/story/' + st.id; } },
    avatar(st.title, storyCover(st), 52),
    h('div', { class: 'grow', style: 'min-width:0' },
      h('div', { class: 't ellipsis' }, st.title),
      h('div', { class: 's ellipsis' }, st.mine ? (st.visibility === 'public' ? 'Моя · публичная' : 'Моя · личная') : 'Автор: ' + ((st.author && st.author.nick) || '—')),
      st.description ? h('div', { class: 's', style: 'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden' }, st.description) : null));
}

function screenCharacters(root) {
  const page = tabPage(root, 'characters', 'Персонажи', (store.me && store.me.nick) || '');
  let scope = sessionStorage.getItem('gs_scope') || 'all';
  let q = '';
  let seq = 0;
  let timer;
  const grid = h('div', { class: 'grid', id: 'personas' });
  const search = h('input', { class: 'field', id: 'persona-search', placeholder: 'Имя или #тег', type: 'search', autocomplete: 'off' });
  const chips = h('div', { class: 'chips', style: 'margin-top:10px' });
  const drawChips = () => chips.replaceChildren(...[['all', 'Все'], ['mine', 'Мои'], ['drafts', 'Черновики']].map(([id, l]) =>
    h('button', { class: 'chip' + (scope === id ? ' on' : ''), onclick: () => { scope = id; sessionStorage.setItem('gs_scope', id); drawChips(); load(); } }, l)));
  let load = async function () {
    const my = ++seq;
    try {
      const r = await api(`/v1/personas?q=${encodeURIComponent(q)}&scope=${scope}`);
      if (my !== seq) return;
      grid.replaceChildren(...r.personas.map(personaCard));
      if (!r.personas.length) grid.append(h('div', { class: 'muted', id: 'personas-empty' },
        scope === 'drafts' ? 'Черновиков нет.' : q ? 'Ничего не нашли.'
          : scope === 'mine' ? 'У тебя пока нет персонажей — создай первого.'
            : 'Пока нет персонажей. Создай своего — или загляни позже, когда другие опубликуют.'));
    } catch (e) {
      if (my === seq) grid.replaceChildren(errorBox(e.message, load));
    }
  };
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { q = search.value.trim(); load(); }, 300); });
  drawChips();
  // personas | stories
  let kind = sessionStorage.getItem('gs_kind') || 'personas';
  const kindSeg = h('div', { class: 'seg', style: 'margin-bottom:12px' });
  const storyBox = h('div', { id: 'stories' });
  const drawKind = () => {
    kindSeg.replaceChildren(...[['personas', 'Персонажи'], ['stories', 'Истории']].map(([k, l]) =>
      h('button', { type: 'button', id: 'kind-' + k, class: kind === k ? 'on' : '', onclick: () => { kind = k; sessionStorage.setItem('gs_kind', k); drawKind(); load(); } }, l)));
    search.placeholder = kind === 'stories' ? 'Название истории' : 'Имя или #тег';
    chips.classList.toggle('hidden', kind === 'stories');
    grid.classList.toggle('hidden', kind === 'stories');
    storyBox.classList.toggle('hidden', kind !== 'stories');
  };
  const personasLoad = load;
  async function loadStories() {
    const my = ++seq;
    try {
      const r = await api(`/v1/stories?scope=all&q=${encodeURIComponent(q)}`);
      if (my !== seq) return;
      fill(storyBox, r.stories.length ? r.stories.map(storyItem)
        : h('div', { class: 'muted' }, q ? 'Ничего не нашли.' : 'Историй пока нет — создай свою или дождись, пока друзья опубликуют.'));
    } catch (e) { if (my === seq) fill(storyBox, errorBox(e.message, loadStories)); }
  }
  load = () => (kind === 'stories' ? loadStories() : personasLoad());
  drawKind();
  page.append(kindSeg, search, chips,
    h('button', { class: 'btn primary wide', id: 'create-persona', style: 'margin-top:12px', onclick: createSheet }, icon('plus', 20), 'Создать'),
    grid, storyBox);
  load();
}

async function screenPersona(root, id) {
  const page = subPage(root, '', '#/characters');
  let p;
  try {
    p = (await api('/v1/personas/' + id)).persona;
  } catch (e) {
    page.append(errorBox(e.message, () => render()));
    return;
  }
  const name = p.name || 'Без имени';
  $('.title', page).textContent = name;
  if (p.mine) {
    $('.topbar', page).append(
      h('button', { class: 'icon-btn', id: 'persona-edit', 'aria-label': 'Изменить', onclick: () => { location.hash = '#/persona-edit/' + id; } }, icon('edit')),
      h('button', { class: 'icon-btn', id: 'persona-delete', 'aria-label': 'Удалить', style: 'color:var(--muted)', onclick: async () => {
        if (!(await confirmSheet('Удалить персонажа?', 'Карточка исчезнет у всех. Это нельзя отменить.', 'Удалить', true))) return;
        try { await api('/v1/personas/' + id, { method: 'DELETE' }); location.hash = '#/characters'; } catch (e) { toast(e.message); }
      } }, icon('close')));
  }
  const portrait = h('div', { class: 'portrait', style: `background:${gradFor(name)}` }, name[0].toUpperCase());
  const ap = personaAvatarPath(p);
  if (ap) portrait.append(authImg(ap, name));
  const startBtn = h('button', { class: 'btn primary grow', id: 'persona-chat-new', onclick: async () => {
    startBtn.disabled = true;
    try { const r = await api(`/v1/personas/${id}/chats`, { method: 'POST' }); location.hash = '#/chat/' + r.room.id; } catch (e) { toast(e.message); startBtn.disabled = false; }
  } }, p.chats && p.chats.length ? 'Новый чат' : 'Начать чат');
  const actions = h('div', { class: 'row' }, startBtn,
    p.chats && p.chats.length ? h('button', { class: 'btn ghost grow', id: 'persona-chat-continue', onclick: () => { location.hash = '#/chat/' + p.chats[0].id; } }, 'Продолжить') : null);
  const tags = h('div', { class: 'tags' },
    p.status === 'draft' ? h('span', { class: 'pill' }, 'Черновик') : null,
    p.mine ? h('span', { class: 'pill lilac' }, p.visibility === 'public' ? 'Публичный' : 'Личный') : null,
    h('span', { class: 'pill grey' }, '18+'),
    (p.tags || []).map((t) => h('span', { class: 'pill' }, '#' + t)));
  // publish or hide at any time — also when chats with this character already exist
  const pubBtn = p.mine ? h('button', { class: 'btn ghost wide', id: 'persona-publish-toggle', style: 'margin-top:10px' },
    icon('globe', 20), p.visibility === 'public' && p.status === 'published' ? 'Сделать личным' : 'Опубликовать для всех') : null;
  if (pubBtn) pubBtn.addEventListener('click', async () => {
    const pub = p.visibility === 'public' && p.status === 'published';
    try {
      p = (await api(`/v1/personas/${id}/visibility`, { method: 'PATCH', body: { visibility: pub ? 'private' : 'public' } })).persona;
      toast(pub ? 'Персонаж снова личный' : 'Персонаж опубликован');
      render();
    } catch (e) { toast(e.message); }
  });
  put(page, portrait,
    h('div', { class: 'center', style: 'font-size:24px;font-weight:700' }, name),
    h('div', { class: 'center muted' }, p.is_demo ? 'Персонаж GramSoul' : p.mine ? 'Твой персонаж' : 'Автор: ' + ((p.author && p.author.nick) || '—')),
    tags, actions, pubBtn,
    p.description ? [h('div', { class: 'section' }, 'Описание'), h('div', { style: 'white-space:pre-wrap' }, p.description)] : null,
    p.first_message ? [h('div', { class: 'section' }, 'Первое сообщение'), h('div', { class: 'bubble char', style: 'user-select:text' }, richText(p.first_message, true))] : null,
    p.mine && p.personality ? [h('div', { class: 'section' }, 'Характер · видно только тебе'), h('div', { class: 'muted', style: 'white-space:pre-wrap' }, p.personality)] : null,
    p.mine && p.backstory ? [h('div', { class: 'section' }, 'Предыстория · видно только тебе'), h('div', { class: 'muted', style: 'white-space:pre-wrap' }, p.backstory)] : null);
}

function counted(label, el, max) {
  const c = h('span', { class: 'counter' }, `${el.value.length}/${max}`);
  el.setAttribute('maxlength', max);
  el.addEventListener('input', () => { c.textContent = `${el.value.length}/${max}`; });
  return [h('label', { class: 'lbl' }, label, c), el];
}
function autoGrow(t, max = 320) {
  const fit = () => { t.style.height = 'auto'; t.style.height = Math.min(max, t.scrollHeight + 2) + 'px'; };
  t.addEventListener('input', fit);
  setTimeout(fit, 0);
  return t;
}

async function screenPersonaEdit(root, id) {
  const page = subPage(root, id ? 'Редактирование' : 'Новый персонаж', '#/characters');
  let p = { name: '', first_message: '', description: '', backstory: '', personality: '', tags: [], visibility: 'private', avatar_image_id: null };
  if (id) {
    try { p = (await api('/v1/personas/' + id)).persona; } catch (e) { page.append(errorBox(e.message, () => render())); return; }
  }
  let avatarId = p.avatar_image_id;
  let visibility = p.visibility || 'private';
  const name = h('input', { class: 'field', id: 'p-name', value: p.name || '' });
  const first = autoGrow(h('textarea', { class: 'field', id: 'p-first', rows: 4, placeholder: 'С него ИИ начинает каждый чат. *Действия* — в звёздочках, реплика — с тире.' }));
  first.value = p.first_message || '';
  const desc = autoGrow(h('textarea', { class: 'field', id: 'p-desc', rows: 3, placeholder: 'Кратко для карточки: кто это, внешность, чем интересен' }));
  desc.value = p.description || '';
  const back = autoGrow(h('textarea', { class: 'field', id: 'p-back', rows: 3, placeholder: 'История, черты, контекст' }));
  back.value = p.backstory || '';
  const pers = autoGrow(h('textarea', { class: 'field', id: 'p-pers', rows: 3, placeholder: 'Поведение, привычки, манера речи' }));
  pers.value = p.personality || '';
  const tags = h('input', { class: 'field', id: 'p-tags', placeholder: 'мистика, море, детектив', value: (p.tags || []).join(', ') });

  const tile = h('button', { class: 'avatar-tile', id: 'avatar-tile', type: 'button', style: `background:${gradFor(p.name || '?')}` });
  const drawTile = () => {
    tile.replaceChildren(avatarId ? authImg('/v1/images/' + avatarId, 'Аватар') : h('span', null, 'AI-аватар'));
    if (avatarId && id && avatarId === p.avatar_image_id) { // the stored avatar of an existing character
      tile.replaceChildren(authImg(personaAvatarPath(p), 'Аватар'));
    }
  };
  drawTile();
  tile.addEventListener('click', () => avatarSheet(name.value, desc.value, (iid) => { avatarId = iid; drawTile(); }));

  const seg = h('div', { class: 'seg' });
  const drawSeg = () => seg.replaceChildren(...[['public', 'Публичный'], ['private', 'Личный']].map(([v, l]) =>
    h('button', { type: 'button', id: 'vis-' + v, class: visibility === v ? 'on' : '', onclick: () => { visibility = v; drawSeg(); } }, l)));
  drawSeg();

  const idea = h('textarea', { class: 'field', id: 'fill-idea', rows: 2, placeholder: 'Например: травница-оборотень на перекрёстке дорог', maxlength: 1000 });
  const fillBtn = h('button', { class: 'btn ghost wide', id: 'fill', type: 'button', style: 'margin-top:8px' }, icon('magic', 20), 'Заполнить поля');
  fillBtn.addEventListener('click', async () => {
    if (!idea.value.trim()) return;
    fillBtn.disabled = true;
    fillBtn.lastChild.textContent = 'Придумываю…';
    try {
      const f = (await api('/v1/personas/fill', { method: 'POST', body: { idea: idea.value.trim() } })).persona;
      if (f.name) name.value = f.name;
      desc.value = f.description; pers.value = f.personality; back.value = f.backstory; first.value = f.first_message;
      tags.value = (f.tags || []).join(', ');
      [name, desc, pers, back, first].forEach((x) => x.dispatchEvent(new Event('input')));
    } catch (e) { toast(e.message); }
    fillBtn.disabled = false;
    fillBtn.lastChild.textContent = 'Заполнить поля';
  });

  const voice = voiceFields(p, 'p');
  const err = h('div', { class: 'error', id: 'p-error' });
  async function save(publish) {
    err.textContent = '';
    if (publish && (!name.value.trim() || !first.value.trim())) { err.textContent = 'Чтобы опубликовать, заполни имя и первое сообщение.'; return; }
    const body = {
      name: name.value.trim(), first_message: first.value.trim(), description: desc.value.trim(), backstory: back.value.trim(),
      personality: pers.value.trim(), tags: tags.value.split(/[,;]/).map((s) => s.trim()).filter(Boolean),
      visibility, status: publish ? 'published' : 'draft', avatar_image_id: avatarId, ...voice.value(),
    };
    try {
      const r = id ? await api('/v1/personas/' + id, { method: 'PUT', body }) : await api('/v1/personas', { method: 'POST', body });
      location.replace('#/persona/' + r.persona.id);
    } catch (e) { err.textContent = e.message; }
  }

  put(page,
    h('div', { class: 'card' }, h('div', { style: 'color:var(--accent);font-weight:600' }, 'Придумать с ИИ'), idea, fillBtn),
    h('div', { class: 'row', style: 'margin-top:16px' }, tile,
      h('div', { class: 'grow' }, h('div', { style: 'font-weight:600' }, 'Портрет 2:3'),
        h('div', { class: 'muted small' }, 'Загрузи картинку или создай её с ИИ в одном из пяти стилей.'))),
    counted('Имя персонажа *', name, 60),
    counted('Первое сообщение *', first, 5000),
    counted('Описание персонажа', desc, 10000),
    h('label', { class: 'lbl' }, 'Видимость'), seg,
    h('div', { class: 'hint' }, 'Публичного персонажа увидят все игроки GramSoul, личного — только ты.'),
    h('details', { style: 'margin-top:14px' }, h('summary', { style: 'font-weight:600;padding:6px 4px' }, 'Дополнительные настройки'),
      counted('Предыстория', back, 2000), counted('Характер', pers, 2000),
      h('label', { class: 'lbl' }, 'Теги через запятую'), tags,
      h('div', { class: 'hint' }, 'Предыстория и характер видны только тебе — их получает ИИ.')),
    voice.el,
    h('div', { class: 'hint', style: 'margin-top:14px' }, 'Все персонажи по умолчанию 18+.'),
    err,
    h('div', { class: 'row', style: 'margin-top:14px' },
      h('button', { class: 'btn ghost grow', id: 'save-draft', onclick: () => save(false) }, 'Черновик'),
      h('button', { class: 'btn primary grow', id: 'publish', onclick: () => save(true) }, 'Опубликовать')));
}

const STYLES = [['aesthetic', 'Эстетика'], ['anime', 'Аниме'], ['realism', 'Реализм'], ['painted', 'Нарисованный'], ['manhwa', 'Манхва'], ['sketch', 'Ч/б рисунок']];
const STYLE_PREVIEWS = new Set(['anime', 'realism', 'painted', 'manhwa', 'sketch']);
function styleTile(sid, label, on, idPrefix, onPick) {
  const pic = STYLE_PREVIEWS.has(sid) ? h('img', { src: 'styles/' + sid + '.jpg', alt: label }) : h('div', { class: 'ph ' + sid, role: 'img', 'aria-label': label });
  return h('button', { class: 'style' + (on ? ' on' : ''), id: idPrefix + sid, type: 'button', onclick: onPick }, pic, label);
}
function avatarSheet(name, description, onUse) {
  let style = 'anime';
  const body = h('div');
  const s = sheet('AI-аватар', body);
  s.el.id = 'avatar-sheet';
  const showMain = () => {
    const desc = autoGrow(h('textarea', { class: 'field', id: 'avatar-desc', rows: 3, placeholder: 'Волосы, глаза, одежда… или: Лелуш Ви Британия из аниме «Код Гиасс». Пусто — по имени.' }), 160);
    desc.value = (description || '').slice(0, 400);
    const grid = h('div', { class: 'styles' });
    const draw = () => grid.replaceChildren(...STYLES.map(([sid, label]) =>
      styleTile(sid, label, sid === style, 'style-', () => { style = sid; draw(); })));
    draw();
    const err = h('div', { class: 'error' });
    const gen = h('button', { class: 'btn primary wide', id: 'avatar-generate', style: 'margin-top:14px' }, 'Сгенерировать');
    gen.addEventListener('click', async () => {
      // the description is optional: the name of a known character is enough
      if ((desc.value.trim() || (name || '').trim()).length < 2) { err.textContent = 'Напиши имя персонажа или опиши внешность.'; return; }
      gen.disabled = true;
      gen.textContent = 'Рисую… 10–30 с';
      try {
        const r = await api('/v1/avatars/generate', { method: 'POST', body: { name: name || '', description: desc.value.trim(), style } });
        showResult(r.image_id, desc.value);
      } catch (e) {
        err.textContent = e.message;
        gen.disabled = false;
        gen.textContent = 'Сгенерировать';
      }
    });
    const upload = h('button', { class: 'btn ghost wide', id: 'avatar-upload', style: 'margin-top:8px' }, 'Загрузить из галереи');
    upload.addEventListener('click', async () => {
      const f = await pickFile();
      if (!f) return;
      upload.disabled = true;
      upload.textContent = 'Загружаю…';
      try { const r = await uploadImage(f, 1024); onUse(r.id); s.close(); } catch (e) { err.textContent = e.message; upload.disabled = false; upload.textContent = 'Загрузить из галереи'; }
    });
    fill(body, h('label', { class: 'lbl' }, 'Внешность или кто это (необязательно)'), desc, h('label', { class: 'lbl' }, 'Стиль'), grid, err, gen, upload);
  };
  const showResult = (iid, desc) => {
    description = desc;
    body.replaceChildren(
      h('div', { class: 'portrait', style: 'width:200px' }, authImg('/v1/images/' + iid, 'Результат')),
      h('button', { class: 'btn primary wide', id: 'avatar-use', onclick: () => { onUse(iid); s.close(); } }, 'Использовать'),
      h('button', { class: 'btn ghost wide', style: 'margin-top:8px', onclick: showMain }, 'Сгенерировать заново'));
  };
  showMain();
}

// ------------------------------------------------------------------ stories
async function startStory(id, withFriend) {
  const r = await api(`/v1/stories/${id}/rooms`, { method: 'POST' });
  if (withFriend) await api(`/v1/rooms/${r.room.id}/invite`, { method: 'POST', body: { user_id: withFriend } });
  location.hash = '#/chat/' + r.room.id;
}
async function pickFriendSheet(onPick) {
  let fr;
  try { fr = (await api('/v1/friends')).friends || []; } catch (e) { toast(e.message); return; }
  const s = sheet('С кем играть?', fr.length ? fr.map((f) => h('button', { class: 'list-item', 'data-friend': f.nick, onclick: () => { s.close(); onPick(f); } },
    avatar(f.nick, userAvatarPath(f), 40), h('div', { class: 'grow' }, h('div', { class: 't' }, f.nick))))
    : h('div', { class: 'muted' }, 'Сначала добавь друга во вкладке «Друзья».'));
}

async function screenStory(root, id) {
  const page = subPage(root, '', '#/characters');
  let st;
  try { st = (await api('/v1/stories/' + id)).story; } catch (e) { page.append(errorBox(e.message, () => render())); return; }
  $('.title', page).textContent = st.title;
  if (st.mine) {
    $('.topbar', page).append(
      h('button', { class: 'icon-btn', id: 'story-edit', 'aria-label': 'Изменить', onclick: () => { location.hash = '#/story-edit/' + id; } }, icon('edit')),
      h('button', { class: 'icon-btn', id: 'story-delete', 'aria-label': 'Удалить', style: 'color:var(--muted)', onclick: async () => {
        if (!(await confirmSheet('Удалить историю?', 'Вместе с ней удалятся все её сцены и переписка в них.', 'Удалить', true))) return;
        try { await api('/v1/stories/' + id, { method: 'DELETE' }); location.hash = '#/characters'; } catch (e) { toast(e.message); }
      } }, icon('trash')));
  }
  const cover = storyCover(st);
  const pub = st.visibility === 'public';
  const go = (friend) => async (e) => {
    const b = e.currentTarget;
    b.disabled = true;
    try { await startStory(id, friend); } catch (ex) { toast(ex.message); b.disabled = false; }
  };
  const solo = h('button', { class: 'btn primary grow', id: 'story-play' }, 'Играть');
  solo.addEventListener('click', go(null));
  const withFriend = h('button', { class: 'btn ghost grow', id: 'story-play-friend' }, 'С другом');
  withFriend.addEventListener('click', () => pickFriendSheet((f) => startStory(id, f.id).catch((e) => toast(e.message))));
  const pubBtn = st.mine ? h('button', { class: 'btn ghost wide', id: 'story-publish-toggle', style: 'margin-top:10px' }, icon('globe', 20),
    pub ? 'Сделать личной' : 'Опубликовать для всех') : null;
  if (pubBtn) pubBtn.addEventListener('click', async () => {
    try {
      await api(`/v1/stories/${id}/visibility`, { method: 'PATCH', body: { visibility: pub ? 'private' : 'public' } });
      toast(pub ? 'История снова личная' : 'История опубликована');
      render();
    } catch (e) { toast(e.message); }
  });
  const chars = (st.characters || []).map((c) => h('div', { class: 'list-item', style: 'cursor:default' },
    avatar(c.name, c.avatar_image_id ? `/v1/stories/${id}/images/${c.avatar_image_id}` : null, 44),
    h('div', { class: 'grow', style: 'min-width:0' }, h('div', { class: 't' }, c.name, c.role === 'hero' ? h('span', { class: 'pill lilac', style: 'margin-left:6px' }, 'герой игрока') : null),
      c.appearance || c.personality ? h('div', { class: 's', style: 'display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden' }, c.appearance || c.personality) : null)));
  put(page,
    cover ? h('div', { class: 'story-cover' }, authImg(cover, st.title)) : null,
    h('div', { class: 'center', style: 'font-size:24px;font-weight:700;margin-top:8px' }, st.title),
    h('div', { class: 'center muted' }, st.mine ? (pub ? 'Твоя история · публичная' : 'Твоя история · личная') : 'Автор: ' + ((st.author && st.author.nick) || '—')),
    h('div', { class: 'row', style: 'margin-top:14px' }, solo, withFriend), pubBtn,
    !st.mine ? h('div', { class: 'hint' }, 'Ты сыграешь свою копию истории — её можно менять, оригинал автора не изменится.') : null,
    st.description ? [h('div', { class: 'section' }, 'О чём'), h('div', { style: 'white-space:pre-wrap' }, st.description)] : null,
    st.world_rules ? [h('div', { class: 'section' }, 'Мир'), h('div', { class: 'muted', style: 'white-space:pre-wrap' }, st.world_rules)] : null,
    chars.length ? [h('div', { class: 'section' }, 'Персонажи'), chars] : null);
}

/** Story editor: world, place, several characters (with voices), first messages, visibility. */
async function screenStoryEdit(root, id) {
  const page = subPage(root, id ? 'Редактирование истории' : 'Новая история', '#/characters');
  let st = { title: '', description: '', intro: '', world_rules: '', start_scene: '', cover_image_id: null, visibility: 'private',
    characters: [{ key: 'k' + uuid().slice(0, 8), role: 'npc', name: '' }], start_messages: [] };
  if (id) {
    try { st = (await api('/v1/stories/' + id)).story; } catch (e) { page.append(errorBox(e.message, () => render())); return; }
    if (!st.mine) { page.append(errorBox('Это не твоя история.', null)); return; }
  }
  let cover = st.cover_image_id;
  let visibility = st.visibility || 'private';
  const title = h('input', { class: 'field', id: 's-title', value: st.title || '' });
  const area = (idv, val, ph, rows = 3) => { const t = autoGrow(h('textarea', { class: 'field', id: idv, rows, placeholder: ph })); t.value = val || ''; return t; };
  const desc = area('s-desc', st.description, 'О чём история — это увидят в каталоге');
  const world = area('s-world', st.world_rules, 'Эпоха, место, правила мира, тон');
  const scene = area('s-scene', st.start_scene, 'Где начинается действие и что вокруг', 2);
  const intro = area('s-intro', st.intro, 'Вступление, которое игроки прочитают первым (необязательно)', 2);

  const coverTile = h('button', { class: 'avatar-tile', id: 's-cover', type: 'button', style: `background:${gradFor(st.title || '?')};width:120px;aspect-ratio:4/3` });
  const drawCover = () => coverTile.replaceChildren(cover ? authImg(id && cover === st.cover_image_id ? `/v1/stories/${id}/images/${cover}` : '/v1/images/' + cover, 'Обложка') : h('span', null, 'Обложка'));
  drawCover();
  coverTile.addEventListener('click', async () => {
    const f = await pickFile();
    if (!f) return;
    try { cover = (await uploadImage(f, 1280)).id; drawCover(); } catch (e) { toast(e.message); }
  });

  // characters
  const charsBox = h('div', { id: 's-chars' });
  const rows = [];
  function charRow(c) {
    const r = { c: { ...c }, avatar: c.avatar_image_id || null };
    const name = h('input', { class: 'field', 'data-field': 'name', placeholder: 'Имя', maxlength: 40, value: c.name || '' });
    const role = h('select', { class: 'field', 'data-field': 'role' }, h('option', { value: 'npc' }, 'Ведёт ИИ'), h('option', { value: 'hero' }, 'Герой игрока'));
    role.value = c.role || 'npc';
    const look = area('', c.appearance, 'Внешность', 2);
    const pers = area('', c.personality, 'Характер', 2);
    const speech = area('', c.speech_style, 'Манера речи в тексте', 2);
    const back = area('', c.backstory, 'Предыстория (необязательно)', 2);
    const av = h('button', { class: 'avatar-tile', type: 'button', style: `background:${gradFor(c.name || '?')};width:72px` });
    const drawAv = () => av.replaceChildren(r.avatar ? authImg(id && r.avatar === c.avatar_image_id ? `/v1/stories/${id}/images/${r.avatar}` : '/v1/images/' + r.avatar, 'Аватар') : h('span', null, 'Аватар'));
    drawAv();
    av.addEventListener('click', () => avatarSheet(name.value, look.value, (iid) => { r.avatar = iid; drawAv(); }));
    const voice = voiceFields(c, 'c' + rows.length);
    const voiceWrap = h('div', null, voice.el);
    const syncRole = () => voiceWrap.classList.toggle('hidden', role.value !== 'npc');
    role.addEventListener('change', syncRole);
    syncRole();
    const del = h('button', { class: 'icon-btn small', type: 'button', 'aria-label': 'Убрать персонажа', style: 'color:var(--error)' }, icon('trash', 18));
    r.el = h('div', { class: 'card char-card', style: 'margin-top:12px' },
      h('div', { class: 'row' }, av, h('div', { class: 'grow' }, name, role), del),
      look, pers, speech, back, voiceWrap);
    del.addEventListener('click', () => { rows.splice(rows.indexOf(r), 1); r.el.remove(); drawStarts(); });
    name.addEventListener('change', drawStarts);
    r.value = () => ({ ...r.c, name: name.value.trim(), role: role.value, appearance: look.value.trim(), personality: pers.value.trim(),
      speech_style: speech.value.trim(), backstory: back.value.trim(), avatar_image_id: r.avatar, ...voice.value(),
      key: r.c.key || r.c.id });
    rows.push(r);
    charsBox.append(r.el);
  }
  (st.characters || []).forEach(charRow);
  const addChar = h('button', { class: 'btn ghost wide', id: 's-add-char', type: 'button', style: 'margin-top:10px' }, icon('plus', 18), 'Добавить персонажа');
  addChar.addEventListener('click', () => { if (rows.length >= 10) { toast('До 10 персонажей'); return; } charRow({ key: 'k' + uuid().slice(0, 8), role: 'npc', name: '' }); drawStarts(); });

  // first messages
  const startsBox = h('div', { id: 's-starts' });
  let starts = (st.start_messages || []).map((m) => ({ ...m }));
  function drawStarts() {
    const opts = () => [h('option', { value: 'narrator' }, 'Рассказчик'),
      ...rows.filter((r) => r.value().role === 'npc' && r.value().name).map((r) => h('option', { value: r.value().key }, r.value().name))];
    fill(startsBox, starts.map((m, i) => {
      const sp = h('select', { class: 'field' }, ...opts());
      sp.value = m.speaker || 'narrator';
      if (sp.value !== (m.speaker || 'narrator')) sp.value = 'narrator';
      sp.addEventListener('change', () => { m.speaker = sp.value; });
      const t = area('', m.text, '*Действие* и реплика с тире', 2);
      t.addEventListener('input', () => { m.text = t.value; });
      return h('div', { class: 'card', style: 'margin-top:10px' }, h('div', { class: 'row' }, h('div', { class: 'grow' }, sp),
        h('button', { class: 'icon-btn small', type: 'button', 'aria-label': 'Убрать', style: 'color:var(--error)', onclick: () => { starts.splice(i, 1); drawStarts(); } }, icon('trash', 18))), t);
    }));
  }
  drawStarts();
  const addStart = h('button', { class: 'btn ghost wide', id: 's-add-start', type: 'button', style: 'margin-top:10px' }, icon('plus', 18), 'Добавить первое сообщение');
  addStart.addEventListener('click', () => { starts.push({ speaker: 'narrator', text: '' }); drawStarts(); });

  const seg = h('div', { class: 'seg' });
  const drawSeg = () => seg.replaceChildren(...[['public', 'Публичная'], ['private', 'Личная']].map(([v, l]) =>
    h('button', { type: 'button', id: 's-vis-' + v, class: visibility === v ? 'on' : '', onclick: () => { visibility = v; drawSeg(); } }, l)));
  drawSeg();

  const err = h('div', { class: 'error', id: 's-error' });
  const save = h('button', { class: 'btn primary wide', id: 's-save', style: 'margin-top:14px' }, 'Сохранить');
  save.addEventListener('click', async () => {
    err.textContent = '';
    const characters = rows.map((r) => r.value());
    if (!title.value.trim()) { err.textContent = 'Дай истории название.'; return; }
    if (characters.some((c) => !c.name)) { err.textContent = 'У каждого персонажа должно быть имя.'; return; }
    if (!characters.some((c) => c.role === 'npc')) { err.textContent = 'Нужен хотя бы один персонаж, которого ведёт ИИ.'; return; }
    if (characters.filter((c) => c.role === 'hero').length > 2) { err.textContent = 'Героев игроков может быть не больше двух.'; return; }
    const body = { title: title.value.trim(), description: desc.value.trim(), world_rules: world.value.trim(), start_scene: scene.value.trim(),
      intro: intro.value.trim(), cover_image_id: cover, visibility, characters,
      start_messages: starts.filter((m) => (m.text || '').trim()).map((m) => ({ speaker: m.speaker || 'narrator', text: m.text.trim() })) };
    save.disabled = true;
    try {
      const r = id ? await api('/v1/stories/' + id, { method: 'PUT', body }) : await api('/v1/stories', { method: 'POST', body });
      location.replace('#/story/' + r.story.id);
    } catch (e) { err.textContent = e.message; save.disabled = false; }
  });

  put(page,
    h('div', { class: 'row', style: 'margin-top:6px' }, coverTile,
      h('div', { class: 'grow' }, h('div', { style: 'font-weight:600' }, 'История'),
        h('div', { class: 'muted small' }, 'Мир, место и несколько персонажей. Играть можно одному или с другом — тогда у каждого свой герой.'))),
    counted('Название *', title, 80),
    counted('Описание', desc, 1500),
    counted('Мир и правила', world, 3000),
    counted('Стартовая сцена', scene, 1000),
    counted('Вступление', intro, 2000),
    h('div', { class: 'section' }, 'Персонажи'),
    h('div', { class: 'hint' }, '«Ведёт ИИ» — за них отвечает ИИ и озвучивает их голосом. «Герой игрока» — за него пишешь ты или друг (до двух).'),
    charsBox, addChar,
    h('div', { class: 'section' }, 'Первые сообщения'), startsBox, addStart,
    h('label', { class: 'lbl' }, 'Видимость'), seg,
    h('div', { class: 'hint' }, 'Публичную историю видят все; другие играют свою копию и не меняют твою.'),
    err, save);
}

// ------------------------------------------------------------------ chats list
async function screenChats(root) {
  const page = tabPage(root, 'chats', 'Чаты', 'Личные чаты с персонажами и сцены с друзьями');
  const box = h('div', { id: 'rooms' }, h('div', { class: 'muted' }, 'Загрузка…'));
  page.append(box);
  async function load() {
    try {
      const r = await api('/v1/rooms');
      const items = [];
      if (r.invites && r.invites.length) {
        items.push(h('div', { class: 'section' }, 'Приглашения'));
        for (const inv of r.invites) {
          items.push(h('div', { class: 'list-item', id: 'invite-' + inv.id },
            avatar(inv.from.nick, null, 44),
            h('div', { class: 'grow' }, h('div', { class: 't ellipsis' }, inv.story_title), h('div', { class: 's' }, 'Зовёт ' + inv.from.nick)),
            h('button', { class: 'btn small ghost', onclick: async () => { try { await api(`/v1/invites/${inv.id}/decline`, { method: 'POST' }); load(); refreshBadges(); } catch (e) { toast(e.message); } } }, 'Нет'),
            h('button', { class: 'btn small primary', id: 'invite-accept', onclick: async () => {
              try { const a = await api(`/v1/invites/${inv.id}/accept`, { method: 'POST' }); refreshBadges(); location.hash = '#/chat/' + (a.room_id || inv.room_id); } catch (e) { toast(e.message); }
            } }, 'Играть')));
        }
      }
      items.push(h('div', { class: 'section' }, 'Мои чаты'));
      if (!r.rooms.length) items.push(h('div', { class: 'muted' }, 'Пока пусто. Открой персонажа и нажми «Начать чат».'));
      for (const room of r.rooms) {
        items.push(h('button', { class: 'list-item', 'data-room': room.id, onclick: () => { location.hash = '#/chat/' + room.id; } },
          avatar(room.story_title, room.cover_image_id ? `/v1/rooms/${room.id}/images/${room.cover_image_id}` : null, 48),
          h('div', { class: 'grow' },
            h('div', { class: 't ellipsis' }, room.story_title),
            h('div', { class: 's ellipsis' }, room.last_message || '')),
          h('span', { class: 'pill ' + (room.kind === 'chat' ? '' : 'lilac') }, room.kind === 'chat' ? 'чат' : room.partner ? 'вдвоём' : 'сцена')));
      }
      box.replaceChildren(...items);
    } catch (e) {
      box.replaceChildren(errorBox(e.message, load));
    }
  }
  load();
}

// ------------------------------------------------------------------ chat
// "*улыбается* — Привет. *думает о своём*" → [{act, text}] — actions/thoughts and spoken parts
function segments(text) {
  const out = [];
  let i = 0;
  text = text || '';
  const push = (act, raw) => {
    for (const piece of raw.split(/\n+/)) {
      const t = piece.trim();
      if (t && !/^[.,;:!?—–-]+$/.test(t)) out.push({ act, text: t });
    }
  };
  while (i < text.length) {
    const s = text.indexOf('*', i);
    const e = s >= 0 ? text.indexOf('*', s + 1) : -1;
    if (s < 0 || e < 0) { push(false, text.slice(i)); break; }
    push(false, text.slice(i, s));
    push(true, text.slice(s + 1, e));
    i = e + 1;
  }
  return out;
}

// keep the chat exactly inside the visible area (iPhone keyboard, PWA status bar)
function fitToViewport(el) {
  const vv = window.visualViewport;
  const fit = () => {
    if (vv) {
      el.style.height = vv.height + 'px';
      el.style.transform = `translateY(${vv.offsetTop}px)`;
    }
  };
  fit();
  if (vv) { vv.addEventListener('resize', fit); vv.addEventListener('scroll', fit); }
  document.documentElement.classList.add('chat-open');
  return () => {
    if (vv) { vv.removeEventListener('resize', fit); vv.removeEventListener('scroll', fit); }
    document.documentElement.classList.remove('chat-open');
  };
}

function screenChat(root, rid) {
  const me = store.me || {};
  const st = { rev: 0, pv: -1, msgs: new Map(), room: null, gen: null, job: null, pending: [], suggestions: [], busy: false, uploading: 0 };
  const ctrl = new AbortController();
  let alive = true;
  const els = new Map(); // message id -> { el, sig }

  const title = h('div', { class: 'title ellipsis' }, 'Чат');
  const sub = h('div', { class: 'sub ellipsis' });
  const aiBtn = h('button', { class: 'icon-btn hidden', id: 'ai-mode', 'aria-label': 'Режим ИИ' });
  const menuBtn = h('button', { class: 'icon-btn', id: 'chat-menu', 'aria-label': 'Ещё', style: 'color:#fff' }, icon('more'));
  const top = h('div', { class: 'topbar' },
    h('button', { class: 'icon-btn', id: 'back', 'aria-label': 'Назад', onclick: () => { location.hash = '#/chats'; } }, icon('back')),
    h('div', { class: 'grow', style: 'min-width:0' }, title, sub), aiBtn, menuBtn);
  const offline = h('div', { class: 'offline hidden', id: 'offline' }, 'Нет связи — переподключаюсь…');
  const list = h('div', { class: 'msgs', id: 'msgs' });
  const status = h('div', { id: 'status' });
  list.append(status);

  // composer: white icon tools at the edges, the input with a "*" button, send
  const tool = (id, ic, label) => h('button', { class: 'tool', id, type: 'button', 'aria-label': label, title: label }, icon(ic, 22));
  const editBtn = tool('edit-last', 'edit', 'Изменить последний ответ');
  const suggestBtn = tool('suggest', 'sparkle', 'Варианты реплики');
  const regenBtn = tool('regenerate', 'refresh', 'Перегенерировать');
  const contBtn = tool('continue', 'forward', 'Продолжить сцену');
  const sceneBtn = tool('photo', 'camera', 'Картинка сцены: авто или по описанию');
  const uploadBtn = tool('upload', 'image', 'Отправить своё фото');
  const panelBox = h('div');
  const suggBox = h('div', { id: 'suggestions' });
  const input = autoGrow(h('textarea', { class: 'field', id: 'chat-input', rows: 1, placeholder: 'Сообщение…' }), 140);
  const starBtn = h('button', { class: 'star', id: 'star', type: 'button', 'aria-label': 'Действие в звёздочках' }, '*');
  const sendBtn = h('button', { class: 'send', id: 'send', disabled: true, 'aria-label': 'Отправить' }, icon('send', 24));
  const composer = h('div', { class: 'composer' }, panelBox, suggBox,
    h('div', { class: 'toolbar' }, h('div', { class: 'tools' }, editBtn, suggestBtn, regenBtn, contBtn), h('div', { class: 'tools' }, sceneBtn, uploadBtn)),
    h('div', { class: 'inputrow' }, h('div', { class: 'inputwrap' }, input, starBtn), sendBtn));
  const chat = h('div', { class: 'chat' }, top, offline, list, composer);
  root.append(chat);
  const unfit = fitToViewport(chat);

  const active = () => st.gen && (st.gen.status === 'queued' || st.gen.status === 'running');
  const visible = () => Array.from(st.msgs.values()).filter((m) => !m.hidden).sort((a, b) => a.seq - b.seq);
  const lastText = () => { const v = visible().filter((m) => !m.image_id && m.kind !== 'system'); return v[v.length - 1]; };
  const lastAiMsg = () => { const l = lastText(); return l && l.kind !== 'player' && l.generation_id ? l : null; };
  const canEdit = (m) => !m.image_id && m.kind !== 'system' && (m.kind !== 'player' || m.user_id === me.id);
  const chars = () => (st.room && st.room.story && st.room.story.characters) || [];
  const charById = (cid) => chars().find((c) => c.id === cid);
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 140;
  const toBottom = () => { list.scrollTop = list.scrollHeight; };

  function longPress(el, onLong) {
    let t;
    const start = () => { t = setTimeout(onLong, 520); };
    const stop = () => clearTimeout(t);
    el.addEventListener('pointerdown', start);
    ['pointerup', 'pointerleave', 'pointercancel'].forEach((ev) => el.addEventListener(ev, stop));
    el.addEventListener('pointermove', (e) => { if (Math.abs(e.movementY) > 4 || Math.abs(e.movementX) > 4) stop(); });
    el.addEventListener('contextmenu', (e) => { e.preventDefault(); onLong(); });
  }

  function photoEl(m, cls) {
    const path = `/v1/rooms/${rid}/images/${m.image_id}`;
    const frame = h('div', { class: 'frame' }, authImg(path, m.text));
    frame.addEventListener('click', () => authImage(path).then((u) => {
      const v = h('div', { class: 'viewer', onclick: () => v.remove() }, h('img', { src: u, alt: m.text }));
      document.body.append(v);
    }));
    return h('div', { class: 'photo ' + (cls || ''), 'data-kind': 'photo' },
      cls ? null : h('div', { class: 'lbl2' }, 'ФОТО СЦЕНЫ'), frame,
      m.text && m.text !== 'Фото сцены' ? h('div', { class: 'cap' }, m.text) : null);
  }

  function speakBtn(m) {
    if (!st.room || !st.room.voice_available) return null;
    const b = h('button', { class: 'speak', type: 'button', 'data-speak': m.id, 'aria-label': 'Озвучить' }, icon('speaker', 17));
    b.addEventListener('click', (e) => { e.stopPropagation(); playVoice(m.id, `/v1/rooms/${rid}/messages/${m.id}/speech`); });
    return b;
  }
  const onVoice = () => {
    for (const b of list.querySelectorAll('[data-speak]')) {
      const k = b.getAttribute('data-speak');
      b.classList.toggle('on', PLAYER.key === k);
      b.classList.toggle('busy', PLAYER.key === 'loading:' + k);
      b.replaceChildren(icon(PLAYER.key === k ? 'stop' : 'speaker', 17));
    }
  };
  document.addEventListener('voice-state', onVoice);

  function msgEl(m) {
    if (m.image_id && m.kind !== 'player') return photoEl(m);
    if (m.kind === 'system') return h('div', { class: 'm-system' }, m.text);
    if (m.kind === 'narrator') {
      const el = h('div', { class: 'narrator', 'data-kind': 'narrator' }, h('div', { class: 'lbl2' }, 'РАССКАЗЧИК', speakBtn(m)),
        h('div', { class: 'txt' }, richText(m.text, true)), m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
      if (canEdit(m)) longPress(el, () => openEdit(m));
      return el;
    }
    if (m.kind === 'character') {
      const c = charById(m.character_id);
      const path = c && c.avatar_image_id ? `/v1/rooms/${rid}/images/${c.avatar_image_id}` : null;
      const av = avatar(m.speaker_name, path, 36);
      av.style.cursor = 'pointer';
      av.addEventListener('click', () => { if (st.room && st.room.kind === 'chat' && m.character_id) location.hash = '#/persona/' + m.character_id; });
      // thoughts and actions on the black background, every spoken part as its own bubble
      const parts = segments(m.text).map((sg) => (sg.act ? h('div', { class: 'thought' }, sg.text) : h('div', { class: 'bubble char' }, sg.text)));
      const col = h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, m.speaker_name, speakBtn(m)), parts,
        m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
      if (canEdit(m)) longPress(col, () => openEdit(m));
      return h('div', { class: 'm-row', 'data-kind': 'character' }, av, col);
    }
    // player
    const mine = m.user_id === me.id;
    const seat = st.room && st.room.seats ? st.room.seats.find((s) => s.user && s.user.id === m.user_id) : null;
    const nick = seat && seat.user ? seat.user.nick : '';
    const label = m.speaker_name + (nick && nick !== m.speaker_name ? ' · ' + nick : '');
    const body = m.image_id ? photoEl(m, 'own')
      : h('div', { class: 'bubble ' + (mine ? 'mine' : 'friend') }, richText(m.text, false), m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
    if (!m.image_id && canEdit(m)) longPress(body, () => openEdit(m));
    const col = h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, label), body);
    const av = avatar(m.speaker_name, seat && seat.user ? userAvatarPath(seat.user) : null, 30);
    return h('div', { class: 'm-row ' + (mine ? 'mine' : 'friend'), 'data-kind': mine ? 'mine' : 'friend' }, mine ? [col, av] : [av, col]);
  }

  function drawMessages() {
    const stick = nearBottom();
    let prev = null;
    const keep = new Set();
    for (const m of visible()) {
      const sig = `${m.rev}|${m.text}|${m.edited}|${m.image_id}|${m.kind}|${st.room ? st.room.meta_rev : 0}`;
      let rec = els.get(m.id);
      if (!rec || rec.sig !== sig) {
        const el = msgEl(m);
        if (rec) rec.el.replaceWith(el);
        rec = { el, sig };
        els.set(m.id, rec);
      }
      keep.add(m.id);
      const want = prev ? prev.nextSibling : list.firstChild;
      if (want !== rec.el) list.insertBefore(rec.el, want);
      prev = rec.el;
    }
    for (const [mid, rec] of els) if (!keep.has(mid)) { rec.el.remove(); els.delete(mid); }
    drawStatus();
    if (stick) toBottom();
  }

  function drawStatus() {
    const parts = [];
    for (const p of st.pending) {
      parts.push(h('div', { class: 'm-row mine pending' }, h('div', { class: 'm-col' },
        h('div', { class: 'bubble mine' }, richText(p.text, false)),
        p.failed ? h('div', { class: 'row small', style: 'justify-content:flex-end;gap:4px' },
          h('span', { class: 'error', style: 'margin:0' }, 'Не отправлено'),
          h('button', { class: 'link accent', onclick: () => { p.failed = false; sendPending(p); drawStatus(); } }, 'Повторить'),
          h('button', { class: 'link', onclick: () => { st.pending = st.pending.filter((x) => x !== p); drawStatus(); } }, 'Удалить')) : null)));
    }
    if (st.uploading) parts.push(h('div', { class: 'status' }, 'Отправляю фото…'));
    const g = st.gen;
    const last = lastText();
    if (g && g.status === 'queued') {
      parts.push(h('div', { class: 'status', id: 'generation-status' }, 'печатает', h('span', { class: 'typing' }, h('i'), h('i'), h('i'))));
    } else if (g && g.status === 'running') {
      const text = (g.partial || '').replace(/^[^:\n*]{1,40}:\s*/, '');
      parts.push(h('div', { class: 'm-row', id: 'generation-status' }, avatar('…', null, 36),
        h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, 'печатает', h('span', { class: 'typing' }, h('i'), h('i'), h('i'))),
          text.trim() ? segments(text).map((sg) => (sg.act ? h('div', { class: 'thought' }, sg.text) : h('div', { class: 'bubble char' }, sg.text))) : null)));
    } else if (g && g.status === 'failed' && !(last && last.generation_id === g.id)) {
      parts.push(h('div', { class: 'failcard', id: 'generation-failed' }, h('b', null, 'Ответ не получился'),
        h('div', { class: 'muted small', style: 'margin:4px 0 10px' }, (g.error || '') + ' Твой ход сохранён, предыдущий ответ тоже.'),
        h('button', { class: 'btn primary small', id: 'retry', onclick: () => action('retry') }, 'Повторить генерацию')));
    }
    const j = st.job;
    if (j && (j.status === 'queued' || j.status === 'running')) parts.push(h('div', { class: 'status' }, 'Рисую сцену…'));
    else if (j && j.status === 'failed' && j.id === st.jobFresh) parts.push(h('div', { class: 'failcard' }, h('b', null, 'Фото не получилось'), h('div', { class: 'muted small' }, j.error || '')));
    fill(status, parts);
    // tools
    const busy = active();
    const room = st.room;
    contBtn.disabled = busy || st.busy;
    regenBtn.disabled = busy || st.busy || !lastAiMsg();
    editBtn.disabled = busy || !lastAiMsg();
    const drawing = j && (j.status === 'queued' || j.status === 'running');
    sceneBtn.disabled = !room || !room.images_available || drawing;
    sendBtn.disabled = !input.value.trim() || (busy && g.kind === 'regenerate');
    if (room) {
      title.textContent = room.title || (room.story && room.story.title) || 'Чат';
      sub.textContent = room.kind === 'chat' ? 'Личный чат' : seatLine(room);
      aiBtn.classList.toggle('hidden', !room.local_available);
      aiBtn.replaceChildren(icon(room.ai_mode === 'cloud' ? 'cloud' : 'chip'));
    }
  }

  function seatLine(room) {
    const seat = (s) => (!s.user || s.user.nick === s.hero_name ? s.hero_name : `${s.hero_name} — ${s.user.nick}`);
    const a = room.seats[0];
    const b = room.seats[1];
    const first = a ? seat(a) : '';
    if (b && b.user) return first + ' · ' + seat(b);
    if (room.invite && room.invite.status === 'pending') return first + ' · ждём ' + ((room.invite.to && room.invite.to.nick) || 'друга');
    return first;
  }

  function apply(s) {
    for (const m of s.messages) st.msgs.set(m.id, m);
    if (s.room) st.room = s.room;
    st.gen = s.generation;
    st.job = s.image_job;
    st.pv = s.pv;
    st.rev = s.rev;
    const ids = new Set(Array.from(st.msgs.values()).map((m) => m.client_id).filter(Boolean));
    st.pending = st.pending.filter((p) => !ids.has(p.clientId));
    drawMessages();
  }

  async function loop() {
    let since = 0;
    while (alive) {
      try {
        const s = await api(`/v1/rooms/${rid}/sync?since=${since}&pv=${st.pv}&wait=${since === 0 ? 0 : 25}`, { signal: ctrl.signal });
        if (!alive) return;
        apply(s);
        if (since === 0) toBottom();
        since = s.rev;
        offline.classList.add('hidden');
      } catch (e) {
        if (!alive || e.name === 'AbortError') return;
        if (e.status === 404) {
          list.replaceChildren(errorBox('Чат не найден или удалён.', () => { location.hash = '#/chats'; }));
          composer.remove();
          return;
        }
        offline.classList.remove('hidden');
        await sleep(3000);
      }
    }
  }

  async function sendPending(p) {
    try {
      await api(`/v1/rooms/${rid}/messages`, { method: 'POST', body: { client_id: p.clientId, text: p.text } });
    } catch (e) {
      p.failed = true;
      toast(e.message);
      drawStatus();
    }
  }
  function send() {
    const text = input.value.trim();
    if (!text) return;
    const p = { clientId: uuid(), text, failed: false };
    st.pending.push(p);
    input.value = '';
    input.dispatchEvent(new Event('input'));
    st.suggestions = [];
    drawSugg();
    drawStatus();
    toBottom();
    sendPending(p);
  }
  async function action(kind) {
    if (st.busy) return;
    st.busy = true;
    drawStatus();
    try {
      const r = await api(`/v1/rooms/${rid}/${kind}`, { method: 'POST', body: { client_id: uuid() } });
      if (r.generation) st.gen = r.generation;
    } catch (e) { toast(e.message); }
    st.busy = false;
    drawStatus();
  }

  function openEdit(m) {
    const ta = autoGrow(h('textarea', { class: 'field', id: 'edit-input', rows: 3 }), 220);
    ta.value = m.text;
    const save = h('button', { class: 'btn primary small', id: 'edit-save' }, 'Сохранить');
    save.addEventListener('click', async () => {
      const t = ta.value.trim();
      if (!t || t === m.text) { closePanel(); return; }
      save.disabled = true;
      try {
        const r = await api(`/v1/rooms/${rid}/messages/${m.id}`, { method: 'PATCH', body: { text: t } });
        st.msgs.set(r.message.id, r.message);
        closePanel();
        drawMessages();
      } catch (e) { toast(e.message); save.disabled = false; }
    });
    panelBox.replaceChildren(h('div', { class: 'panel', id: 'edit-panel' },
      h('div', { class: 'row' }, h('b', { class: 'grow' }, m.kind === 'player' ? 'Изменить своё сообщение' : 'Изменить ответ ИИ'),
        h('button', { class: 'link', id: 'edit-cancel', onclick: closePanel }, 'Отмена')),
      ta, h('div', { class: 'row', style: 'justify-content:flex-end;margin-top:8px' }, save)));
    ta.focus();
  }
  function closePanel() { panelBox.replaceChildren(); }

  async function drawScene(prompt) {
    try {
      const r = await api(`/v1/rooms/${rid}/photo`, { method: 'POST', body: { client_id: uuid(), prompt: prompt || '' } });
      st.job = r.image_job;
      st.jobFresh = r.image_job && r.image_job.id;
      drawStatus();
      toBottom();
    } catch (e) { toast(e.message); }
  }
  function chooseScene() {
    const room = st.room;
    if (!room) return;
    const style = (STYLES.find(([sid]) => sid === (room.image_style || 'aesthetic')) || STYLES[0])[1];
    const s = sheet('Картинка сцены',
      h('button', { class: 'list-item', id: 'photo-auto', onclick: () => { s.close(); drawScene(''); } }, icon('sparkle'),
        h('div', { class: 'grow' }, h('div', { class: 't' }, 'Авто — по диалогу'),
          h('div', { class: 's' }, 'Что происходит сейчас, с учётом описания сцен чата'))),
      h('button', { class: 'list-item', id: 'photo-custom', onclick: () => { s.close(); openScenePrompt(); } }, icon('edit'),
        h('div', { class: 'grow' }, h('div', { class: 't' }, 'По моему описанию'), h('div', { class: 's' }, 'Напиши, что нарисовать'))),
      h('button', { class: 'list-item', id: 'photo-settings', onclick: () => { s.close(); openImageSettings(); } }, icon('sliders'),
        h('div', { class: 'grow' }, h('div', { class: 't' }, 'Стиль и описание сцен'),
          h('div', { class: 's ellipsis' }, style + (room.image_notes ? ' · ' + room.image_notes : '')))));
  }
  function openImageSettings() {
    const room = st.room;
    if (!room) return;
    const owner = room.my_role === 'owner';
    let style = room.image_style || 'aesthetic';
    const notes = autoGrow(h('textarea', { class: 'field', id: 'image-notes', rows: 3, maxlength: 1000,
      placeholder: 'Например: зимний посёлок у моря, вечер, тёплые окна. Ива — в чёрной куртке, Ян — длинные тёмные волосы.' }), 180);
    notes.value = room.image_notes || '';
    notes.disabled = !owner;
    const grid = h('div', { class: 'styles' });
    const draw = () => grid.replaceChildren(...STYLES.map(([sid, label]) =>
      styleTile(sid, label, sid === style, 'scene-style-', () => { if (owner) { style = sid; draw(); } })));
    draw();
    const save = h('button', { class: 'btn primary wide', id: 'image-settings-save', style: 'margin-top:14px', disabled: !owner }, 'Сохранить');
    save.addEventListener('click', async () => {
      save.disabled = true;
      try {
        const r = await api(`/v1/rooms/${rid}/settings`, { method: 'PATCH', body: { image_style: style, image_notes: notes.value.trim() } });
        st.room = { ...st.room, image_style: r.image_style, image_notes: r.image_notes };
        s.close();
        toast('Настройки картинок сохранены');
      } catch (e) { toast(e.message); save.disabled = false; }
    });
    const s = sheet('Картинки этого чата',
      h('div', { class: 'muted small', style: 'margin-bottom:10px;line-height:1.45' },
        'ИИ рисует сцены в выбранном стиле и всегда держится этого описания: места, обстановки, внешности героев — и не придумывает новое каждый раз.'),
      h('label', { class: 'lbl' }, 'Описание сцен'), notes,
      h('label', { class: 'lbl' }, 'Стиль'), grid,
      owner ? save : h('div', { class: 'muted small', style: 'margin-top:12px' }, 'Менять может только хозяин сцены.'));
    s.el.id = 'image-settings';
  }
  function openScenePrompt() {
    const what = h('input', { class: 'field', id: 'photo-prompt', placeholder: 'что нарисовать', maxlength: 300 });
    const go = h('button', { class: 'btn primary small', id: 'photo-confirm' }, 'Нарисовать');
    go.addEventListener('click', () => { closePanel(); drawScene(what.value.trim()); });
    panelBox.replaceChildren(h('div', { class: 'panel', id: 'photo-panel' },
      h('div', { class: 'row' }, h('b', { class: 'grow' }, 'Картинка по описанию'), h('button', { class: 'link', onclick: closePanel }, 'Отмена')),
      h('div', { class: 'row', style: 'margin-top:8px' }, what, go)));
    what.focus();
  }
  async function uploadOwnPhoto() {
    const f = await pickFile();
    if (!f) return;
    st.uploading++;
    drawStatus();
    toBottom();
    try {
      const fd = new FormData();
      fd.append('file', await prepareImage(f, 1600), 'photo.jpg');
      fd.append('client_id', uuid());
      await api(`/v1/rooms/${rid}/upload`, { method: 'POST', form: fd });
    } catch (e) { toast(e.message); }
    st.uploading--;
    drawStatus();
  }

  function drawSugg() {
    if (!st.suggestions.length) { suggBox.replaceChildren(); return; }
    const hide = h('button', { class: 'icon-btn small', id: 'suggestions-hide', 'aria-label': 'Скрыть варианты', title: 'Скрыть',
      onclick: () => { st.suggestions = []; drawSugg(); } }, icon('close', 18));
    suggBox.replaceChildren(
      h('div', { class: 'sugg-head' }, h('span', null, 'Варианты ответа'), hide),
      ...st.suggestions.map((t, i) => h('button', { class: 'sugg', id: 'suggestion-' + i, style: `animation-delay:${i * 45}ms`, onclick: () => {
        input.value = t;
        input.dispatchEvent(new Event('input'));
        st.suggestions = [];
        drawSugg();
        input.focus();
      } }, richText(t, false))));
  }

  input.addEventListener('input', () => { sendBtn.disabled = !input.value.trim(); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
  // "*": a pair of stars with the cursor between them; the keyboard stays open
  starBtn.addEventListener('pointerdown', (e) => e.preventDefault());
  starBtn.addEventListener('mousedown', (e) => e.preventDefault());
  starBtn.addEventListener('click', () => {
    const s = input.selectionStart ?? input.value.length;
    const e = input.selectionEnd ?? s;
    const v = input.value;
    const sel = v.slice(s, e);
    input.value = v.slice(0, s) + '*' + sel + '*' + v.slice(e);
    const pos = s + 1 + sel.length;
    input.focus();
    input.setSelectionRange(pos, pos);
    input.dispatchEvent(new Event('input'));
  });
  sendBtn.addEventListener('click', send);
  contBtn.addEventListener('click', () => action('continue'));
  regenBtn.addEventListener('click', () => action('regenerate'));
  editBtn.addEventListener('click', () => { const m = lastAiMsg(); if (m) openEdit(m); });
  uploadBtn.addEventListener('click', uploadOwnPhoto);
  sceneBtn.addEventListener('click', chooseScene);
  suggestBtn.addEventListener('click', async () => {
    suggestBtn.disabled = true;
    try {
      st.suggestions = (await api(`/v1/rooms/${rid}/suggest`, { method: 'POST' })).suggestions || [];
      drawSugg();
    } catch (e) { toast(e.message); }
    suggestBtn.disabled = false;
  });
  aiBtn.addEventListener('click', () => {
    const room = st.room;
    if (!room || !room.local_available) return;
    const owner = room.my_role === 'owner';
    const opt = (mode, name, text, enabled) => h('button', {
      class: 'list-item', id: 'mode-' + mode, disabled: !enabled, style: room.ai_mode === mode ? 'outline:2px solid var(--accent)' : '',
      onclick: async () => {
        s.close();
        if (mode === room.ai_mode) return;
        try { await api(`/v1/rooms/${rid}/settings`, { method: 'PATCH', body: { ai_mode: mode } }); } catch (e) { toast(e.message); }
      },
    }, icon(mode === 'cloud' ? 'cloud' : 'chip'), h('div', { class: 'grow' }, h('div', { class: 't' }, name), h('div', { class: 's' }, text)));
    const s = sheet('Кто ведёт сцену', opt('local', 'Локальный ИИ', '', owner), opt('cloud', 'Облачный ИИ', '', owner && room.cloud_available));
  });
  menuBtn.addEventListener('click', () => {
    const room = st.room;
    if (!room) return;
    const owner = room.my_role === 'owner';
    const label = room.kind === 'chat' ? 'Удалить чат' : owner ? 'Удалить сцену' : 'Выйти из сцены';
    const s = sheet(null,
      room.kind === 'chat' && room.story && room.story.characters && room.story.characters[0]
        ? h('button', { class: 'btn ghost wide', id: 'menu-persona', style: 'margin-bottom:8px', onclick: () => { s.close(); location.hash = '#/persona/' + room.story.characters[0].id; } }, 'Персонаж: описание и голос') : null,
      room.kind === 'story' && owner && room.story && room.story.mine
        ? h('button', { class: 'btn ghost wide', id: 'menu-edit-story', style: 'margin-bottom:8px', onclick: () => { s.close(); location.hash = '#/story-edit/' + room.story.id; } }, 'Редактировать историю') : null,
      h('button', { class: 'btn ghost wide', id: 'menu-image-settings', style: 'margin-bottom:8px', onclick: () => { s.close(); openImageSettings(); } }, 'Стиль и описание картинок'),
      h('button', { class: 'btn ghost wide', style: 'margin-bottom:8px', onclick: () => { s.close(); openScenePrompt(); } }, 'Картинка по своему описанию'),
      h('button', { class: 'btn danger wide', id: 'leave', onclick: async () => {
        s.close();
        if (!(await confirmSheet(label + '?', owner ? 'Переписка удалится.' : 'Ты больше не увидишь эту сцену.', 'Да', true))) return;
        try { await api('/v1/rooms/' + rid, { method: 'DELETE' }); location.hash = '#/chats'; } catch (e) { toast(e.message); }
      } }, label),
      h('button', { class: 'btn ghost wide', style: 'margin-top:8px', onclick: () => s.close() }, 'Отмена'));
  });

  loop();
  return () => { alive = false; ctrl.abort(); unfit(); stopVoice(); document.removeEventListener('voice-state', onVoice); };
}

// ------------------------------------------------------------------ friends
function screenFriends(root) {
  const page = tabPage(root, 'friends', 'Друзья');
  const search = h('input', { class: 'field', id: 'friend-search', type: 'search', placeholder: 'Найти по нику', autocomplete: 'off', autocapitalize: 'off' });
  const results = h('div', { id: 'search-results', style: 'margin-top:10px' });
  const lists = h('div', { id: 'friend-lists' });
  let timer;
  let seq = 0;
  const relationButton = (r) => {
    const u = r.user;
    if (r.relation === 'none' || r.relation === 'outgoing_declined') {
      return h('button', { class: 'btn primary small', id: 'add-' + u.nick, onclick: async (e) => {
        e.currentTarget.disabled = true;
        try { await api('/v1/friends/request', { method: 'POST', body: { user_id: u.id } }); runSearch(); loadLists(); } catch (ex) { toast(ex.message); }
      } }, r.relation === 'none' ? 'В друзья' : 'Ещё раз');
    }
    if (r.relation === 'outgoing_pending') return h('span', { class: 'pill', id: 'sent-' + u.nick }, 'Заявка отправлена');
    if (r.relation === 'friends' || r.relation === 'outgoing_accepted') return h('span', { class: 'pill lilac' }, 'В друзьях');
    if (r.relation === 'incoming_pending') {
      return h('button', { class: 'btn primary small', onclick: async () => {
        try { await api('/v1/friends/accept', { method: 'POST', body: { user_id: u.id } }); runSearch(); loadLists(); refreshBadges(); } catch (ex) { toast(ex.message); }
      } }, 'Принять');
    }
    return null;
  };
  async function runSearch() {
    const q = search.value.trim();
    const my = ++seq;
    if (q.length < 2) { results.replaceChildren(); return; }
    try {
      const r = await api('/v1/users/search?q=' + encodeURIComponent(q));
      if (my !== seq) return;
      results.replaceChildren(...r.users.map((x) => h('div', { class: 'list-item', 'data-user': x.user.nick },
        avatar(x.user.nick, userAvatarPath(x.user), 44),
        h('div', { class: 'grow' }, h('div', { class: 't ellipsis' }, x.user.nick), x.user.about ? h('div', { class: 's ellipsis' }, x.user.about) : null),
        relationButton(x))));
      if (!r.users.length) results.append(h('div', { class: 'muted' }, `Никого не нашли по «${q}».`));
    } catch (e) { if (my === seq) results.replaceChildren(h('div', { class: 'error' }, e.message)); }
  }
  function lastSeen(ts) {
    if (!ts) return 'давно не заходил(а)';
    const min = Math.floor((Date.now() - ts) / 60000);
    if (min < 60) return `был(а) ${Math.max(min, 1)} мин назад`;
    if (min < 1440) return `был(а) ${Math.floor(min / 60)} ч назад`;
    return `был(а) ${Math.floor(min / 1440)} дн назад`;
  }
  async function loadLists() {
    try {
      const f = await api('/v1/friends');
      const items = [];
      if (f.incoming.length) {
        items.push(h('div', { class: 'section' }, 'Входящие заявки'));
        for (const r of f.incoming) {
          items.push(h('div', { class: 'list-item', id: 'incoming-' + r.user.nick }, avatar(r.user.nick, userAvatarPath(r.user), 40),
            h('div', { class: 'grow t' }, r.user.nick),
            h('button', { class: 'btn small ghost', onclick: async () => { await api(`/v1/friends/requests/${r.id}/decline`, { method: 'POST' }).catch((e) => toast(e.message)); loadLists(); refreshBadges(); } }, 'Нет'),
            h('button', { class: 'btn small primary', id: 'accept-' + r.user.nick, onclick: async () => { await api(`/v1/friends/requests/${r.id}/accept`, { method: 'POST' }).catch((e) => toast(e.message)); loadLists(); refreshBadges(); } }, 'Принять')));
        }
      }
      if (f.outgoing.length) {
        items.push(h('div', { class: 'section' }, 'Мои заявки'));
        for (const r of f.outgoing) {
          items.push(h('div', { class: 'list-item' }, avatar(r.user.nick, userAvatarPath(r.user), 36), h('div', { class: 'grow' }, r.user.nick),
            h('span', { class: 'pill ' + (r.status === 'accepted' ? 'lilac' : r.status === 'declined' ? 'grey' : '') },
              r.status === 'accepted' ? 'принята' : r.status === 'declined' ? 'отклонена' : 'отправлена')));
        }
      }
      items.push(h('div', { class: 'section' }, 'Друзья'));
      if (!f.friends.length) items.push(h('div', { class: 'muted' }, 'Пока никого. Найди друга по нику и отправь заявку.'));
      for (const u of f.friends) {
        items.push(h('div', { class: 'list-item', id: 'friend-' + u.nick },
          avatar(u.nick, userAvatarPath(u), 42, u.online ? h('span', { class: 'dot' }) : null),
          h('div', { class: 'grow' }, h('div', { class: 't' }, u.nick),
            h('div', { class: 's', style: u.online ? 'color:var(--green)' : '' }, u.online ? 'в сети' : lastSeen(u.last_seen_at)))));
      }
      lists.replaceChildren(...items);
    } catch (e) { lists.replaceChildren(errorBox(e.message, loadLists)); }
  }
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(runSearch, 300); });
  put(page, search, h('div', { class: 'hint' }, 'По началу или части ника, от 2 символов'), results, lists);
  loadLists();
}

// ------------------------------------------------------------------ profile
async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (_) {
    const t = h('textarea', { style: 'position:fixed;opacity:0' });
    t.value = text;
    document.body.append(t);
    t.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (__) { ok = false; }
    t.remove();
    return ok;
  }
}

function manageList(title, id, load, rowFor) {
  const box = h('div', { id });
  const wrap = h('div', null, h('div', { class: 'section' }, title), box);
  const refresh = async () => {
    try {
      const items = await load();
      fill(box, items.length ? items.map((it) => rowFor(it, refresh)) : h('div', { class: 'muted small' }, 'Пусто.'));
    } catch (e) { fill(box, h('div', { class: 'error' }, e.message)); }
  };
  refresh();
  return wrap;
}
function trashButton(label, question, text, onYes) {
  return h('button', { class: 'icon-btn', 'aria-label': label, title: label, style: 'color:var(--error)', onclick: async (e) => {
    e.stopPropagation();
    if (!(await confirmSheet(question, text, 'Удалить', true))) return;
    try { await onYes(); } catch (ex) { toast(ex.message); }
  } }, icon('trash', 22));
}

async function screenProfile(root) {
  const page = tabPage(root, 'profile', 'Профиль');
  let u;
  try { u = (await api('/v1/me')).user; store.me = u; } catch (e) { page.append(errorBox(e.message, () => render())); return; }
  const av = h('button', { class: 'avatar', id: 'profile-avatar', style: `width:104px;height:104px;font-size:44px;margin:10px auto 6px;border:0;background:${colorFor(u.nick)}` });
  const drawAv = () => {
    av.replaceChildren((u.nick[0] || '?').toUpperCase());
    if (u.avatar_image_id) av.append(authImg(userAvatarPath(u), u.nick));
  };
  drawAv();
  const pick = async () => {
    const f = await pickFile();
    if (!f) return;
    try {
      const img = await uploadImage(f, 512);
      u = (await api('/v1/me', { method: 'PATCH', body: { avatar_image_id: img.id } })).user;
      drawAv();
      toast('Фото профиля обновлено');
    } catch (e) { toast(e.message); }
  };
  av.addEventListener('click', pick);
  const about = autoGrow(h('textarea', { class: 'field', id: 'about', rows: 3, placeholder: 'Пара слов для друзей — необязательно' }), 200);
  about.value = u.about || '';
  const saveAbout = h('button', { class: 'btn primary wide', id: 'about-save', style: 'margin-top:10px' }, 'Сохранить');
  saveAbout.addEventListener('click', async () => {
    try { u = (await api('/v1/me', { method: 'PATCH', body: { about: about.value.trim() } })).user; toast('Сохранено'); } catch (e) { toast(e.message); }
  });

  // nick: can be changed (unique, same rules as at registration)
  const nickText = h('span', { id: 'profile-nick' }, u.nick);
  const nickRow = h('div', { class: 'row', style: 'justify-content:center;gap:6px;font-size:24px;font-weight:700' }, nickText,
    h('button', { class: 'icon-btn small', id: 'nick-edit', 'aria-label': 'Изменить ник', title: 'Изменить ник', onclick: () => {
      const field = h('input', { class: 'field', id: 'nick-new', value: u.nick, maxlength: 20, autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });
      const err = h('div', { class: 'error' });
      const save = h('button', { class: 'btn primary wide', id: 'nick-save', style: 'margin-top:12px' }, 'Сохранить ник');
      save.addEventListener('click', async () => {
        save.disabled = true;
        try {
          u = (await api('/v1/me', { method: 'PATCH', body: { nick: field.value.trim() } })).user;
          store.me = { ...(store.me || {}), ...u };
          nickText.textContent = u.nick;
          drawAv();
          sh.close();
          toast('Ник изменён');
        } catch (e) { err.textContent = e.message; save.disabled = false; }
      });
      const sh = sheet('Новый ник', h('div', { class: 'muted small', style: 'margin-bottom:10px' },
        '3–20 символов: буквы, цифры, «_» и «.». Друзья увидят новый ник сразу; войти можно будет только по нему.'), field, err, save);
      field.focus();
    } }, icon('edit', 20)));

  // gender: how characters address the player
  const genderSeg = h('div', { class: 'seg', id: 'gender' });
  const drawGender = () => genderSeg.replaceChildren(...[['', 'Не указан'], ['male', 'Мужской'], ['female', 'Женский']].map(([g, l]) =>
    h('button', { type: 'button', id: 'gender-' + (g || 'none'), class: (u.gender || '') === g ? 'on' : '', onclick: async () => {
      try { u = (await api('/v1/me', { method: 'PATCH', body: { gender: g } })).user; store.me = { ...(store.me || {}), ...u }; drawGender(); } catch (e) { toast(e.message); }
    } }, l)));
  drawGender();

  // password change
  const oldPw = h('input', { class: 'field', id: 'old-password', type: 'password', placeholder: 'Старый пароль', autocomplete: 'current-password' });
  const newPw = h('input', { class: 'field', id: 'change-password', type: 'password', placeholder: 'Новый пароль (от 8 символов)', autocomplete: 'new-password', style: 'margin-top:8px' });
  const pwBtn = h('button', { class: 'btn ghost wide', id: 'change-password-save', style: 'margin-top:8px' }, 'Сменить пароль');
  pwBtn.addEventListener('click', async () => {
    try {
      await api('/v1/me/password', { method: 'POST', body: { password: newPw.value, old_password: oldPw.value } });
      oldPw.value = ''; newPw.value = '';
      toast('Пароль изменён. На других устройствах нужно войти заново.');
      drawDevices();
    } catch (e) { toast(e.message); }
  });

  // devices signed in to this account; a lost phone is signed out from here
  const devicesInfo = h('div', { class: 'muted small', id: 'devices-count', style: 'margin-top:6px;line-height:1.5' });
  const othersBtn = h('button', { class: 'btn ghost wide', id: 'logout-others', style: 'margin-top:10px' }, 'Выйти на других устройствах');
  const drawDevices = async () => {
    try {
      const n = (await api('/v1/me/sessions')).count;
      devicesInfo.textContent = n > 1 ? `Аккаунт открыт на ${n} устройствах, включая это.` : 'Аккаунт открыт только на этом устройстве.';
      othersBtn.disabled = n <= 1;
    } catch (_) { devicesInfo.textContent = ''; }
  };
  othersBtn.addEventListener('click', async () => {
    if (!(await confirmSheet('Выйти на других устройствах?', 'На всех остальных телефонах и компьютерах придётся войти заново. Это устройство останется в аккаунте.', 'Выйти на других', true))) return;
    try {
      const r = await api('/v1/logout/others', { method: 'POST' });
      toast(r.signed_out ? `Готово: вышли на ${r.signed_out} устр.` : 'Других устройств не было');
      drawDevices();
    } catch (e) { toast(e.message); }
  });
  drawDevices();

  // transfer code: tap to copy
  const codeBox = h('div', { id: 'transfer-box' });
  let tick;
  const codeBtn = h('button', { class: 'btn ghost wide', id: 'transfer-code-button', style: 'margin-top:12px' }, 'Получить код переноса');
  codeBtn.addEventListener('click', async () => {
    try {
      const r = await api('/v1/me/transfer-code', { method: 'POST' });
      const until = Date.now() + r.ttl_s * 1000;
      clearInterval(tick);
      const codeEl = h('button', { class: 'code', id: 'transfer-code', style: 'margin-top:14px;display:block;width:100%;background:none;border:0',
        onclick: async () => { toast((await copyText(r.code)) ? 'Код скопирован' : 'Не получилось скопировать'); } }, r.code);
      const left = h('div', { class: 'center muted small' });
      fill(codeBox, codeEl, left, h('div', { class: 'center faint small' }, 'Нажми на код, чтобы скопировать'));
      const draw = () => {
        const sec = Math.max(0, Math.round((until - Date.now()) / 1000));
        left.textContent = sec > 0 ? `Действует ещё ${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, '0')}` : 'Код истёк — получи новый.';
        if (!sec) { clearInterval(tick); codeEl.style.opacity = '.3'; }
      };
      draw();
      tick = setInterval(draw, 1000);
      codeBtn.textContent = 'Новый код';
    } catch (e) { toast(e.message); }
  });

  put(page, av,
    h('div', { class: 'row', style: 'justify-content:center' },
      h('button', { class: 'link accent', onclick: pick }, u.avatar_image_id ? 'Сменить фото' : 'Добавить фото'),
      u.avatar_image_id ? h('button', { class: 'link', onclick: async () => {
        try { u = (await api('/v1/me', { method: 'PATCH', body: { avatar_image_id: '' } })).user; drawAv(); } catch (e) { toast(e.message); }
      } }, 'Убрать') : null),
    nickRow,
    h('label', { class: 'lbl' }, 'Пол — так к тебе будут обращаться персонажи'), genderSeg,
    h('label', { class: 'lbl' }, 'О себе'), about, saveAbout,
    h('div', { class: 'card', style: 'margin-top:20px' },
      h('div', { style: 'font-weight:600' }, 'Вход с другого устройства'),
      h('div', { class: 'muted small', style: 'margin-top:6px;line-height:1.5' },
        'Войди по нику и паролю. Или получи одноразовый код переноса (действует 10 минут) и введи его в «Вход по коду переноса».'),
      codeBtn, codeBox),
    h('div', { class: 'card', style: 'margin-top:14px' }, h('div', { style: 'font-weight:600;margin-bottom:8px' }, 'Пароль'), oldPw, newPw, pwBtn),
    h('div', { class: 'card', style: 'margin-top:14px' }, h('div', { style: 'font-weight:600' }, 'Устройства'), devicesInfo, othersBtn),
    manageList('Мои персонажи', 'my-personas', async () => (await api('/v1/personas?scope=mine')).personas, (p, refresh) =>
      h('div', { class: 'list-item', 'data-persona': p.name },
        avatar(p.name || '?', personaAvatarPath(p), 40),
        h('button', { class: 'grow', style: 'background:none;border:0;text-align:left;padding:0', onclick: () => { location.hash = '#/persona/' + p.id; } },
          h('div', { class: 't ellipsis' }, p.name || 'Без имени'), h('div', { class: 's' }, p.status === 'draft' ? 'черновик' : p.visibility === 'public' ? 'публичный' : 'личный')),
        trashButton('Удалить персонажа', 'Удалить персонажа?', 'Карточка исчезнет у всех. Чаты с ним останутся, но новых ответов не будет.',
          async () => { await api('/v1/personas/' + p.id, { method: 'DELETE' }); refresh(); }))),
    manageList('Мои истории', 'my-stories', async () => (await api('/v1/stories')).stories, (st, refresh) =>
      h('div', { class: 'list-item' },
        h('div', { class: 'grow' }, h('div', { class: 't ellipsis' }, st.title), h('div', { class: 's' }, st.is_demo ? 'демо-история' : 'своя история')),
        trashButton('Удалить историю', 'Удалить историю?', 'Вместе с ней удалятся все её сцены и переписка в них.',
          async () => { await api('/v1/stories/' + st.id, { method: 'DELETE' }); refresh(); }))),
    manageList('Мои чаты', 'my-rooms', async () => (await api('/v1/rooms')).rooms, (r, refresh) =>
      h('div', { class: 'list-item' },
        h('button', { class: 'grow', style: 'background:none;border:0;text-align:left;padding:0', onclick: () => { location.hash = '#/chat/' + r.id; } },
          h('div', { class: 't ellipsis' }, r.story_title), h('div', { class: 's ellipsis' }, r.last_message || '')),
        trashButton(r.my_role === 'owner' ? 'Удалить' : 'Выйти', r.my_role === 'owner' ? 'Удалить переписку?' : 'Выйти из сцены?',
          r.my_role === 'owner' ? 'Переписка удалится навсегда.' : 'Ты больше не увидишь эту сцену.',
          async () => { await api('/v1/rooms/' + r.id, { method: 'DELETE' }); refresh(); }))),
    installHint(),
    h('div', { class: 'card', style: 'margin-top:14px' },
      h('div', { class: 'muted small' }, 'Android-приложение: ', h('a', { href: '/fonar.apk', download: 'GramSoul.apk', style: 'color:var(--accent)' }, 'скачать GramSoul.apk'))),
    h('button', { class: 'btn danger wide', id: 'logout', style: 'margin-top:18px', onclick: async () => {
      if (!(await confirmSheet('Выйти из аккаунта?', 'Войти снова можно по нику и паролю.', 'Выйти', true))) return;
      try { await api('/v1/logout', { method: 'POST' }); } catch (_) {}
      store.token = null; store.me = null;
      location.hash = '#/login';
    } }, 'Выйти'),
    h('div', { class: 'center faint small', id: 'app-version', style: 'margin-top:18px' }, 'GramSoul Web ' + WEB_VERSION));
}

// ------------------------------------------------------------------ router
const ROUTES = [
  [/^#\/login$/, screenLogin],
  [/^#\/set-password$/, screenSetPassword],
  [/^#\/characters$/, screenCharacters],
  [/^#\/persona\/([\w-]+)$/, screenPersona],
  [/^#\/persona-edit(?:\/([\w-]+))?$/, screenPersonaEdit],
  [/^#\/story\/([\w-]+)$/, screenStory],
  [/^#\/story-edit(?:\/([\w-]+))?$/, screenStoryEdit],
  [/^#\/chats$/, screenChats],
  [/^#\/chat\/([\w-]+)$/, screenChat],
  [/^#\/friends$/, screenFriends],
  [/^#\/profile$/, screenProfile],
];
let cleanup = null;
let renderSeq = 0;
async function render() {
  const my = ++renderSeq;
  if (cleanup) { try { cleanup(); } catch (_) {} cleanup = null; }
  document.querySelectorAll('.scrim, .viewer').forEach((x) => x.remove());
  let hash = location.hash || '#/characters';
  if (!store.token && hash !== '#/login') { location.replace('#/login'); return; }
  if (store.token && (!store.me || store.me.has_password === undefined)) {
    try { store.me = (await api('/v1/me')).user; } catch (_) { if (!store.token) return; }
  }
  if (store.token && store.me && store.me.has_password === false && hash !== '#/set-password') { location.replace('#/set-password'); return; }
  const route = ROUTES.find(([re]) => re.test(hash));
  if (!route) { location.replace('#/characters'); return; }
  const root = $('#app');
  root.replaceChildren();
  window.scrollTo(0, 0);
  const args = hash.match(route[0]).slice(1);
  const res = await route[1](root, ...args);
  if (my === renderSeq && typeof res === 'function') cleanup = res;
  if (store.token) { inboxLoop(); refreshBadges(); }
}
window.addEventListener('hashchange', render);
window.addEventListener('DOMContentLoaded', render);
