#!/usr/bin/env python3
"""Start Jira sandbox with visible output and log monitoring."""
import subprocess, os, shutil, time

BASE = r"H:\workbuddy\jira\jira-workbuddy-plugin\target"
TOMCAT = os.path.join(BASE, "container", "tomcat8x", "apache-tomcat-8.5.6")
CARGO_HOME = os.path.join(BASE, "container", "tomcat8x", "cargo-jira-home")
JIRA_HOME = os.path.join(BASE, "jira", "home")
WEBAPPS = os.path.join(TOMCAT, "webapps")
JDK = r"C:\tools\jdk11\jdk-11.0.31+11"
LOG = os.path.join(JIRA_HOME, "log", "atlassian-jira.log")
CATALINA = os.path.join(TOMCAT, "logs", "catalina.out")

# Clean and re-deploy WAR
root_dir = os.path.join(WEBAPPS, "ROOT")
root_war = os.path.join(WEBAPPS, "ROOT.war")
if os.path.exists(root_dir): shutil.rmtree(root_dir)
if os.path.exists(root_war): os.remove(root_war)

# Copy Jira WAR
JIRA_WAR = os.path.join(BASE, "jira", "jira.war")
shutil.copy2(JIRA_WAR, root_war)
print(f"WAR deployed ({os.path.getsize(root_war)} bytes)")

# Copy our plugin
PLUGIN_DIR = os.path.join(JIRA_HOME, "plugins", "installed-plugins")
os.makedirs(PLUGIN_DIR, exist_ok=True)
PLUGIN_JAR = os.path.join(BASE, "jira-workbuddy-plugin-1.0.0.jar")
shutil.copy2(PLUGIN_JAR, os.path.join(PLUGIN_DIR, os.path.basename(PLUGIN_JAR)))
print(f"Plugin deployed ({os.path.getsize(PLUGIN_JAR)} bytes)")

# 禁用 fastdev-plugin（Guava 版本冲突导致刷新时 Jira 500 错误）
FASTDEV = os.path.join(PLUGIN_DIR, "fastdev-plugin-2.6.jar")
FASTDEV_DISABLED = os.path.join(JIRA_HOME, "plugins", "disabled", "fastdev-plugin-2.6.jar")
if os.path.exists(FASTDEV):
    os.makedirs(os.path.dirname(FASTDEV_DISABLED), exist_ok=True)
    shutil.move(FASTDEV, FASTDEV_DISABLED)
    print(f"fastdev-plugin disabled (Guava conflict)")

# 推送静态文件到 Tomcat webapps（ChatDialogServlet 优先读文件系统）
STATIC_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jira-workbuddy-plugin", "build", "static")
STATIC_DST = os.path.join(TOMCAT, "webapps", "static")
if os.path.isdir(STATIC_SRC):
    os.makedirs(STATIC_DST, exist_ok=True)
    for fname in os.listdir(STATIC_SRC):
        shutil.copy2(os.path.join(STATIC_SRC, fname), os.path.join(STATIC_DST, fname))
    print(f"Static files pushed to Tomcat ({len(os.listdir(STATIC_DST))} files)")

# Set JNDI context
catalina_localhost = os.path.join(CARGO_HOME, "conf", "Catalina", "localhost")
os.makedirs(catalina_localhost, exist_ok=True)
db_url = f"jdbc:h2:file:{JIRA_HOME}\\database\\h2db;MODE=LEGACY;LOCK_TIMEOUT=30000"
root_xml = os.path.join(catalina_localhost, "ROOT.xml")
with open(root_xml, 'w') as f:
    f.write(f'<Context docBase="{WEBAPPS}\\ROOT" unpackWAR="true">\n')
    f.write(f'  <Resource name="jdbc/JiraDS" auth="Container" type="javax.sql.DataSource"\n')
    f.write(f'    driverClassName="org.h2.Driver"\n')
    f.write(f'    url="{db_url}"\n')
    f.write(f'    username="sa" password=""\n')
    f.write(f'    factory="org.apache.tomcat.dbcp.dbcp2.BasicDataSourceFactory"/>\n')
    f.write(f'</Context>\n')
print(f"JNDI context configured")

# Start Tomcat
env = os.environ.copy()
env["JAVA_HOME"] = JDK
env["JRE_HOME"] = JDK
java_opts = [
    f"-Djira.home={JIRA_HOME}",
    "-Datlassian.standalone=true",
    "-Datlassian.dev.mode=true",
    "-Djava.awt.headless=true",
    f"-Dcatalina.base={TOMCAT}",
    "-Xms1024m", "-Xmx2048m",
]
env["CATALINA_OPTS"] = " ".join(java_opts)
env["JAVA_OPTS"] = " ".join(java_opts)

startup = os.path.join(TOMCAT, "bin", "startup.bat")
print(f"\nStarting Tomcat...\n")

# Wait for previous log to settle
log_size_before = os.path.getsize(LOG) if os.path.exists(LOG) else 0

proc = subprocess.Popen(
    [startup], env=env, cwd=TOMCAT, shell=True,
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)

print("Tomcat started. Monitoring Jira log (sampling every 15s)\n")

# Monitor logs every 15s for up to 5 min
key_phrases = ["JIRA-Bootstrap", "ERROR", "ready", "plugin", "workbuddy", "RUNNING", "STARTING", "database", "locked"]
for i in range(20):
    time.sleep(15)
    
    # Check Jira log for new entries
    if os.path.exists(LOG):
        with open(LOG, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
            # Get only new content since last check
            new_lines = content[log_size_before:]
            log_size_before = len(content)
            
            if new_lines.strip():
                for line in new_lines.strip().split('\n'):
                    # Only show meaningful lines
                    for phrase in key_phrases:
                        if phrase.lower() in line.lower():
                            ts = line[:19] if len(line) > 19 else ""
                            msg = line[24:] if len(line) > 24 else line
                            print(f"  [{ts}] {msg[:120]}")
                            break
    
    # Check port + status
    try:
        import urllib.request, json
        r = urllib.request.urlopen('http://localhost:8080/status', timeout=5)
        status = json.loads(r.read())
        state = status.get('state', '?')
        print(f"\n  >>> Jira status: {state} (at {i*15}s)")
        if state in ('RUNNING', 'FIRST_RUN'):
            print("  ✅ JIRA IS UP!")
            break
    except Exception as e:
        if i % 2 == 0:
            print(f"  (Jira not responding yet at {i*15}s)")

print(f"\n--- Sandbox Info ---")
print(f"  http://localhost:8080")
print(f"  Plugin admin: http://localhost:8080/plugins/servlet/wb-admin")
print(f"  REST ping:    http://localhost:8080/rest/wb/1.0/chat/ping")
print(f"  Log:          {LOG}")
