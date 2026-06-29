'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const puppeteer = require('puppeteer-core');

const ROOT = path.join(__dirname, '..');
const EVIDENCE = path.join(ROOT, 'docs', 'evidence', 'al2.5-cursor');
const SERVER_URL = process.env.BAIZE_DESKTOP_SERVER_URL || 'http://127.0.0.1:3000';
const USERNAME = `al364_${Date.now().toString(36)}`;
const PASSWORD = 'al364pass';
const ELECTRON = require('electron');
const MAIN = path.join(ROOT, 'client', 'desktop', 'main.cjs');
const DEBUG_PORT = 9224;
const CHAT_MESSAGE = '请用一句话介绍白泽是什么，不要提 Jira 或工程任务。';

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function saveShot(page, name) {
  await page.screenshot({ path: path.join(EVIDENCE, name), fullPage: true });
}

async function main() {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  const hubSmoke = [];
  const healthRes = await fetch(`${SERVER_URL}/health`);
  hubSmoke.push({ step: 'health', status: healthRes.status, body: await healthRes.json() });

  const registerRes = await fetch(`${SERVER_URL}/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD, platform: 'windows', deviceId: 'al364-smoke' })
  });
  hubSmoke.push({ step: 'register', status: registerRes.status, body: await registerRes.json() });

  const loginRes = await fetch(`${SERVER_URL}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD, platform: 'windows', deviceId: 'al364-smoke' })
  });
  const loginBody = await loginRes.json();
  hubSmoke.push({ step: 'login', status: loginRes.status, body: loginBody });

  const token = loginBody?.data?.token;
  const chatRes = await fetch(`${SERVER_URL}/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ text: CHAT_MESSAGE, platform: 'windows', clientId: 'al364-smoke' })
  });
  const chatBody = await chatRes.json();
  hubSmoke.push({ step: 'chat', status: chatRes.status, body: chatBody });
  fs.writeFileSync(path.join(EVIDENCE, 'hub-api-smoke.json'), JSON.stringify(hubSmoke, null, 2));

  if (chatRes.status !== 200 || chatBody?.data?.provider !== 'cursor') {
    throw new Error(`Expected cursor provider chat, got status=${chatRes.status} provider=${chatBody?.data?.provider}`);
  }

  const electron = spawn(ELECTRON, [MAIN, `--remote-debugging-port=${DEBUG_PORT}`], {
    cwd: ROOT,
    env: { ...process.env, BAIZE_DESKTOP_SERVER_URL: SERVER_URL },
    stdio: 'ignore',
    windowsHide: false
  });

  try {
    await sleep(5000);
    const browser = await puppeteer.connect({
      browserURL: `http://127.0.0.1:${DEBUG_PORT}`,
      defaultViewport: { width: 1100, height: 760 }
    });
    const pages = await browser.pages();
    const page = pages[0] || (await browser.newPage());

    await sleep(2000);
    await saveShot(page, '01-login.png');

    await page.waitForSelector('#authUsername', { timeout: 15000 });
    await page.type('#authUsername', USERNAME, { delay: 20 });
    await page.type('#authPassword', PASSWORD, { delay: 20 });
    await page.click('#authSubmit');
    await sleep(3000);
    await saveShot(page, '02-chat-shell.png');

    await page.waitForSelector('#chatInput', { timeout: 15000 });
    await page.evaluate((message) => {
      const input = document.getElementById('chatInput');
      input.value = message;
      document.getElementById('chatForm').requestSubmit();
    }, CHAT_MESSAGE);
    await sleep(45000);
    await saveShot(page, '03-cursor-reply.png');

    const transcript = await page.evaluate(() => {
      const items = Array.from(document.querySelectorAll('.chat-message, [data-role="message"], .message'));
      return items.map((node) => node.textContent || '').filter(Boolean);
    });
    fs.writeFileSync(path.join(EVIDENCE, 'desktop-transcript.json'), JSON.stringify(transcript, null, 2));

    await browser.disconnect();
  } finally {
    electron.kill();
  }

  console.log(JSON.stringify({
    ok: true,
    evidence: EVIDENCE,
    username: USERNAME,
    provider: chatBody?.data?.provider,
    replyPreview: String(chatBody?.data?.reply || '').slice(0, 120)
  }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
