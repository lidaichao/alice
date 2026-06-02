# ═══════════════════════════════════════════════════
#  jira-workbuddy-plugin 工程配置中心
#  所有凭据/地址/端口统一管理，其他脚本从本文件导入
# ═══════════════════════════════════════════════════

# ── 生产服务器 ──
PROD_HOST = "192.168.8.34"
PROD_USER = "root"
PROD_PASS = "U2QqkUncZGCM"
PROD_JIRA_PORT = 8080
PROD_CONFLUENCE_PORT = 8090
PROD_FISHEYE_PORT = 8060

# ── Jira 服务器路径 ──
PROD_JIRA_HOME = "/data/jiradata"
PROD_JIRA_PLUGINS = "/data/jiradata/plugins/installed-plugins"
PROD_JIRA_BIN = "/data/jira"

# ── 本地 Jira 沙箱 ──
SANDBOX_JAVA_HOME = r"C:\tools\jdk11\jdk-11.0.31+11"
SANDBOX_TOMCAT = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\container\tomcat8x\apache-tomcat-8.5.6"
SANDBOX_JIRA_HOME = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\jira\home"
SANDBOX_JAR = r"H:\workbuddy\jira\jira-workbuddy-plugin\target\jira-workbuddy-plugin-1.0.0.jar"
SANDBOX_PORT = 8080
SANDBOX_ADMIN = "admin"
SANDBOX_PASS = "admin"

# ── Jira API ──
JIRA_BASE_URL = "http://ctjira1.lmdgame.com:8080"
JIRA_PAT = "NDAxMTQxMjkzNTgxOuZalJfcnLL7pSovrFXkMXj9/EGG"

# ── SVN ──
SVN_URL = "https://192.168.8.162/svn/captain_tsubasa_proj/branches/v3"
SVN_USER = "lidaichao"
SVN_PASS = "123456"

# ── AI Bridge (Python) ──
AI_BRIDGE_HOST = "localhost"
AI_BRIDGE_PORT = 9099
AI_BRIDGE_DIR = r"H:\workbuddy\jira\wecom-jira-bridge"

# ── DeepSeek AI ──
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = "sk-9879e6d86abf41c18d9148d2d7124d4d"
DEEPSEEK_MODEL = "deepseek-chat"

# ── Notion ──
NOTION_KEY = "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"

# ── Google Drive ──
GDRIVE_KEY = "AIzaSyAEDfaeKL4uBrIGEgBHmmG_Hc4TFbMUsUY"
GDRIVE_FOLDER = "1b7JJwDTGRV6EmVUieBOjnFcTXFtbCHiI"

# ── MCP Server ──
MCP_SERVER = r"H:\workbuddy\jira\wecom-jira-bridge\jira_mcp_server.py"

# ── 构建路径 ──
PLUGIN_SRC = r"H:\workbuddy\jira\jira-workbuddy-plugin"
PLUGIN_TARGET = r"H:\workbuddy\jira\jira-workbuddy-plugin\target"
LOCAL_M2_REPO = r"H:\workbuddy\jira\.m2\repository"
