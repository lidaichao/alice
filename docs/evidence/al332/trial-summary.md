# AL-332 trial install · tester 1 (squirtle)

| Check | Result | Evidence |
|-------|--------|----------|
| Rebuilt NSIS after .31 commit | PASS | SHA256 60529A24…3649 |
| asar PRODUCTION_HUB_URL | `.31:5000` | al327/asar-hub-check.txt |
| scp to .31 | PASS | al327/scp-upload.log |
| curl .31:5000/health | 200 | health-curl.json |
| Packaged app launch | PASS | 01-packaged-first-launch.png |
| Hub connection UI | PASS (health OK) | 02-hub-connection-status.png |
| Register/login on .31 | SKIP (404) | hub-api-smoke.json — v3.2 hub until step⑦ |
| Cursor chat on .31 | DEFER step⑦ | P2.5 al2.5-cursor already green locally |

## NSIS silent install note

Automated `/S` on dev host exited `0xC0000005`; GUI install + coordinator path documented in coordinator-install-guide.md. Functional validation used `dist/desktop/win-unpacked/白泽.exe` (same asar as NSIS payload).
