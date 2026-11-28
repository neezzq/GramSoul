// End-to-end check of the web app (iPhone viewport) against tools/web_dev.py with the fake model.
//   ADMIN_PASSWORD=… node tools/web_e2e.js http://127.0.0.1:8010 out_dir
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

const base = process.argv[2] || 'http://127.0.0.1:8010';
const out = process.argv[3] || 'web-screens';
const adminPassword = process.env.ADMIN_PASSWORD || '';
fs.mkdirSync(out, { recursive: true });
const phone = devices['iPhone 15 Pro'] || devices['iPhone 14 Pro'] || devices['iPhone 13'];
const results = [];
const ok = (name, cond, info = '') => { results.push([name, !!cond]); console.log((cond ? 'OK   ' : 'FAIL ') + name + (info ? ' — ' + info : '')); };
const uniq = (p) => p + '_' + (Date.now() % 100000);
// a tiny PNG for "send my own photo"
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==', 'base64');
const pngPath = path.join(out, 'own-photo.png');
fs.writeFileSync(pngPath, PNG);

async function apiAs(token, p, method = 'GET', body) {
  const r = await fetch(base + p, { method, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) }, body: body ? JSON.stringify(body) : undefined });
  return r.json();
}

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...phone, permissions: ['clipboard-read', 'clipboard-write'] });
  const page = await ctx.newPage();
  const errors = [];
  const watch = (pg) => {
    pg.on('pageerror', (e) => errors.push(String(e)));
    pg.on('console', (m) => {
      if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) errors.push(m.text());
      if (/Content Security Policy|Refused to/.test(m.text())) errors.push('CSP: ' + m.text());
    });
  };
  watch(page);
  const shot = (n, pg = page) => pg.screenshot({ path: `${out}/${n}.png` });
  try {
    await page.goto(base + '/app/');
    await page.waitForSelector('#nick');
    const me = uniq('Mira');
    const pw = 'лунный-кот-7';
    await shot('web_01_login');
    await page.click('#mode-register');
    await page.fill('#nick', me);
    await page.fill('#password', pw);
    await page.fill('#password2', pw);
    await page.click('#login');
    await page.waitForSelector('[data-name="Вера Солнцева"]');
    ok('registered with nick + password, characters listed', true, me);
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
    await page.waitForFunction(() => !document.querySelector('#generation-status'), null, { timeout: 20000 });
    const thoughts = await page.locator('[data-kind="character"]').last().locator('.thought').count();
    const bubbles = await page.locator('[data-kind="character"]').last().locator('.bubble').count();
    ok('reply: thoughts on black, speech as bubbles', thoughts >= 1 && bubbles >= 1, `${thoughts} thought(s), ${bubbles} bubble(s)`);
    const box = await page.locator('[data-kind="character"]').last().locator('.bubble').first().boundingBox();
    const vw = page.viewportSize().width;
    ok('bubbles leave room at the opposite edge', box.x + box.width < vw - 40, `right gap ${Math.round(vw - box.x - box.width)}px`);
    // the input sits at the bottom of the screen
    const ib = await page.locator('#send').boundingBox();
    ok('input row at the bottom of the screen', page.viewportSize().height - (ib.y + ib.height) < 60, `gap ${Math.round(page.viewportSize().height - ib.y - ib.height)}px`);
    await shot('web_03_chat');
    // "*" puts a pair of stars with the cursor between them
    await page.fill('#chat-input', '');
    await page.click('#star');
    const st = await page.evaluate(() => { const t = document.querySelector('#chat-input'); return [t.value, t.selectionStart]; });
    ok('"*" inserts ** with the cursor inside', st[0] === '**' && st[1] === 1, JSON.stringify(st));
    await page.fill('#chat-input', '');
    await page.click('#suggest');
    await page.waitForSelector('#suggestion-2');
    // the options can be hidden
    await page.click('#suggestions-hide');
    await page.waitForFunction(() => !document.querySelector('#suggestion-0'));
    ok('suggestions can be hidden', true);
    await page.click('#suggest');
    await page.waitForSelector('#suggestion-2');
    await page.click('#suggestion-1');
    ok('three suggestions, one fills the input', (await page.inputValue('#chat-input')) === 'Кто ты такой?');
    await page.click('#edit-last');
    await page.fill('#edit-input', '*Вера смеётся* — Поправленный ответ.');
    await page.click('#edit-save');
    await page.waitForSelector('text=Поправленный ответ');
    ok('AI reply edited from the ✎ tool', true);
    const before = await page.locator('.bubble.char').last().innerText();
    await page.click('#regenerate');
    await page.waitForFunction((b) => { const x = document.querySelectorAll('.bubble.char'); return x.length && x[x.length - 1].innerText !== b && !document.querySelector('#generation-status'); }, before, { timeout: 20000 });
    ok('regenerate replaces the reply', true);
    // voice-over of the character's line (the server answers with MP3)
    const [speech] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/speech') && r.request().method() === 'POST', { timeout: 20000 }),
      page.locator('[data-kind="character"] [data-speak]').last().click(),
    ]);
    ok('voice-over of a character line', speech.status() === 200 && (speech.headers()['content-type'] || '').includes('audio/mpeg'));
    // picture settings of this chat: a fixed scene description and a style («Эстетика» by default)
    await page.click('#photo');
    await page.click('#photo-settings');
    await page.waitForSelector('#scene-style-aesthetic.on');
    await page.fill('#image-notes', 'Оранжерея вечером, тёплые фонарики; Вера в соломенной шляпе');
    await page.click('#scene-style-anime');
    await shot('web_04a_image_settings');
    await page.click('#image-settings-save');
    await page.waitForSelector('text=Настройки картинок сохранены');
    const token = await page.evaluate(() => localStorage.getItem('gs_token'));
    const rid = page.url().split('/').pop();
    const rd = (await apiAs(token, '/v1/rooms/' + rid)).room;
    ok('chat picture settings saved (description + style)', rd.image_style === 'anime' && rd.image_notes.includes('Оранжерея'), rd.image_style);
    // scene picture: auto from the dialogue …
    await page.click('#photo');
    await page.click('#photo-auto');
    await page.waitForSelector('[data-kind="photo"]:not(.own)', { timeout: 20000 });
    ok('scene picture: auto from the dialogue', true);
    // … or by own description
    await page.waitForFunction(() => !document.querySelector('#photo').disabled, null, { timeout: 20000 });
    await page.click('#photo');
    await page.click('#photo-custom');
    await page.fill('#photo-prompt', 'они пьют чай под фонариками');
    await page.click('#photo-confirm');
    await page.waitForSelector('[data-kind="photo"] >> text=они пьют чай под фонариками', { timeout: 20000 });
    ok('scene picture: by own description', true);
    // own photo into the chat
    const [chooser] = await Promise.all([page.waitForEvent('filechooser'), page.click('#upload')]);
    await chooser.setFiles(pngPath);
    await page.waitForSelector('.photo.own img.loaded', { timeout: 20000 });
    ok('own photo sent to the chat', true);
    await shot('web_04_chat_tools');

    // profile: copy the code, change the password, manage characters / stories / chats
    await page.click('#back');
    await page.click('#tab-profile');
    await page.waitForSelector('#profile-nick');
    await page.click('#transfer-code-button');
    const code = (await page.textContent('#transfer-code')).trim();
    await page.click('#transfer-code');
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    ok('tap on the transfer code copies it', clip === code, code);
    await page.waitForSelector('#my-personas');
    await page.waitForSelector('#my-rooms .list-item');
    await page.waitForSelector('#my-stories .list-item');
    ok('profile lists my characters, stories and chats', true);
    await page.click('#my-rooms .list-item [aria-label]');
    await page.click('#confirm-ok');
    await page.waitForFunction(() => !document.querySelector('#my-rooms .list-item'));
    ok('a chat deleted from the profile', true);
    await page.fill('#old-password', pw);
    await page.fill('#change-password', pw + '!');
    await page.click('#change-password-save');
    await page.waitForSelector('text=Пароль изменён');
    ok('password changed in the profile', true);
    // another device signs in; «Выйти на других устройствах» ends its session, this one stays
    const other = await apiAs(null, '/v1/login', 'POST', { nick: me, password: pw + '!' });
    await page.click('#tab-chats'); await page.click('#tab-profile');
    await page.waitForSelector('#devices-count >> text=2 устройствах');
    await page.click('#logout-others');
    await page.click('#confirm-ok');
    await page.waitForSelector('#devices-count >> text=только на этом устройстве');
    const gone = await fetch(base + '/v1/me', { headers: { Authorization: 'Bearer ' + other.token } });
    ok('signed out on the other devices', gone.status === 401 && !!(await apiAs(token, '/v1/me')).user, String(gone.status));
    // a new nick
    const me2 = uniq('Nika');
    await page.click('#nick-edit');
    await page.fill('#nick-new', me2);
    await page.click('#nick-save');
    await page.waitForSelector('#profile-nick >> text=' + me2);
    ok('nick changed in the profile', true, me2);
    // gender: characters address the player by it
    await page.click('#gender-female');
    await page.waitForSelector('#gender-female.on');
    const tok = await page.evaluate(() => localStorage.getItem('gs_token'));
    ok('gender saved in the profile', (await apiAs(tok, '/v1/me')).user.gender === 'female');
    await shot('web_05_profile');

    // a character with a chat can be published from its page; its voice is set in the editor
    const lisa = (await apiAs(tok, '/v1/personas', 'POST', { name: 'Лиса', first_message: '*Лиса щурится* — Ну привет.', description: 'рыжая', visibility: 'private', status: 'draft' })).persona;
    await apiAs(tok, `/v1/personas/${lisa.id}/chats`, 'POST');
    await page.goto(base + '/app/#/persona/' + lisa.id);
    await page.click('#persona-publish-toggle');
    await page.waitForSelector('#persona-publish-toggle >> text=Сделать личным');
    ok('character published although a chat exists', (await apiAs(tok, '/v1/personas/' + lisa.id)).persona.visibility === 'public');
    await page.goto(base + '/app/#/persona-edit/' + lisa.id);
    await page.waitForSelector('#p-voice option[value="nova"]', { state: 'attached' });
    await page.selectOption('#p-voice', 'nova');
    await page.fill('#p-manner', 'игриво, с улыбкой');
    await shot('web_05b_voice');
    const [pre] = await Promise.all([
      page.waitForResponse((r) => r.url().includes('/v1/voice/preview'), { timeout: 20000 }),
      page.click('#p-preview'),
    ]);
    await page.click('#publish');
    await page.waitForSelector('#persona-chat-new');
    const lisa2 = (await apiAs(tok, '/v1/personas/' + lisa.id)).persona;
    ok('character voice set in the editor (with a sample)', pre.status() === 200 && lisa2.voice === 'nova' && lisa2.voice_manner === 'игриво, с улыбкой');

    // a story: world, characters with voices, first message; published for everyone
    const storyTitle = uniq('Трамвай');
    await page.goto(base + '/app/#/characters');
    await page.click('#kind-stories');
    await page.click('#create-persona');
    await page.click('#create-story-item');
    await page.fill('#s-title', storyTitle);
    await page.fill('#s-desc', 'Последний рейс через спящий город.');
    await page.fill('#s-chars input[data-field="name"]', 'Кондуктор');
    await page.waitForSelector('#c0-voice option[value="onyx"]', { state: 'attached' });
    await page.selectOption('#c0-voice', 'onyx');
    await page.click('#s-add-start');
    await page.fill('#s-starts textarea', '*Кондуктор поднимает глаза* — Конечная не скоро.');
    await shot('web_08_story_editor');
    await page.click('#s-save');
    await page.waitForSelector('#story-play');
    await page.click('#story-publish-toggle');
    await page.waitForSelector('text=История опубликована');
    const myStories = (await apiAs(tok, '/v1/stories')).stories.filter((x) => x.title === storyTitle);
    ok('story created in the editor and published', myStories.length === 1 && myStories[0].visibility === 'public');

    // another device: nick + password
    const ctx2 = await browser.newContext({ ...phone });
    const p2 = await ctx2.newPage();
    watch(p2);
    await p2.goto(base + '/app/');
    await p2.fill('#nick', me2.toUpperCase());
    await p2.fill('#password', pw + '!');
    await p2.click('#login');
    await p2.waitForSelector('#persona-search');
    ok('second device signs in with nick + password', true);

    // an account from before passwords must set one first
    const legacy = await apiAs(null, '/v1/register', 'POST', { nick: uniq('Old') });
    const ctx3 = await browser.newContext({ ...phone });
    await ctx3.addInitScript(([t, u]) => { localStorage.setItem('gs_token', t); localStorage.setItem('gs_me', u); },
      [legacy.token, JSON.stringify({ id: legacy.user.id, nick: legacy.user.nick })]);
    const p3 = await ctx3.newPage();
    watch(p3);
    await p3.goto(base + '/app/');
    await p3.waitForSelector('#new-password');
    await shot('web_06_set_password', p3);
    await p3.fill('#new-password', 'старыйаккаунт');
    await p3.fill('#new-password2', 'старыйаккаунт');
    await p3.click('#set-password');
    await p3.waitForSelector('#persona-search');
    ok('old account is asked for a password first', true);
    // another player finds the published story and plays an own copy
    await p3.click('#kind-stories');
    await p3.waitForSelector(`[data-story="${storyTitle}"]`);
    await p3.click(`[data-story="${storyTitle}"]`);
    await p3.waitForSelector('#story-play');
    await shot('web_09_public_story', p3);
    await p3.click('#story-play');
    await p3.waitForSelector('text=Конечная не скоро', { timeout: 20000 });
    ok('another player plays a published story (own copy)', true);
    // an own photo in this chat (the first chat with a photo was deleted above: its photo went with it)
    const [chooser3] = await Promise.all([p3.waitForEvent('filechooser'), p3.click('#upload')]);
    await chooser3.setFiles(pngPath);
    await p3.waitForSelector('.photo.own img.loaded', { timeout: 20000 });

    // admin page
    if (adminPassword) {
      const p4 = await (await browser.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
      watch(p4);
      await p4.goto(base + '/admin/');
      await p4.fill('#admin-password', 'неверный');
      await p4.click('#admin-login');
      await p4.waitForSelector('text=Неверный пароль');
      await p4.fill('#admin-password', adminPassword);
      await p4.click('#admin-login');
      await p4.waitForSelector(`#users-table tr[data-nick="${me2}"]`);
      const cells = await p4.locator(`#users-table tr[data-nick="${me2}"] td`).allInnerTexts();
      ok('admin sees the user with text tokens', parseInt((cells[3] || '0').replace(/\D/g, ''), 10) > 0, cells.slice(0, 5).join(' | '));
      await p4.screenshot({ path: `${out}/web_07_admin_users.png` });
      await p4.click('#tab-photos');
      await p4.waitForSelector('[data-photo]');
      ok('a deleted chat takes its photos along (only the photo of the live chat is listed)', (await p4.locator('[data-photo]').count()) === 1);
      p4.once('dialog', (d) => d.accept());
      await p4.locator('[data-photo] button').first().click();
      await p4.waitForFunction(() => !document.querySelector('[data-photo]'));
      ok('admin deletes a player photo before the week is over', true);
      // a test account is removed with everything it made
      const junk = uniq('test');
      await apiAs(null, '/v1/register', 'POST', { nick: junk, password: 'junk-pass-1' });
      await p4.click('#tab-users');
      await p4.waitForSelector(`#users-table tr[data-nick="${junk}"]`);
      p4.once('dialog', (d) => d.accept());
      await p4.click(`[data-delete="${junk}"]`);
      await p4.waitForFunction((n) => !document.querySelector(`#users-table tr[data-nick="${n}"]`), junk);
      const gone = await apiAs(null, '/v1/login', 'POST', { nick: junk, password: 'junk-pass-1' });
      ok('admin deletes a test account', !gone.token);
      // a gift of coins and Elite days from the admin page
      const coinsBefore = (await apiAs(tok, '/v1/shop')).coins;
      await p4.click(`[data-grant="${me2}"]`);
      await p4.fill('#grant-coins', '50');
      await p4.fill('#grant-days', '7');
      await p4.click('#grant-go');
      await p4.waitForFunction((n) => { const c = document.querySelector(`[data-elite="${n}"]`); return c && c.textContent !== '—'; }, me2);
      const shop2 = await apiAs(tok, '/v1/shop');
      ok('admin gives coins and Elite days', shop2.coins === coinsBefore + 50 && shop2.elite.active, `${coinsBefore} → ${shop2.coins}`);
      // a post in the feed is removed by the admin
      const badPost = (await apiAs(tok, '/v1/posts', 'POST', { text: 'Публикация для модерации ' + Date.now() })).post;
      await p4.click('#tab-posts');
      await p4.waitForSelector(`[data-post="${badPost.id}"]`);
      await p4.screenshot({ path: `${out}/web_07b_admin_posts.png` });
      p4.once('dialog', (d) => d.accept());
      await p4.click(`[data-post="${badPost.id}"] button`);
      await p4.waitForFunction((id) => !document.querySelector(`[data-post="${id}"]`), badPost.id);
      const feedNow = await apiAs(tok, '/v1/posts');
      ok('admin removes a post from the feed', !feedNow.posts.some((x) => x.id === badPost.id));
      const msgs = await page.goto(base + '/app/#/chats');
    }

    // computer: a sidebar instead of the tab bar, the list of chats next to the open chat, Enter sends
    const dk = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const desk = await apiAs(null, '/v1/register', 'POST', { nick: uniq('Desk'), password: 'desk-pass-1' });
    await dk.addInitScript(([t, u]) => { localStorage.setItem('gs_token', t); localStorage.setItem('gs_me', u); },
      [desk.token, JSON.stringify(desk.user)]);
    const p5 = await dk.newPage();
    watch(p5);
    await p5.goto(base + '/app/#/characters');
    await p5.waitForSelector('#sidenav #side-characters.on');
    ok('computer: sidebar instead of the bottom tab bar', !(await p5.isVisible('#tab-characters')) && await p5.isVisible('#side-create'));
    await p5.screenshot({ path: `${out}/web_10_desktop_characters.png` });
    const dp = (await apiAs(desk.token, '/v1/personas?scope=all')).personas[0];
    const droom = (await apiAs(desk.token, `/v1/personas/${dp.id}/chats`, 'POST')).room;
    await p5.click('#side-chats');
    await p5.waitForSelector(`[data-room="${droom.id}"]`);
    await p5.click(`[data-room="${droom.id}"]`);
    await p5.waitForSelector(`#rooms-rail [data-rail-room="${droom.id}"].on`);
    await p5.fill('#chat-input', 'Привет с компьютера');
    await p5.keyboard.press('Enter');
    await p5.waitForSelector('.m-row.mine >> text=Привет с компьютера', { timeout: 15000 });
    ok('computer: the list of chats next to the chat, Enter sends', true);
    await p5.screenshot({ path: `${out}/web_11_desktop_chat.png` });

    // phone: favourites, the feed, coins and Elite (the payment stub in test mode), the look of the profile
    const ec = await browser.newContext({ ...phone });
    const el = await apiAs(null, '/v1/register', 'POST', { nick: uniq('Elite'), password: 'elite-pass-1' });
    await ec.addInitScript(([t, u]) => { localStorage.setItem('gs_token', t); localStorage.setItem('gs_me', u); },
      [el.token, JSON.stringify(el.user)]);
    const p6 = await ec.newPage();
    watch(p6);
    await p6.goto(base + '/app/#/characters');
    await p6.waitForSelector('[data-fav="Вера Солнцева"]');
    await p6.click('[data-fav="Вера Солнцева"]');
    await p6.waitForSelector('[data-fav="Вера Солнцева"].on');
    await p6.click('#scope-favorites');
    await p6.waitForSelector('#scope-favorites.on');
    await p6.waitForFunction(() => document.querySelectorAll('#personas [data-name]').length === 1);
    ok('a character added to the favourites shows under «Избранное»', !!(await p6.$('#personas [data-name="Вера Солнцева"]')));
    await p6.click('#tab-feed');
    await p6.waitForSelector('#post-text');
    const postText = 'Публикация из сценария ' + Date.now().toString(36);
    await p6.fill('#post-text', postText + ' #проверка');
    const [ch6] = await Promise.all([p6.waitForEvent('filechooser'), p6.click('#post-add-image')]);
    await ch6.setFiles(pngPath);
    await p6.waitForSelector('.composer-thumbs .thumb img.loaded', { timeout: 20000 });
    await p6.click('#post-publish');
    const myPost = p6.locator('.post', { hasText: postText });
    await myPost.waitFor();
    await myPost.locator('.post-img img.loaded').waitFor({ timeout: 20000 });
    const postId = await myPost.getAttribute('data-post');
    await p6.click('[data-like="' + postId + '"]');
    await p6.waitForSelector('[data-like="' + postId + '"].on >> text=1');
    await p6.click('[data-comments="' + postId + '"]');
    await p6.fill('[data-comment-input="' + postId + '"]', 'Комментарий из сценария');
    await p6.click('[data-comment-send="' + postId + '"]');
    await p6.waitForSelector('.comment >> text=Комментарий из сценария');
    ok('feed: a post with a picture, a like and a comment', true);
    await shot('web_12_feed', p6);
    // Elite things are locked without Elite
    await p6.click('#tab-profile');
    await p6.waitForSelector('[data-nick-style="aurora"].locked');
    await p6.click('[data-nick-style="aurora"]');
    await p6.waitForSelector('text=Нужна подписка Elite');
    await p6.click('#confirm-ok');
    await p6.waitForSelector('#buy-elite');
    // coins: the stub pays in test mode (PAYMENTS_TEST_MODE=on)
    await p6.click('[data-product="coins_100"]');
    await p6.click('#confirm-ok');
    await p6.waitForSelector('#coins-balance >> text=200');
    await p6.click('#buy-elite');
    await p6.click('#confirm-ok');
    await p6.waitForSelector('#elite-status');
    ok('coins and Elite bought through the payment stub (test mode)', (await p6.textContent('#coins-balance')).trim() === '500');
    await shot('web_13_coins', p6);
    await p6.goto(base + '/app/#/profile');
    await p6.waitForSelector('[data-nick-style="aurora"]:not(.locked)');
    await p6.click('[data-nick-style="aurora"]');
    await p6.waitForSelector('#profile-nick.nick-fx');
    await p6.click('[data-frame-opt="neon"]');
    await p6.waitForSelector('.profile-av-box .ring.spin');
    const look = await apiAs(el.token, '/v1/users/' + el.user.id);
    ok('Elite: a glowing nick and an animated frame, seen by others too', look.user.nick_style === 'aurora' && look.user.frame === 'neon' && look.user.elite);
    await shot('web_14_profile_looks', p6);
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
