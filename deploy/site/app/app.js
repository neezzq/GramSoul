/* GramSoul web — the same account, characters and chats as the Android app, for iPhone
   (Safari → «Поделиться» → «На экран „Домой“») and any browser.
   Talks to the same API on the same origin. User text is only ever inserted with
   textContent / text nodes (never innerHTML). */
'use strict';

const WEB_VERSION = '1.0';

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
  const { method = 'GET', body, form, signal } = opts;
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

function screenLogin(root) {
  if (store.token) { location.hash = '#/characters'; return; }
  let transfer = false;
  const nick = h('input', { class: 'field', id: 'nick', placeholder: 'Ник', autocapitalize: 'off', autocomplete: 'username', spellcheck: 'false', maxlength: 24 });
  const code = h('input', { class: 'field hidden', id: 'code', placeholder: 'Код переноса, например ABCD-EFGH', autocapitalize: 'characters', autocomplete: 'off', maxlength: 12 });
  const hint = h('div', { class: 'hint' }, '3–20 символов: буквы, цифры, «_» и «.»');
  const err = h('div', { class: 'error', id: 'login-error' });
  const btn = h('button', { class: 'btn primary wide', id: 'login', type: 'submit', disabled: true }, 'Войти');
  const toggle = h('button', { class: 'link', type: 'button', id: 'transfer-toggle' }, 'Вход с другого устройства по коду переноса');
  const lost = sessionStorage.getItem('gs_lost');
  sessionStorage.removeItem('gs_lost');
  const update = () => {
    const e = nickError(nick.value);
    hint.textContent = e || (transfer ? 'Ник и код из профиля на старом устройстве (код действует 10 минут)' : '3–20 символов: буквы, цифры, «_» и «.»');
    hint.style.color = e ? 'var(--error)' : '';
    btn.disabled = !nick.value.trim() || !!e;
  };
  nick.addEventListener('input', () => { err.textContent = ''; update(); });
  toggle.addEventListener('click', () => {
    transfer = !transfer;
    code.classList.toggle('hidden', !transfer);
    toggle.textContent = transfer ? 'Я здесь впервые — создать ник' : 'Вход с другого устройства по коду переноса';
    err.textContent = '';
    update();
  });
  const form = h('form', null, nick, code, hint, err, btn, toggle);
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (btn.disabled) return;
    btn.disabled = true;
    err.textContent = '';
    try {
      const res = transfer
        ? await api('/v1/login/transfer', { method: 'POST', body: { nick: nick.value.trim(), code: code.value.trim() } })
        : await api('/v1/register', { method: 'POST', body: { nick: nick.value.trim() } });
      store.token = res.token;
      store.me = res.user;
      location.hash = '#/characters';
    } catch (ex) {
      err.textContent = ex.code === 'nick_taken'
        ? 'Ник занят. Если это твой ник на другом устройстве — войди по коду переноса.' : ex.message;
      if (ex.code === 'nick_taken') toggle.classList.add('accent');
    } finally {
      update();
    }
  });
  root.append(h('div', { class: 'login' },
    h('div', { class: 'orb' }),
    h('div', { class: 'brand' }, 'Gram', h('span', null, 'Soul')),
    h('div', { class: 'muted center', style: 'margin-top:6px' }, 'Ролевые чаты с ИИ-персонажами', h('br'), 'вместе с друзьями'),
    lost ? h('div', { class: 'card', style: 'margin-top:20px;font-size:14px' }, 'Сессия на этом устройстве закончилась. Войди по коду переноса или создай новый ник.') : null,
    form,
    h('div', { class: 'faint small center', style: 'margin-top:14px;line-height:1.5' },
      'Без пароля и почты: новый ник сразу становится твоим аккаунтом, ключ входа хранится на этом устройстве. ' +
      'Чтобы войти с другого устройства, создай в профиле код переноса.'),
    installHint(),
    h('div', { class: 'faint small', style: 'margin-top:16px' }, 'GramSoul Web ' + WEB_VERSION)));
  update();
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
  async function load() {
    const my = ++seq;
    try {
      const r = await api(`/v1/personas?q=${encodeURIComponent(q)}&scope=${scope}`);
      if (my !== seq) return;
      grid.replaceChildren(...r.personas.map(personaCard));
      if (!r.personas.length) grid.append(h('div', { class: 'muted' }, scope === 'drafts' ? 'Черновиков нет.' : 'Ничего не нашли.'));
    } catch (e) {
      if (my === seq) grid.replaceChildren(errorBox(e.message, load));
    }
  }
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { q = search.value.trim(); load(); }, 300); });
  drawChips();
  page.append(search, chips,
    h('button', { class: 'btn primary wide', id: 'create-persona', style: 'margin-top:12px', onclick: () => { location.hash = '#/persona-edit'; } }, icon('plus', 20), 'Создать персонажа'),
    grid);
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
  put(page, portrait,
    h('div', { class: 'center', style: 'font-size:24px;font-weight:700' }, name),
    h('div', { class: 'center muted' }, p.is_demo ? 'Персонаж GramSoul' : p.mine ? 'Твой персонаж' : 'Автор: ' + ((p.author && p.author.nick) || '—')),
    tags, actions,
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

  const err = h('div', { class: 'error', id: 'p-error' });
  async function save(publish) {
    err.textContent = '';
    if (publish && (!name.value.trim() || !first.value.trim())) { err.textContent = 'Чтобы опубликовать, заполни имя и первое сообщение.'; return; }
    const body = {
      name: name.value.trim(), first_message: first.value.trim(), description: desc.value.trim(), backstory: back.value.trim(),
      personality: pers.value.trim(), tags: tags.value.split(/[,;]/).map((s) => s.trim()).filter(Boolean),
      visibility, status: publish ? 'published' : 'draft', avatar_image_id: avatarId,
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
    h('div', { class: 'hint', style: 'margin-top:14px' }, 'Все персонажи по умолчанию 18+.'),
    err,
    h('div', { class: 'row', style: 'margin-top:14px' },
      h('button', { class: 'btn ghost grow', id: 'save-draft', onclick: () => save(false) }, 'Черновик'),
      h('button', { class: 'btn primary grow', id: 'publish', onclick: () => save(true) }, 'Опубликовать')));
}

const STYLES = [['anime', 'Аниме'], ['realism', 'Реализм'], ['painted', 'Нарисованный'], ['manhwa', 'Манхва'], ['sketch', 'Ч/б рисунок']];
function avatarSheet(name, description, onUse) {
  let style = 'anime';
  const body = h('div');
  const s = sheet('AI-аватар', body);
  s.el.id = 'avatar-sheet';
  const showMain = () => {
    const desc = autoGrow(h('textarea', { class: 'field', id: 'avatar-desc', rows: 3, placeholder: 'Волосы, глаза, одежда, настроение…' }), 160);
    desc.value = (description || '').slice(0, 400);
    const grid = h('div', { class: 'styles' });
    const draw = () => grid.replaceChildren(...STYLES.map(([sid, label]) =>
      h('button', { class: 'style' + (sid === style ? ' on' : ''), id: 'style-' + sid, type: 'button', onclick: () => { style = sid; draw(); } },
        h('img', { src: 'styles/' + sid + '.jpg', alt: label }), label)));
    draw();
    const err = h('div', { class: 'error' });
    const gen = h('button', { class: 'btn primary wide', id: 'avatar-generate', style: 'margin-top:14px' }, 'Сгенерировать');
    gen.addEventListener('click', async () => {
      if (desc.value.trim().length < 5) { err.textContent = 'Опиши внешность подробнее.'; return; }
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
    fill(body, h('label', { class: 'lbl' }, 'Опишите внешность'), desc, h('label', { class: 'lbl' }, 'Стиль'), grid, err, gen, upload);
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
function screenChat(root, rid) {
  const me = store.me || {};
  const st = { rev: 0, pv: -1, msgs: new Map(), room: null, gen: null, job: null, pending: [], editing: null, suggestions: [], busy: false, closed: false };
  const ctrl = new AbortController();
  let alive = true;
  const els = new Map(); // message id -> { el, sig }

  const title = h('div', { class: 'title ellipsis' }, 'Чат');
  const sub = h('div', { class: 'sub ellipsis' });
  const aiBtn = h('button', { class: 'icon-btn hidden', id: 'ai-mode', 'aria-label': 'Режим ИИ' });
  const menuBtn = h('button', { class: 'icon-btn', id: 'chat-menu', 'aria-label': 'Ещё', style: 'color:var(--muted)' }, icon('more'));
  const top = h('div', { class: 'topbar' },
    h('button', { class: 'icon-btn', id: 'back', 'aria-label': 'Назад', onclick: () => { location.hash = '#/chats'; } }, icon('back')),
    h('div', { class: 'grow', style: 'min-width:0' }, title, sub), aiBtn, menuBtn);
  const offline = h('div', { class: 'offline hidden', id: 'offline' }, 'Нет связи — переподключаюсь…');
  const list = h('div', { class: 'msgs', id: 'msgs' });
  const status = h('div', { id: 'status' });
  const listEnd = h('div');
  list.append(status, listEnd);

  // composer
  const chips = h('div', { class: 'chips' });
  const contBtn = h('button', { class: 'chip', id: 'continue' }, icon('forward', 18), 'Продолжить сцену');
  const regenBtn = h('button', { class: 'chip', id: 'regenerate' }, icon('refresh', 18), 'Перегенерировать');
  chips.append(contBtn, regenBtn);
  const panelBox = h('div');
  const suggBox = h('div', { id: 'suggestions' });
  const input = autoGrow(h('textarea', { class: 'field', id: 'chat-input', rows: 1, placeholder: '*действие* и реплика…' }), 140);
  const bulb = h('button', { class: 'icon-btn bulb', id: 'suggest', 'aria-label': 'Варианты реплики' }, icon('bulb', 22));
  const camBtn = h('button', { class: 'icon-btn hidden', id: 'photo', 'aria-label': 'Фото сцены' }, icon('camera', 26));
  const sendBtn = h('button', { class: 'send', id: 'send', disabled: true, 'aria-label': 'Отправить' }, icon('send', 24));
  const composer = h('div', { class: 'composer' }, panelBox, chips, suggBox,
    h('div', { class: 'inputrow' }, camBtn, h('div', { class: 'inputwrap' }, input, bulb), sendBtn));
  root.append(h('div', { class: 'chat' }, top, offline, list, composer));

  const active = () => st.gen && (st.gen.status === 'queued' || st.gen.status === 'running');
  const visible = () => Array.from(st.msgs.values()).filter((m) => !m.hidden).sort((a, b) => a.seq - b.seq);
  const lastText = () => { const v = visible().filter((m) => !m.image_id && m.kind !== 'system'); return v[v.length - 1]; };
  const canEdit = (m) => !m.image_id && m.kind !== 'system' && (m.kind !== 'player' || m.user_id === me.id);
  const chars = () => (st.room && st.room.story && st.room.story.characters) || [];
  const charById = (cid) => chars().find((c) => c.id === cid);
  const nearBottom = () => list.scrollHeight - list.scrollTop - list.clientHeight < 140;
  const toBottom = () => { list.scrollTop = list.scrollHeight; };

  function longPress(el, m) {
    if (!canEdit(m)) return;
    let t;
    const start = () => { t = setTimeout(() => openEdit(m), 520); };
    const stop = () => clearTimeout(t);
    el.addEventListener('pointerdown', start);
    ['pointerup', 'pointerleave', 'pointercancel', 'pointermove'].forEach((ev) => el.addEventListener(ev, (e) => { if (ev !== 'pointermove' || Math.abs(e.movementY) > 4) stop(); }));
    el.addEventListener('contextmenu', (e) => { e.preventDefault(); openEdit(m); });
  }

  function msgEl(m) {
    if (m.image_id) {
      const frame = h('div', { class: 'frame' }, authImg(`/v1/rooms/${rid}/images/${m.image_id}`, m.text));
      frame.addEventListener('click', () => authImage(`/v1/rooms/${rid}/images/${m.image_id}`).then((u) => {
        const v = h('div', { class: 'viewer', onclick: () => v.remove() }, h('img', { src: u, alt: m.text }));
        document.body.append(v);
      }));
      return h('div', { class: 'photo', 'data-kind': 'photo' }, h('div', { class: 'lbl2' }, 'ФОТО СЦЕНЫ'), frame,
        m.text && m.text !== 'Фото сцены' ? h('div', { class: 'cap' }, m.text) : null);
    }
    if (m.kind === 'system') return h('div', { class: 'm-system' }, m.text);
    if (m.kind === 'narrator') {
      const el = h('div', { class: 'narrator', 'data-kind': 'narrator' }, h('div', { class: 'lbl2' }, 'РАССКАЗЧИК'),
        h('div', { class: 'txt' }, richText(m.text, true)), m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
      longPress(el, m);
      return el;
    }
    if (m.kind === 'character') {
      const c = charById(m.character_id);
      const path = c && c.avatar_image_id ? `/v1/rooms/${rid}/images/${c.avatar_image_id}` : null;
      const av = avatar(m.speaker_name, path, 38);
      av.style.cursor = 'pointer';
      av.addEventListener('click', () => { if (st.room && st.room.kind === 'chat' && m.character_id) location.hash = '#/persona/' + m.character_id; });
      const bubble = h('div', { class: 'bubble char' }, richText(m.text, true), m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
      longPress(bubble, m);
      return h('div', { class: 'm-row', 'data-kind': 'character' }, av, h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, m.speaker_name), bubble));
    }
    // player
    const mine = m.user_id === me.id;
    const seat = st.room && st.room.seats ? st.room.seats.find((s) => s.user && s.user.id === m.user_id) : null;
    const nick = seat && seat.user ? seat.user.nick : '';
    const label = m.speaker_name + (nick && nick !== m.speaker_name ? ' · ' + nick : '');
    const bubble = h('div', { class: 'bubble ' + (mine ? 'mine' : 'friend') }, richText(m.text, false), m.edited ? h('span', { class: 'edited' }, 'изменено') : null);
    longPress(bubble, m);
    const col = h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, label), bubble);
    const av = avatar(m.speaker_name, seat && seat.user ? userAvatarPath(seat.user) : null, 32);
    return h('div', { class: 'm-row ' + (mine ? 'mine' : 'friend'), 'data-kind': mine ? 'mine' : 'friend' }, mine ? [col, av] : [av, col]);
  }

  function drawMessages() {
    const stick = nearBottom();
    const vis = visible();
    const keep = new Set();
    let prev = null;
    for (const m of vis) {
      const sig = `${m.rev}|${m.text}|${m.edited}|${st.room ? st.room.meta_rev : 0}`;
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
    const last = lastText();
    const lastAi = last && last.kind !== 'player' && last.generation_id ? last : null;
    for (const p of st.pending) {
      parts.push(h('div', { class: 'm-row mine pending' }, h('div', { class: 'm-col' },
        h('div', { class: 'bubble mine' }, richText(p.text, false)),
        p.failed ? h('div', { class: 'row small', style: 'justify-content:flex-end;gap:4px' },
          h('span', { class: 'error', style: 'margin:0' }, 'Не отправлено'),
          h('button', { class: 'link accent', onclick: () => { p.failed = false; sendPending(p); drawStatus(); } }, 'Повторить'),
          h('button', { class: 'link', onclick: () => { st.pending = st.pending.filter((x) => x !== p); drawStatus(); } }, 'Удалить')) : null)));
    }
    const g = st.gen;
    if (g && g.status === 'queued') {
      parts.push(h('div', { class: 'status', id: 'generation-status' }, g.queue_position ? `ИИ в очереди (${g.queue_position} перед вами)…` : 'ИИ думает…'));
    } else if (g && g.status === 'running') {
      if (g.partial && g.partial.trim()) {
        parts.push(h('div', { class: 'm-row', id: 'generation-status' }, avatar('…', null, 38),
          h('div', { class: 'm-col' }, h('div', { class: 'm-name' }, 'печатает', h('span', { class: 'typing' }, h('i'), h('i'), h('i'))),
            h('div', { class: 'bubble char' }, g.partial.replace(/^[^:\n]{1,40}:\s*/, '')))));
      } else {
        parts.push(h('div', { class: 'status', id: 'generation-status' }, 'печатает', h('span', { class: 'typing' }, h('i'), h('i'), h('i'))));
      }
    } else if (g && g.status === 'failed' && !(last && last.generation_id === g.id)) {
      parts.push(h('div', { class: 'failcard', id: 'generation-failed' }, h('b', null, 'Ответ не получился'),
        h('div', { class: 'muted small', style: 'margin:4px 0 10px' }, (g.error || '') + ' Твой ход сохранён, предыдущий ответ тоже.'),
        h('button', { class: 'btn primary small', id: 'retry', onclick: () => action('retry') }, 'Повторить генерацию')));
    } else if (lastAi && canEdit(lastAi) && !st.pending.length) {
      parts.push(h('button', { class: 'link edit-last', id: 'edit-last-ai', onclick: () => openEdit(lastAi) }, '✎ Изменить ответ'));
    }
    const j = st.job;
    if (j && (j.status === 'queued' || j.status === 'running')) parts.push(h('div', { class: 'status' }, '📷 Рисую фото сцены…'));
    else if (j && j.status === 'failed' && !st.jobSeen) parts.push(h('div', { class: 'failcard' }, h('b', null, 'Фото не получилось'), h('div', { class: 'muted small' }, j.error || '')));
    fill(status, parts);
    // composer state
    const busy = active();
    const lastIsAi = !!lastAi;
    contBtn.disabled = busy || st.busy;
    regenBtn.disabled = busy || st.busy || !lastIsAi;
    sendBtn.disabled = !input.value.trim() || (busy && g.kind === 'regenerate');
    const room = st.room;
    if (room) {
      title.textContent = room.title || (room.story && room.story.title) || 'Чат';
      sub.textContent = room.kind === 'chat' ? 'Личный чат' : seatLine(room);
      aiBtn.classList.toggle('hidden', false);
      aiBtn.replaceChildren(icon(room.ai_mode === 'cloud' ? 'cloud' : 'chip'));
      aiBtn.style.color = room.ai_mode === 'cloud' ? 'var(--accent)' : 'var(--lilac)';
      camBtn.classList.toggle('hidden', !room.images_available);
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
    if (s.image_job && st.job && s.image_job.id !== st.job.id) st.jobSeen = false;
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
          st.closed = true;
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
    st.editing = m;
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
  function closePanel() { st.editing = null; panelBox.replaceChildren(); }

  function openPhoto() {
    const what = h('input', { class: 'field', id: 'photo-prompt', placeholder: 'что показать (необязательно)', maxlength: 300 });
    const go = h('button', { class: 'btn primary small', id: 'photo-confirm' }, 'Нарисовать');
    go.addEventListener('click', async () => {
      go.disabled = true;
      try {
        const r = await api(`/v1/rooms/${rid}/photo`, { method: 'POST', body: { client_id: uuid(), prompt: what.value.trim() } });
        st.job = r.image_job;
        st.jobSeen = false;
        closePanel();
        drawStatus();
      } catch (e) { toast(e.message); go.disabled = false; }
    });
    panelBox.replaceChildren(h('div', { class: 'panel', id: 'photo-panel' },
      h('div', { class: 'row' }, h('b', { class: 'grow' }, 'Фото сцены'), h('button', { class: 'link', onclick: closePanel }, 'Отмена')),
      h('div', { class: 'muted small', style: 'margin:2px 0 8px' }, 'ИИ нарисует, что сейчас происходит, или то, что ты попросишь.'),
      h('div', { class: 'row' }, what, go)));
  }

  function drawSugg() {
    suggBox.replaceChildren(...st.suggestions.map((t, i) => h('button', { class: 'sugg', id: 'suggestion-' + i, onclick: () => {
      input.value = t;
      input.dispatchEvent(new Event('input'));
      st.suggestions = [];
      drawSugg();
      input.focus();
    } }, richText(t, false))));
  }

  input.addEventListener('input', () => { sendBtn.disabled = !input.value.trim(); });
  input.addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); send(); } });
  sendBtn.addEventListener('click', send);
  contBtn.addEventListener('click', () => action('continue'));
  regenBtn.addEventListener('click', () => action('regenerate'));
  camBtn.addEventListener('click', () => (panelBox.firstChild && panelBox.firstChild.id === 'photo-panel' ? closePanel() : openPhoto()));
  bulb.addEventListener('click', async () => {
    bulb.disabled = true;
    bulb.style.opacity = '.4';
    try {
      st.suggestions = (await api(`/v1/rooms/${rid}/suggest`, { method: 'POST' })).suggestions || [];
      drawSugg();
    } catch (e) { toast(e.message); }
    bulb.disabled = false;
    bulb.style.opacity = '';
  });
  aiBtn.addEventListener('click', () => {
    const room = st.room;
    if (!room) return;
    const owner = room.my_role === 'owner';
    const opt = (mode, name, text, enabled) => h('button', {
      class: 'list-item', id: 'mode-' + mode, disabled: !enabled, style: room.ai_mode === mode ? 'outline:2px solid var(--accent)' : '',
      onclick: async () => {
        s.close();
        if (mode === room.ai_mode) return;
        try { await api(`/v1/rooms/${rid}/settings`, { method: 'PATCH', body: { ai_mode: mode } }); } catch (e) { toast(e.message); }
      },
    }, icon(mode === 'cloud' ? 'cloud' : 'chip'), h('div', { class: 'grow' }, h('div', { class: 't' }, name), h('div', { class: 's' }, text)));
    const s = sheet('Кто ведёт сцену',
      opt('local', 'Локальный ИИ', 'Модель на нашем сервере: бесплатно, проще.', owner),
      opt('cloud', 'Облачный ИИ', 'Умнее и подробнее, рисует фото сцены.', owner && room.cloud_available),
      owner ? null : h('div', { class: 'hint' }, 'Переключать может только хозяин сцены.'));
  });
  menuBtn.addEventListener('click', () => {
    const room = st.room;
    if (!room) return;
    const owner = room.my_role === 'owner';
    const label = room.kind === 'chat' ? 'Удалить чат' : owner ? 'Удалить сцену' : 'Выйти из сцены';
    const s = sheet(null,
      h('button', { class: 'btn danger wide', id: 'leave', onclick: async () => {
        s.close();
        if (!(await confirmSheet(label + '?', owner ? 'Переписка удалится.' : 'Ты больше не увидишь эту сцену.', 'Да', true))) return;
        try { await api('/v1/rooms/' + rid, { method: 'DELETE' }); location.hash = '#/chats'; } catch (e) { toast(e.message); }
      } }, label),
      h('button', { class: 'btn ghost wide', style: 'margin-top:8px', onclick: () => s.close() }, 'Отмена'));
  });

  loop();
  return () => { alive = false; ctrl.abort(); };
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
  const codeBox = h('div', { id: 'transfer-box' });
  let tick;
  const codeBtn = h('button', { class: 'btn ghost wide', id: 'transfer-code-button', style: 'margin-top:12px' }, 'Получить код переноса');
  codeBtn.addEventListener('click', async () => {
    try {
      const r = await api('/v1/me/transfer-code', { method: 'POST' });
      const until = Date.now() + r.ttl_s * 1000;
      clearInterval(tick);
      const draw = () => {
        const left = Math.max(0, Math.round((until - Date.now()) / 1000));
        fill(codeBox, left > 0
          ? [h('div', { class: 'code', id: 'transfer-code', style: 'margin-top:14px' }, r.code),
            h('div', { class: 'center muted small' }, `Действует ещё ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`)]
          : h('div', { class: 'center error' }, 'Код истёк — получи новый.'));
        if (!left) clearInterval(tick);
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
    h('div', { class: 'center', id: 'profile-nick', style: 'font-size:24px;font-weight:700' }, u.nick),
    h('label', { class: 'lbl' }, 'О себе'), about, saveAbout,
    h('div', { class: 'card', style: 'margin-top:20px' },
      h('div', { style: 'font-weight:600' }, 'Вход с другого устройства'),
      h('div', { class: 'muted small', style: 'margin-top:6px;line-height:1.5' },
        'На другом телефоне или в другом браузере открой GramSoul, выбери «Вход с другого устройства по коду переноса» и введи ник и этот код. Код одноразовый, действует 10 минут.'),
      codeBtn, codeBox),
    installHint(),
    h('div', { class: 'card', style: 'margin-top:14px' },
      h('div', { class: 'muted small' }, 'Android-приложение: ', h('a', { href: '/fonar.apk', download: 'GramSoul.apk', style: 'color:var(--accent)' }, 'скачать GramSoul.apk'))),
    h('button', { class: 'btn danger wide', id: 'logout', style: 'margin-top:18px', onclick: async () => {
      if (!(await confirmSheet('Выйти из аккаунта?', 'Войти снова под этим ником можно только с кодом переноса с другого устройства, где ты в аккаунте. Если такого нет — ник будет потерян.', 'Выйти', true))) return;
      try { await api('/v1/logout', { method: 'POST' }); } catch (_) {}
      store.token = null; store.me = null;
      location.hash = '#/login';
    } }, 'Выйти'),
    h('div', { class: 'center faint small', id: 'app-version', style: 'margin-top:18px' }, 'GramSoul Web ' + WEB_VERSION));
}

// ------------------------------------------------------------------ router
const ROUTES = [
  [/^#\/login$/, screenLogin],
  [/^#\/characters$/, screenCharacters],
  [/^#\/persona\/([\w-]+)$/, screenPersona],
  [/^#\/persona-edit(?:\/([\w-]+))?$/, screenPersonaEdit],
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
