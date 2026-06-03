#!/bin/bash
# ─────────────────────────────────────────────────────────
#  build_backend.sh — PyInstaller 编译 Python AI Bridge
#  适用: macOS/Linux (darwin/arm64 优先, 预留 Windows .bat)
# ─────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
OUTPUT_DIR="$BACKEND_DIR/dist"

echo "========================================"
echo "  Alice AI Bridge — Build Backend"
echo "========================================"
echo ""

# ── 环境检查 ───────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "[ERR] python3 not found. Please install Python 3.10+"
    exit 1
fi

if ! python3 -c "import PyInstaller" 2>/dev/null; then
    echo "[INFO] Installing PyInstaller..."
    python3 -m pip install pyinstaller
fi

# ── 添加隐式依赖 (dataclasses, os, re 等内置模块无需额外声明) ──
HIDDEN_IMPORTS=(
    "asyncio"
    "hashlib"
    "threading"
    "collections"
    "concurrent.futures"
    "json"
    "re"
    "logging"
    "logging.handlers"
    "yaml"
    "flask"
    "flask_cors"
    "waitress"
    "urllib"
    "http.client"
    "ssl"
    "subprocess"
    "tempfile"
    "base64"
)

HIDDEN_ARGS=""
for mod in "${HIDDEN_IMPORTS[@]}"; do
    HIDDEN_ARGS="$HIDDEN_ARGS --hidden-import=$mod"
done

# ── 编译 ──────────────────────────────────────
cd "$BACKEND_DIR"

echo "[1/2] Cleaning old builds..."
rm -rf dist build *.spec 2>/dev/null || true

echo "[2/2] PyInstaller compiling ai_bridge..."
python3 -m PyInstaller \
    --noconfirm \
    --onedir \
    --windowed \
    --name ai_bridge \
    --add-data "tools:tools" \
    --add-data "skills:skills" \
    --add-data "logic:logic" \
    --add-data "tests:tests" \
    --add-data "eval:eval" \
    --hidden-import flask \
    --hidden-import flask_cors \
    --hidden-import waitress \
    --hidden-import yaml \
    $HIDDEN_ARGS \
    ai_bridge.py

# ── 验证 ──────────────────────────────────────
if [ -f "dist/ai_bridge/ai_bridge" ] || [ -f "dist/ai_bridge/ai_bridge.exe" ]; then
    echo ""
    echo "✅ Build successful: $BACKEND_DIR/dist/ai_bridge/"
    ls -lh dist/ai_bridge/ | head -10
else
    echo ""
    echo "[WARN] Binary not found at expected path, checking dist/..."
    ls -la dist/
fi
