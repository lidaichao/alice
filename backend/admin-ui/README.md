# Alice Admin UI (Element Plus)

Vue 3 + Element Plus 管理后台，构建产物输出到 `backend/static/admin/`。

## 开发

```bash
npm install
npm run dev
```

代理后端：`http://127.0.0.1:9099`

## 生产构建

```bash
npm run build
```

若本机无 npm，可用仓库自带脚本（仅需 Node.js）：

```bash
node scripts/build-with-node.mjs
```

## 访问

重启 `ai_bridge.py` 后打开：`http://127.0.0.1:9099/admin`

未构建时 Flask 会回退到旧版 `admin.html`。
