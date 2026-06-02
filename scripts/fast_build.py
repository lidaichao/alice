#!/usr/bin/env python3
"""
WorkBuddy Jira 插件 — 本地极速热部署 (OSGi Hot Deploy + 文件系统推送)
_____________________________________________________
用法: python fast_build.py
原理: 编译 → JAR + 静态文件推送 → 3-5s 生效
_____________________________________________________
"""
import os, shutil, subprocess, time, sys

# ═══ 路径配置 ═══
BUILD_SCRIPT    = r"H:\workbuddy\jira\build_plugin.py"
SOURCE_JAR      = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\jira-workbuddy-plugin-1.0.0.jar"
DEST_DIR        = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\jira\home\plugins\installed-plugins"
DEST_JAR        = os.path.join(DEST_DIR, "jira-workbuddy-plugin-1.0.0.jar")
PYTHON          = r"C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
OSGI_CACHE      = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\jira\home\plugins\.osgi-plugins"
# ChatDialogServlet 热部署路径：catalina.base/webapps/static/
TOMCAT_STATIC   = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\container\tomcat8x\apache-tomcat-8.5.6\webapps\static"
BUILD_STATIC    = r"H:\workbuddy\jira\jira-workbuddy-plugin\build\static"
SRC_STATIC      = r"H:\workbuddy\jira\jira-workbuddy-plugin\src\main\resources\static"

def main():
    t0 = time.time()

    # ── 0. 自动存档（有改动就提交，形成回退节点） ──
    print("💾 [0/4] Git 自动存档...")
    r = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, cwd=os.path.dirname(os.path.abspath(__file__)))
    if r.stdout.strip():
        subprocess.run(["git", "add", "-A"], capture_output=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        ts = time.strftime("%Y-%m-%d %H:%M")
        subprocess.run(["git", "commit", "-m", f"deploy: {ts}"], capture_output=True, cwd=os.path.dirname(os.path.abspath(__file__)))
        print(f"   ✅ 已存档 ({ts})")
    else:
        print(f"   ℹ️  无改动，跳过")

    # ── 1. 构建 ──
    print("🚀 [1/4] 编译打包 (javac + jar)...")
    r = subprocess.run([PYTHON, BUILD_SCRIPT], capture_output=True, text=True, timeout=30)
    if "BUILD SUCCESS" not in r.stdout:
        print("❌ 编译失败:")
        print(r.stdout[-500:])
        print(r.stderr[-500:])
        return False
    print(f"   ✅ 编译成功 ({os.path.getsize(SOURCE_JAR)} bytes)")

    # ── 2. 热部署 JAR ──
    print("📦 [2/4] 注入 JAR 到沙箱...")
    os.makedirs(DEST_DIR, exist_ok=True)

    # 尝试清除 OSGi 缓存（可能被 Jira 进程锁定，失败则跳过）
    if os.path.exists(OSGI_CACHE):
        try:
            def _on_rm_error(func, path, exc_info):
                pass
            shutil.rmtree(OSGI_CACHE, onexc=_on_rm_error)
            print(f"   🧹 OSGi cache 已清除")
        except Exception:
            print(f"   ⚠️  OSGi cache 部分被锁定，跳过清理")

    shutil.copy2(SOURCE_JAR, DEST_JAR)
    t_now = time.time()
    os.utime(DEST_JAR, (t_now + 120, t_now + 120))
    time.sleep(0.1)
    os.utime(DEST_JAR, None)

    # ── 3. 静态文件直推（绕过 OSGi classloader 缓存） ──
    print("📄 [3/4] 推送静态文件到 Tomcat...")
    os.makedirs(TOMCAT_STATIC, exist_ok=True)

    # 优先用 build 目录（编译产出），回退到 src 目录
    static_src = BUILD_STATIC if os.path.isdir(BUILD_STATIC) else SRC_STATIC
    for fname in os.listdir(static_src):
        src_file = os.path.join(static_src, fname)
        dst_file = os.path.join(TOMCAT_STATIC, fname)
        if os.path.isfile(src_file):
            shutil.copy2(src_file, dst_file)
            print(f"   ✅ {fname} ({os.path.getsize(dst_file)} bytes)")

    elapsed = round(time.time() - t0, 1)
    print(f"✅ [4/4] 完成 ({elapsed}s)")
    print(f"\n⏳ Ctrl+Shift+R 强制刷新浏览器即可看到更新。")
    print(f"   http://localhost:8080/plugins/servlet/wb-admin")
    return True

if __name__ == "__main__":
    main()
