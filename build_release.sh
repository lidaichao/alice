#!/bin/bash
# ─────────────────────────────────────────────────────────
#  build_release.sh — Alice Jira AI 一键出鞘
#  编排: Backend(PyInstaller) → Frontend(Vite) → Desktop(electron-builder)
#  优先 macOS (darwin/arm64), 预留 Windows .bat
# ─────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "========================================"
echo "  Alice Jira AI — One-Click Release Build"
echo "========================================"
echo "  OS:    $(uname -s)"
echo "  Arch:  $(uname -m)"
echo "  Node:  $(node -v 2>/dev/null || echo 'not found')"
echo "  Python: $(python3 --version 2>/dev/null || echo 'not found')"
echo "========================================"
echo ""

# ── 前置检查 ───────────────────────────────────
check_deps() {
  local missing=()
  command -v node >/dev/null 2>&1 || missing+=("node")
  command -v python3 >/dev/null 2>&1 || missing+=("python3")
  if [ ${#missing[@]} -gt 0 ]; then
    echo "[ERR] Missing dependencies: ${missing[*]}"
    exit 1
  fi
}
check_deps

# ═══════════════════════════════════════════════════════
#  Step 1: Build Backend (PyInstaller)
# ═══════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [1/3] Building Python Backend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$ROOT_DIR/backend"

if [ ! -f "requirements.txt" ]; then
  echo "[WARN] requirements.txt not found, skipping pip install"
else
  echo "[1/3.1] Installing Python dependencies..."
  python3 -m pip install -r requirements.txt -q
fi

echo "[1/3.2] Running PyInstaller..."
python3 -m PyInstaller \
  --noconfirm \
  --onedir \
  --windowed \
  --name ai_bridge \
  --add-data "tools:tools" \
  --add-data "skills:skills" \
  --add-data "logic:logic" \
  --hidden-import flask \
  --hidden-import flask_cors \
  --hidden-import waitress \
  --hidden-import yaml \
  ai_bridge.py

if [ -f "dist/ai_bridge/ai_bridge" ] || [ -f "dist/ai_bridge/ai_bridge.exe" ]; then
  echo "[1/3] ✅ Backend build done"
else
  echo "[1/3] ⚠️ Backend build — binary not at expected path, check dist/"
fi

# ═══════════════════════════════════════════════════════
#  Step 2: Build Frontend (Vite)
# ═══════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [2/3] Building React Frontend"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$ROOT_DIR/frontend"

echo "[2/3.1] npm install..."
npm install --silent

echo "[2/3.2] npm run build (Vite)..."
npm run build

if [ -d "dist/index.html" ]; then
  echo "[2/3] ✅ Frontend build done"
else
  # Vite defaults to dist/
  if [ -f "dist/index.html" ]; then
    echo "[2/3] ✅ Frontend build done (dist/index.html)"
  else
    echo "[2/3] ⚠️ dist/index.html not found, check vite output"
  fi
fi

# ═══════════════════════════════════════════════════════
#  Step 3: Build Desktop (electron-builder)
# ═══════════════════════════════════════════════════════
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  [3/3] Building Electron Desktop"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd "$ROOT_DIR/desktop"

echo "[3/3.1] npm install..."
npm install --silent

echo "[3/3.2] electron-builder..."
if [[ "$(uname -s)" == "Darwin" ]]; then
  npm run dist:mac
else
  npm run dist:win
fi

# ── 最终汇总 ───────────────────────────────────
echo ""
echo "========================================"
echo "  Build Complete!"
echo "========================================"
echo "  Backend : $ROOT_DIR/backend/dist/ai_bridge/"
echo "  Frontend: $ROOT_DIR/frontend/dist/"
echo "  Desktop : $ROOT_DIR/desktop/dist/"
echo ""
echo "  Output files:"
ls -lh "$ROOT_DIR/desktop/dist/" 2>/dev/null || echo "  (run 'npm run dist:mac' or 'dist:win' manually)"
echo "========================================"
