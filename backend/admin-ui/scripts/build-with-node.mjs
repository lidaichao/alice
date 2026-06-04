/**
 * Bootstrap npm from registry and run production build (no system npm required).
 * Usage: node scripts/build-with-node.mjs
 */
import { execSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, '..');
const tools = path.join(root, '.tools');
const npmTgz = path.join(tools, 'npm.tgz');
const npmPkg = path.join(tools, 'package');

fs.mkdirSync(tools, { recursive: true });

if (!fs.existsSync(path.join(npmPkg, 'bin', 'npm-cli.js'))) {
  console.log('Downloading npm...');
  const res = await fetch('https://registry.npmjs.org/npm/-/npm-10.9.2.tgz');
  if (!res.ok) throw new Error(`npm download failed: ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  fs.writeFileSync(npmTgz, buf);
  console.log('Extracting npm...');
  execSync(`tar -xzf "${npmTgz}" -C "${tools}"`, { stdio: 'inherit', shell: true });
}

const npmCli = path.join(npmPkg, 'bin', 'npm-cli.js');
const node = process.execPath;

console.log('npm install...');
execSync(`"${node}" "${npmCli}" install`, { cwd: root, stdio: 'inherit', shell: true });

console.log('npm run build...');
execSync(`"${node}" "${npmCli}" run build`, { cwd: root, stdio: 'inherit', shell: true });

console.log('Admin UI build complete -> ../static/admin');
