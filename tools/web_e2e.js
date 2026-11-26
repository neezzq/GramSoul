// End-to-end check of the web app (iPhone viewport) against tools/web_dev.py with the fake model.
//   node tools/web_e2e.js http://127.0.0.1:8010 out_dir
const { chromium, devices } = require('playwright');
const fs = require('fs');

const base = process.argv[2] || 'http://127.0.0.1:8010';
const out = process.argv[3] || 'web-screens';
fs.mkdirSync(out, { recursive: true });
const phone = devices['iPhone 15 Pro'] || devices['iPhone 14 Pro'] || devices['iPhone 13'];
const results = [];
const ok = (name, cond, info = '') => { results.push([name, !!cond]); console.log((cond ? 'OK   ' : 'FAIL ') + name + (info ? ' — ' + info : '')); };
const uniq = (p) => p + '_' + (Date.now() % 100000);

async function apiAs(token, path, method = 'GET', body) {
  const r = await fetch(base + path, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return r.json();
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...phone });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) errors.push(m.text()); });
  page.on('console', (m) => { if (/Content Security Policy|Refused to/.test(m.text())) errors.push('CSP: ' + m.text()); });
  const shot = (n) => page.screenshot({ path: `${out}/${n}.png` });
  try {
    await page.goto(base + '/app/');
    await page.waitForSelector('#nick');
    const me = uniq('Mira');
    await shot('web_01_login');
    await page.fill('#nick', me);
    await page.click('#login');
    await page.waitForSelector('#persona-search');
    await page.waitForSelector('[data-name="Вера Солнцева"]');
    ok('registered by nick, characters listed', true, me);
    await shot('web_02_characters');

    // personal chat
    await page.click('[data-name="Вера Солнцева"]');
    await page.click('#persona-chat-new');
    await page.waitForSelector('#chat-input');
    await page.waitForSelector('text=стеклянную дверь');
    ok('chat opens with the character greeting', true);
    await page.fill('#chat-input', '*снимаю шляпу* Добрый вечер');
    await page.click('#send');
    await page.waitForSelector('.bubble.char >> text=Ответ №', { timeout: 20000 });
    await page.waitForSelector('#edit-last-ai', { timeout: 20000 });
    ok('streamed reply in the character voice', true);
    await shot('web_03_chat');
    await page.click('#suggest');
    await page.waitForSelector('#suggestion-2');
    await page.click('#suggestion-1');
    ok('three suggestions, one fills the input', (await page.inputValue('#chat-input')) === 'Кто ты такой?');
    await page.click('#edit-last-ai');
    await page.fill('#edit-input', '*Вера смеётся* — Поправленный ответ.');
    await page.click('#edit-save');
    await page.waitForSelector('text=Поправленный ответ');
    await page.waitForSelector('.bubble.char .edited');
    ok('AI reply edited, marked "изменено"', true);
    await shot('web_04_edited');
    const before = await page.locator('.bubble.char').last().innerText();
    await page.click('#regenerate');
    await page.waitForFunction((b) => { const x = document.querySelectorAll('.bubble.char'); return x.length && x[x.length - 1].innerText !== b && !document.querySelector('#generation-status'); }, before, { timeout: 20000 });
    ok('regenerate replaces the reply', true);

    // chats list
    await page.click('#back');
    await page.waitForSelector('[data-room]');
    ok('chat listed under Чаты', true);
    await shot('web_05_chats');

    // friends
    const other = await apiAs(null, '/v1/register', 'POST', { nick: uniq('Kirill') });
    await apiAs(other.token, '/v1/me', 'PATCH', { about: 'Играю за мага' });
    await page.click('#tab-friends');
    await page.fill('#friend-search', other.user.nick.slice(2).toLowerCase());
    await page.waitForSelector(`[data-user="${other.user.nick}"]`);
    await page.click(`#add-${other.user.nick}`);
    await page.waitForSelector(`#sent-${other.user.nick}`);
    ok('people search by part of a nick, request sent', true);
    await shot('web_06_friends');

    // profile + transfer code
    await page.click('#tab-profile');
    await page.waitForSelector('#profile-nick');
    await page.click('#transfer-code-button');
    const code = (await page.textContent('#transfer-code')).trim();
    ok('transfer code shown', /^[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(code), code);
    await shot('web_07_profile');

    // create a character with AI fill and a styled AI avatar
    await page.click('#tab-characters');
    await page.click('#create-persona');
    await page.fill('#fill-idea', 'хозяйка маяка с секретом');
    await page.click('#fill');
    await page.waitForFunction(() => document.querySelector('#p-name').value === 'Ветта');
    await page.click('#avatar-tile');
    await page.click('#style-manhwa');
    await shot('web_08_avatar_styles');
    await page.click('#avatar-generate');
    await page.click('#avatar-use');
    await page.click('#vis-public');
    await page.click('#publish');
    await page.waitForSelector('#persona-chat-new');
    ok('character created with AI fill + avatar and published', (await page.textContent('.topbar .title')) === 'Ветта');
    await shot('web_09_persona');

    // the same account in another "browser" via the transfer code
    const ctx2 = await browser.newContext({ ...phone });
    const p2 = await ctx2.newPage();
    await p2.goto(base + '/app/');
    await p2.click('#transfer-toggle');
    await p2.fill('#nick', me.toUpperCase());
    await p2.fill('#code', code);
    await p2.click('#login');
    await p2.waitForSelector('#persona-search');
    await p2.click('#tab-chats');
    await p2.waitForSelector('[data-room]');
    ok('second device signs in with the code and sees the chat', true);
  } catch (e) {
    ok('scenario', false, String(e).slice(0, 300));
    await shot('web_error').catch(() => {});
  }
  ok('no JavaScript errors', errors.length === 0, errors.slice(0, 3).join(' | '));
  await browser.close();
  const failed = results.filter((r) => !r[1]).length;
  console.log(`\n${results.length - failed}/${results.length} web checks passed`);
  process.exit(failed ? 1 : 0);
})();
