'use strict';

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const puppeteer = require('puppeteer-core');

const ROOT = path.join(__dirname, '..');
const EVIDENCE = path.join(ROOT, 'docs', 'evidence', 'al332');
const SERVER_URL = 'http://192.168.72.31:5000';
const PACKAGED_EXE = path.join(ROOT, 'dist', 'desktop', 'win-unpacked', '白泽.exe');
const DEBUG_PORT = 9225;

async function sleep(ms) {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

async function saveShot(page, name) {
  await page.screenshot({ path: path.join(EVIDENCE, name), fullPage: true });
}

async function probe(url, init) {
  const response = await fetch(url, init);
  const text = await response.text();
  let body = text;
  try {
    body = JSON.parse(text);
  } catch {
    body = text.slice(0, 500);
  }
  return { status: response.status, body };
}

async function main() {
  fs.mkdirSync(EVIDENCE, { recursive: true });

  const hubSmoke = [];
  hubSmoke.push({ step: 'health', url: `${SERVER_URL}/health`, ...(await probe(`${SERVER_URL}/health`)) });
  hubSmoke.push({
    step: 'auth_register_probe',
    url: `${SERVER_URL}/auth/register`,
    ...(await probe(`${SERVER_URL}/auth/register`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username: 'probe', password: 'probe', platform: 'windows', deviceId: 'al332-probe' })
    }))
  });
  fs.writeFileSync(path.join(EVIDENCE, 'hub-api-smoke.json'), JSON.stringify(hubSmoke, null, 2));
  fs.writeFileSync(path.join(EVIDENCE, 'health-curl.json'), JSON.stringify(hubSmoke[0].body, null, 2));

  if (hubSmoke[0].status !== 200) {
    throw new Error(`health expected 200, got ${hubSmoke[0].status}`);
  }

  const electron = spawn(PACKAGED_EXE, [`--remote-debugging-port=${DEBUG_PORT}`], {
    cwd: path.dirname(PACKAGED_EXE),
    env: { ...process.env },
    stdio: 'ignore',
    windowsHide: false
  });

  try {
    await sleep(7000);
    const browser = await puppeteer.connect({
      browserURL: `http://127.0.0.1:${DEBUG_PORT}`,
      defaultViewport: { width: 1100, height: 760 }
    });
    const pages = await browser.pages();
    const page = pages[0] || (await browser.newPage());
    await sleep(2000);
    await saveShot(page, '01-packaged-first-launch.png');

    const connectionText = await page.$eval('#connectionStatus', (node) => node.textContent || '').catch(() => 'unknown');
    fs.writeFileSync(
      path.join(EVIDENCE, 'connection-status.txt'),
      [
        `connectionStatus=${connectionText}`,
        `defaultHub=${SERVER_URL}`,
        `packagedExe=${PACKAGED_EXE}`,
        `authRegister=${hubSmoke[1].status}`,
        'note=Production .31 still runs v3.2 ai-bridge; Baize /auth/* available after step⑦ Node Hub deploy.'
      ].join('\n')
    );

    await saveShot(page, '02-hub-connection-status.png');
    await browser.disconnect();
  } finally {
    electron.kill();
  }

  console.log(JSON.stringify({ ok: true, evidence: EVIDENCE, health: hubSmoke[0].status, authRegister: hubSmoke[1].status }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
