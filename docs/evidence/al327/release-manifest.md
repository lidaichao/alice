# AL-327 release artifact (rebuild after Hub .31)

| Item | Value |
|------|-------|
| Local installer | `H:\workbuddy\aliceV2\dist\desktop\白泽.exe` |
| Release copy | `H:\workbuddy\aliceV2\releases\白泽 Setup.exe` |
| Size | 217,738,670 bytes (~207.6 MiB) |
| SHA256 | `60529A240286155A64F8E6FEF7A3E93E509120F4670D0A93102BB03BCD803649` |
| Default Hub (asar) | `http://192.168.72.31:5000` |
| Build | `npm run desktop:dist` (electron-builder NSIS) |
| Build date | 2026-06-29 20:51 |
| Prior build SHA256 | `10297C0E…820BC5` (pre-.31, superseded) |

## SCP target (AL-329)

- Remote: `alice@192.168.72.31:/tmp/alicev2-releases/白泽 Setup.exe`
- Attempt log: `docs/evidence/al327/scp-upload.log`
- asar check: `docs/evidence/al327/asar-hub-check.txt`
