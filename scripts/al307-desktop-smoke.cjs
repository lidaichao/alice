'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const puppeteer = require('puppeteer-core');

const ROOT = path.join(__dirname, '..');
const EVIDENCE = path.join(ROOT, 'docs', 'evidence', 'al307');
const SERVER_URL = process.env.BAIZE_DESKTOP_SERVER_URL || 'http://127.0.0.1:3000';
const USERNAME = `al307_${Date.now().toString(36)}`;
const PASSWORD = 'al307pass';
const ELECTRON = require('electron');
const MAIN = path.join(ROOT, 'client', 'desktop', 'main.cjs');
const DEBUG_PORT = 9223;

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function saveShot(page, name) {
  await page.screenshot({ path: path.join(EVIDENCE, name), fullPage: true });
}

async function main() {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  const hubSmoke = [];
  const registerRes = await fetch(`${SERVER_URL}/auth/register`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD, platform: 'windows', deviceId: 'al307-smoke' })
  });
  hubSmoke.push({ step: 'register', status: registerRes.status, body: await registerRes.json() });

  const loginRes = await fetch(`${SERVER_URL}/auth/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USERNAME, password: PASSWORD, platform: 'windows', deviceId: 'al307-smoke' })
  });
  const loginBody = await loginRes.json();
  hubSmoke.push({ step: 'login', status: loginRes.status, body: loginBody });

  const token = loginBody?.data?.token;
  const chatRes = await fetch(`${SERVER_URL}/chat`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` },
    body: JSON.stringify({ text: 'AL-307 smoke hello', platform: 'windows', clientId: 'al307-smoke' })
  });
  hubSmoke.push({ step: 'chat', status: chatRes.status, body: await chatRes.json() });
  fs.writeFileSync(path.join(EVIDENCE, 'hub-api-smoke.json'), JSON.stringify(hubSmoke, null, 2));

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
    await page.click('#authSwitch');
    await sleep(500);
    await page.type('#authUsername', USERNAME, { delay: 20 });
    await page.type('#authPassword', PASSWORD, { delay: 20 });
    await page.type('#authConfirmPassword', PASSWORD, { delay: 20 });
    await page.click('#authSubmit');
    await sleep(3000);
    await saveShot(page, '02-chat-shell.png');

    await page.waitForSelector('#chatInput', { timeout: 15000 });
    await page.evaluate(() => {
      const input = document.getElementById('chatInput');
      input.value = '你好';
      document.getElementById('chatForm').requestSubmit();
    });
    await sleep(8000);
    await saveShot(page, '03-ai-reply.png');

    await browser.disconnect();
  } finally {
    electron.kill();
  }

  console.log(JSON.stringify({ ok: true, evidence: EVIDENCE, username: USERNAME }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
