# 改造 2 · 品牌移植（白泽→Alice）证据

**日期**: 2026-06-30  
**Epic**: AL-366 · AliceV2  
**经办**: 杰尼龟

## 改动文件清单（11 文件）

| 父任务 | 文件 | 改动 |
|--------|------|------|
| AL-367 | `baize/config/global.md` | 白泽→Alice · 删小泽/荒野乱斗/G:\Robot |
| AL-367 | `baize/logic/assertions/identity.md` | 白泽→Alice · 删小泽别名行 |
| AL-367 | `baize/logic/assertions/project.md` | 删荒野乱斗行 |
| AL-372 | `baize/config/agents/memory-officer.md` L3 | 白泽→Alice |
| AL-372 | `baize/config/agents/logic-officer.md` L3 | 白泽→Alice |
| AL-372 | `baize/config/agents/integration-officer.md` L9-L10 | 白泽→Alice |
| AL-376 | `baize/memory/shallow/project.md` | ~977 行→5 行模板 |
| AL-376 | `baize/memory/deep/indexes/` (6 files) | 全部删除 |
| AL-380 | `baize/config/client-version.yaml` L11-L12 | 白泽→Alice |
| AL-380 | `baize/config/client-version.example.yaml` L11-L12 | 白泽→Alice（连带修复） |
| AL-380 | `package.json` L5/38/43/66 | 4 处 白泽→Alice |
| AL-384 | `baize/config/jira.example.yaml` L13 | BAIZE→空 + 注释 |
| AL-386 | `baize/skills/wecom/skill.md` L8-L10 | 白泽→Alice |

## npm test

```
35 files · 418 passed · 0 FAIL · Duration 3.53s
```

## desktop:dist

```
file=dist/desktop/Alice.exe
size=217,738,606 bytes
```

## rg 扫描

`baize/config/ baize/logic/assertions/ baize/memory/ baize/skills/`  
`rg "白泽|小泽|荒野乱斗"` → **0 matches**

唯一残留：`baize/config/client-version.example.yaml` 已同步修复。
