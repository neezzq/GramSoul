/* GramSoul admin page: every user with the tokens they spent (text / avatars / scene photos) and
   players' own photos (kept a week; delete earlier here). Password-protected; the session token lives
   only in this tab (sessionStorage). Text goes in through textContent only. */
'use strict';
const $ = (s) => document.querySelector(s);
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;  // CSSOM, allowed by the strict CSP (a style attribute is not)
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const kid of kids.flat(3)) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}
const tokenKey = 'gs_admin';
const token = () => sessionStorage.getItem(tokenKey);
async function api(path, method = 'GET', body) {
  const headers = {};
  if (token()) headers['X-Admin-Token'] = token();
  if (body) headers['Content-Type'] = 'application/json';
  const r = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined, cache: 'no-store' });
  const data = await r.json().catch(() => null);
  if (r.status === 401) { sessionStorage.removeItem(tokenKey); showLogin('Сессия закончилась — войди снова.'); throw new Error('auth'); }
  if (!r.ok) throw new Error((data && data.detail && data.detail.message) || ('Ошибка ' + r.status));
  return data;
}
const fmt = (n) => (n || 0).toLocaleString('ru-RU');
const money = (n) => '$' + (n || 0).toFixed(n >= 1 ? 2 : 4);
const date = (ts) => (ts ? new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '—');

function showLogin(msg) {
  const pw = h('input', { class: 'field', type: 'password', id: 'admin-password', placeholder: 'Пароль администратора', autocomplete: 'current-password' });
  const err = h('div', { class: 'error' }, msg || '');
  const form = h('form', null, pw, err, h('button', { class: 'btn primary wide', id: 'admin-login', style: 'margin-top:10px' }, 'Войти'));
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const r = await fetch('/v1/admin/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ password: pw.value }) });
      const d = await r.json().catch(() => null);
      if (!r.ok) { err.textContent = (d && d.detail && d.detail.message) || (r.status === 404 ? 'Админка не настроена: запусти на сервере deploy/set-admin-password.sh' : 'Ошибка ' + r.status); return; }
      sessionStorage.setItem(tokenKey, d.token);
      showPanel('users');
    } catch (_) { err.textContent = 'Нет связи с сервером.'; }
  });
  $('#admin').replaceChildren(h('div', { class: 'a-login' }, h('img', { src: '/app/logo.png', alt: 'GramSoul' }),
    h('h2', null, 'Админка'), form));
  pw.focus();
}

function showPanel(tab) {
  const body = h('div');
  const seg = h('div', { class: 'seg', style: 'max-width:520px' },
    h('button', { class: tab === 'users' ? 'on' : '', id: 'tab-users', onclick: () => showPanel('users') }, 'Пользователи'),
    h('button', { class: tab === 'photos' ? 'on' : '', id: 'tab-photos', onclick: () => showPanel('photos') }, 'Фото игроков'),
    h('button', { class: tab === 'posts' ? 'on' : '', id: 'tab-posts', onclick: () => showPanel('posts') }, 'Публикации'));
  $('#admin').replaceChildren(h('div', { class: 'a-page' },
    h('div', { class: 'a-head' }, h('img', { src: '/app/icon-192.png', alt: '' }), h('h1', null, 'GramSoul · админка'),
      h('button', { class: 'btn ghost small', id: 'admin-logout', onclick: async () => {
        try { await api('/v1/admin/logout', 'POST'); } catch (_) {}
        sessionStorage.removeItem(tokenKey); showLogin();
      } }, 'Выйти')),
    seg, body));
  ({ users: loadUsers, photos: loadPhotos, posts: loadPosts }[tab] || loadUsers)(body);
}

async function loadUsers(body) {
  body.replaceChildren(h('div', { class: 'muted', style: 'margin-top:12px' }, 'Загрузка…'));
  let d;
  try { d = await api('/v1/admin/users'); } catch (e) { if (e.message !== 'auth') body.replaceChildren(h('div', { class: 'error' }, e.message)); return; }
  const t = d.total;
  const totals = h('div', { class: 'a-totals' },
    h('div', { class: 'card' }, 'Пользователей', h('b', { id: 'total-users' }, fmt(t.users))),
    h('div', { class: 'card' }, 'Токены на текст', h('b', null, fmt(t.text))),
    h('div', { class: 'card' }, 'Токены на аватарки', h('b', null, fmt(t.avatar))),
    h('div', { class: 'card' }, 'Токены на фото сцен', h('b', null, fmt(t.photo))),
    h('div', { class: 'card' }, 'Озвучка, символов', h('b', null, fmt(t.voice || 0))),
    h('div', { class: 'card' }, 'Потрачено всего', h('b', null, money(t.cost))));
  const cols = [
    ['nick', 'Ник'], ['created_at', 'Регистрация'], ['last_seen_at', 'Был(а)'], ['text_tokens', 'Текст, токены', 1],
    ['avatar_tokens', 'Аватарки, токены', 1], ['avatars', 'Аватарок', 1], ['photo_tokens', 'Фото сцен, токены', 1],
    ['scene_photos', 'Фото сцен', 1], ['voice_chars', 'Озвучка, симв.', 1], ['photos', 'Свои фото', 1], ['personas', 'Персонажей', 1], ['rooms', 'Чатов', 1], ['coins', 'Монетки', 1], ['elite_until', 'Elite до'], ['cost', 'Стоимость', 1]];
  let sortKey = 'cost';
  let desc = true;
  const tbody = h('tbody');
  const draw = () => {
    const rows = [...d.users].sort((a, b) => {
      const x = a[sortKey]; const y = b[sortKey];
      const c = typeof x === 'string' ? x.localeCompare(y) : (x || 0) - (y || 0);
      return desc ? -c : c;
    });
    tbody.replaceChildren(...rows.map((u) => h('tr', { 'data-nick': u.nick },
      h('td', null, h('b', null, u.nick), u.has_password ? '' : h('span', { class: 'pill grey', style: 'margin-left:6px' }, 'без пароля')),
      h('td', null, date(u.created_at)), h('td', null, date(u.last_seen_at)),
      h('td', { class: 'num' }, fmt(u.text_tokens)), h('td', { class: 'num' }, fmt(u.avatar_tokens)), h('td', { class: 'num' }, fmt(u.avatars)),
      h('td', { class: 'num' }, fmt(u.photo_tokens)), h('td', { class: 'num' }, fmt(u.scene_photos)), h('td', { class: 'num' }, fmt(u.voice_chars || 0)),
      h('td', { class: 'num' }, fmt(u.photos)),
      h('td', { class: 'num' }, fmt(u.personas)), h('td', { class: 'num' }, fmt(u.rooms)),
      h('td', { class: 'num', 'data-coins': u.nick }, fmt(u.coins || 0)), h('td', { 'data-elite': u.nick }, u.elite_until ? date(u.elite_until) : '—'),
      h('td', { class: 'num' }, money(u.cost)),
      h('td', null, h('button', { class: 'btn small', 'data-grant': u.nick, title: 'Подарить монетки или дни Elite', onclick: () => grantSheet(u, draw) }, 'Выдать')),
      h('td', null, h('button', { class: 'btn danger small', 'data-delete': u.nick, title: 'Удалить игрока со всеми его данными', onclick: async () => {
        if (!confirm(`Удалить игрока «${u.nick}» навсегда — вместе с его персонажами, историями, чатами и фото?`)) return;
        try {
          await api('/v1/admin/users/' + u.id, 'DELETE');
          d.users = d.users.filter((x) => x.id !== u.id);
          draw();
        } catch (e) { if (e.message !== 'auth') alert(e.message); }
      } }, 'Удалить')))));
  };
  const head = h('tr', null, cols.map(([k, label, num]) => h('th', { class: num ? 'num' : '', onclick: () => {
    desc = sortKey === k ? !desc : true; sortKey = k; draw();
  } }, label)), h('th', null, ''), h('th', null, ''));
  draw();
  // why the voice-over fails right now (key, balance, OpenRouter privacy settings) — players only see «недоступна»
  const vp = d.voice_problem;
  const voiceNote = vp ? h('div', { class: 'error', id: 'voice-problem', style: 'margin-top:12px' },
    `Озвучка не работает (${date(vp.at)}): ${vp.text}. Последняя удачная озвучка: ${vp.ok_at ? date(vp.ok_at) : 'не было с запуска сервера'}.`) : '';
  body.replaceChildren(totals, voiceNote, h('div', { class: 'a-wrap' }, h('table', { class: 'a-table', id: 'users-table' }, h('thead', null, head), tbody)));
}

async function loadPhotos(body) {
  body.replaceChildren(h('div', { class: 'muted', style: 'margin-top:12px' }, 'Загрузка…'));
  let d;
  try { d = await api('/v1/admin/photos'); } catch (e) { if (e.message !== 'auth') body.replaceChildren(h('div', { class: 'error' }, e.message)); return; }
  const grid = h('div', { class: 'a-photos', id: 'photos' });
  for (const p of d.photos) {
    const img = h('img', { alt: '' });
    fetch('/v1/admin/photos/' + p.id, { headers: { 'X-Admin-Token': token() } })
      .then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b) img.src = URL.createObjectURL(b); });
    const card = h('div', { class: 'a-photo', 'data-photo': p.id },
      h('div', { class: 'img' }, img),
      h('div', { class: 'meta' }, h('b', null, p.nick || '—'), ' · ', p.room || '—', h('br'),
        'загружено ', date(p.created_at), h('br'), 'удалится ', date(p.expires_at), h('br'),
        Math.round((p.size || 0) / 1024) + ' КБ · ' + p.width + '×' + p.height,
        h('button', { class: 'btn danger small wide', style: 'margin-top:8px', onclick: async () => {
          if (!confirm('Удалить это фото у всех сейчас?')) return;
          try { await api('/v1/admin/photos/' + p.id, 'DELETE'); card.remove(); } catch (e) { if (e.message !== 'auth') alert(e.message); }
        } }, 'Удалить сейчас')));
    grid.append(card);
  }
  body.replaceChildren(h('div', { class: 'muted small', style: 'margin:12px 0' },
    `Свои фото игроков из чатов. Каждое удаляется автоматически через ${d.ttl_days} дней; здесь можно удалить раньше.`),
  d.photos.length ? grid : h('div', { class: 'muted' }, 'Фото нет.'));
}

// a gift to a player: coins and/or days of Elite (to try things out or to reward someone)
function grantSheet(u, redraw) {
  const coins = h('input', { class: 'field', id: 'grant-coins', type: 'number', min: 0, max: 100000, value: 0 });
  const days = h('input', { class: 'field', id: 'grant-days', type: 'number', min: 0, max: 3650, value: 0 });
  const err = h('div', { class: 'error hidden' });
  const close = () => back.remove();
  const go = h('button', { class: 'btn primary', id: 'grant-go', onclick: async () => {
    const body = { coins: Math.max(0, parseInt(coins.value, 10) || 0), elite_days: Math.max(0, parseInt(days.value, 10) || 0) };
    if (!body.coins && !body.elite_days) { err.textContent = 'Укажи монетки или дни Elite.'; err.classList.remove('hidden'); return; }
    go.disabled = true;
    try {
      const r = await api('/v1/admin/users/' + u.id + '/grant', 'POST', body);
      u.coins = r.coins;
      u.elite_until = r.elite_until && r.elite_until > Date.now() ? r.elite_until : null;
      close(); redraw();
    } catch (e) { go.disabled = false; if (e.message !== 'auth') { err.textContent = e.message; err.classList.remove('hidden'); } }
  } }, 'Выдать');
  const back = h('div', { class: 'a-sheet-back', onclick: (e) => { if (e.target === back) close(); } },
    h('div', { class: 'card a-sheet' },
      h('h3', null, 'Подарок для «' + u.nick + '»'),
      h('label', { class: 'muted small' }, 'Монетки'), coins,
      h('label', { class: 'muted small' }, 'Дни Elite (продлевают текущую подписку)'), days, err,
      h('div', { class: 'row', style: 'gap:8px;margin-top:12px' }, h('button', { class: 'btn ghost', onclick: close }, 'Отмена'), go)));
  document.body.append(back);
  coins.focus();
}

// the feed: any post can be removed (rules, complaints)
async function loadPosts(body) {
  body.replaceChildren(h('div', { class: 'muted', style: 'margin-top:12px' }, 'Загрузка…'));
  let d;
  try { d = await api('/v1/admin/posts'); } catch (e) { if (e.message !== 'auth') body.replaceChildren(h('div', { class: 'error' }, e.message)); return; }
  const list = h('div', { class: 'a-posts', id: 'posts' });
  for (const p of d.posts) {
    const imgs = h('div', { class: 'a-post-imgs' }, p.images.map((iid) => {
      const img = h('img', { alt: '' });
      fetch('/v1/admin/posts/' + p.id + '/images/' + iid, { headers: { 'X-Admin-Token': token() } })
        .then((r) => (r.ok ? r.blob() : null)).then((b) => { if (b) img.src = URL.createObjectURL(b); });
      return img;
    }));
    const card = h('div', { class: 'card a-post', 'data-post': p.id },
      h('div', { class: 'muted small' }, h('b', null, p.nick), ' · ', date(p.created_at)),
      p.text ? h('div', { class: 'a-post-text' }, p.text) : null, p.images.length ? imgs : null,
      h('button', { class: 'btn danger small', style: 'margin-top:8px', onclick: async () => {
        if (!confirm('Удалить эту публикацию вместе с комментариями?')) return;
        try { await api('/v1/admin/posts/' + p.id, 'DELETE'); card.remove(); } catch (e) { if (e.message !== 'auth') alert(e.message); }
      } }, 'Удалить'));
    list.append(card);
  }
  body.replaceChildren(h('div', { class: 'muted small', style: 'margin:12px 0' }, 'Последние публикации в ленте. Удалённая пропадает у всех сразу.'),
    d.posts.length ? list : h('div', { class: 'muted' }, 'Публикаций нет.'));
}

window.addEventListener('DOMContentLoaded', () => (token() ? showPanel('users') : showLogin()));
