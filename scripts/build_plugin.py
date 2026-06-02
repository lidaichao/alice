#!/usr/bin/env python3
"""Build Jira plugin JAR manually using javac + jar (no Maven needed)."""
import subprocess, os, shutil, zipfile

JDK = r"C:\tools\jdk11\jdk-11.0.31+11\bin"
JAVAC = os.path.join(JDK, "javac.exe")
JAR = os.path.join(JDK, "jar.exe")
SRC = r"H:\workbuddy\jira\jira-workbuddy-plugin\src"
BUILD = r"H:\workbuddy\jira\jira-workbuddy-plugin\build"
CLASSES = os.path.join(BUILD, "classes")
LOCAL_REPO = r"H:\workbuddy\jira\.m2\repository"
PROJECT = r"H:\workbuddy\jira\jira-workbuddy-plugin"

# Clean build dir
if os.path.exists(BUILD):
    shutil.rmtree(BUILD)
os.makedirs(CLASSES)

# Collect classpath from local repo
cp_jars = []
for root, dirs, files in os.walk(LOCAL_REPO):
    for f in files:
        if f.endswith('.jar'):
            cp_jars.append(os.path.join(root, f))

cp = ';'.join(cp_jars)
print(f"Classpath JARs: {len(cp_jars)}")

# Find Java source files
java_files = []
for root, dirs, files in os.walk(os.path.join(SRC, "main", "java")):
    for f in files:
        if f.endswith('.java'):
            java_files.append(os.path.join(root, f))

print(f"Java files: {len(java_files)}")
for f in java_files:
    print(f"  {os.path.basename(f)}")

# Compile
print("\n=== Compiling ===")
cmd = [JAVAC, "-encoding", "UTF-8", "-cp", cp, "-d", CLASSES] + java_files
result = subprocess.run(cmd, capture_output=True, timeout=30,
                       encoding='gbk', errors='replace')
if result.returncode != 0:
    print("COMPILE FAILED:")
    print(result.stdout)
    print(result.stderr)
    exit(1)
print("Compile OK")

# Create OSGi MANIFEST for plugins-version="2"
import_pkgs = (
    "com.atlassian.jira.component;resolution:=optional,"
    "com.atlassian.jira.config.properties;resolution:=optional,"
    "com.atlassian.jira.issue;resolution:=optional,"
    "com.atlassian.jira.issue.issuetype;resolution:=optional,"
    "com.atlassian.jira.issue.priority;resolution:=optional,"
    "com.atlassian.jira.issue.status;resolution:=optional,"
    "com.atlassian.jira.security;resolution:=optional,"
    "com.atlassian.jira.user;resolution:=optional,"
    "com.atlassian.sal.api.auth;resolution:=optional,"
    "com.atlassian.sal.api.pluginsettings;resolution:=optional,"
    "com.atlassian.sal.api.user;resolution:=optional,"
    "com.atlassian.templaterenderer;resolution:=optional,"
    "com.google.gson;resolution:=optional,"
    "javax.servlet;resolution:=optional,"
    "javax.servlet.http;resolution:=optional"
)

imp_line = "Import-Package: " + import_pkgs
wrapped = [imp_line[:70]]
remain = imp_line[70:]
while remain:
    wrapped.append(" " + remain[:69])
    remain = remain[69:]
import_str = "\n".join(wrapped)

# Full OSGi MANIFEST for plugins-version="2"
import_pkgs = (
    "com.atlassian.jira.component;resolution:=optional,"
    "com.atlassian.jira.config.properties;resolution:=optional,"
    "com.atlassian.jira.issue;resolution:=optional,"
    "com.atlassian.jira.issue.issuetype;resolution:=optional,"
    "com.atlassian.jira.issue.priority;resolution:=optional,"
    "com.atlassian.jira.issue.status;resolution:=optional,"
    "com.atlassian.jira.security;resolution:=optional,"
    "com.atlassian.jira.user;resolution:=optional,"
    "com.atlassian.sal.api.auth;resolution:=optional,"
    "com.atlassian.sal.api.pluginsettings;resolution:=optional,"
    "com.atlassian.sal.api.user;resolution:=optional,"
    "com.atlassian.templaterenderer;resolution:=optional,"
    "com.google.gson;resolution:=optional,"
    "javax.servlet;resolution:=optional,"
    "javax.servlet.http;resolution:=optional"
)

imp_line = "Import-Package: " + import_pkgs
wrapped = [imp_line[:70]]
remain = imp_line[70:]
while remain:
    wrapped.append(" " + remain[:69])
    remain = remain[69:]
import_str = "\n".join(wrapped)

manifest = f"""Manifest-Version: 1.0
Bundle-ManifestVersion: 2
Bundle-Name: WorkBuddy AI for Jira
Bundle-SymbolicName: com.lmd.workbuddy.jira-workbuddy-plugin
Bundle-Version: 1.0.0
Bundle-Description: AI-powered Jira assistant
Spring-Context: *
Atlassian-Plugin-Key: com.lmd.workbuddy.jira-workbuddy-plugin
{import_str}
Export-Package: com.lmd.workbuddy
Bundle-ClassPath: .,META-INF/lib/gson-2.10.1.jar
Require-Capability: osgi.ee;filter:="(&(osgi.ee=JavaSE)(version=1.8))"
"""

meta_dir = os.path.join(BUILD, "META-INF")
os.makedirs(meta_dir, exist_ok=True)
with open(os.path.join(meta_dir, "MANIFEST.MF"), "w") as f:
    f.write(manifest)

# Copy resources
for src_dir in ["css", "js"]:
    src_path = os.path.join(SRC, "main", "resources", src_dir)
    dst_path = os.path.join(BUILD, src_dir)
    if os.path.exists(src_path):
        shutil.copytree(src_path, dst_path)
        print(f"Copied {src_dir}: {len(os.listdir(dst_path))} files")

# Copy static/ (admin.html = test_suite.html)
static_src = os.path.join(SRC, "main", "resources", "static")
static_dst = os.path.join(BUILD, "static")
if os.path.exists(static_src):
    os.makedirs(static_dst, exist_ok=True)
    for f in os.listdir(static_src):
        shutil.copy2(os.path.join(static_src, f), os.path.join(static_dst, f))
    print(f"Copied static/: {len(os.listdir(static_dst))} files")

# Copy atlassian-plugin.xml
shutil.copy2(
    os.path.join(SRC, "main", "resources", "atlassian-plugin.xml"),
    BUILD
)
print("Copied atlassian-plugin.xml")

# Embed Gson JAR for runtime (OSGi doesn't always wire it)
gson_src = os.path.join(LOCAL_REPO, "com", "google", "code", "gson", "gson", "2.10.1", "gson-2.10.1.jar")
gson_dst = os.path.join(BUILD, "META-INF", "lib")
os.makedirs(gson_dst, exist_ok=True)
if os.path.exists(gson_src):
    shutil.copy2(gson_src, os.path.join(gson_dst, "gson-2.10.1.jar"))
    print("Embedded gson-2.10.1.jar")
classes_src = os.path.join(CLASSES, "com")
classes_dst = os.path.join(BUILD, "com")
if os.path.exists(classes_src):
    shutil.copytree(classes_src, classes_dst)
    print(f"Copied classes: {sum(1 for _ in os.walk(classes_dst))} dirs")

# Also copy to target/classes (webapp classpath — Jira loads from there!)
target_classes = os.path.join(PROJECT, "target", "classes")
os.makedirs(target_classes, exist_ok=True)
for root, dirs, files in os.walk(CLASSES):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), CLASSES)
        dst = os.path.join(target_classes, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(root, f), dst)
print("Synced to target/classes")

# Build JAR
print("\n=== Building JAR ===")
jar_path = os.path.join(PROJECT, "target", "jira-workbuddy-plugin-1.0.0.jar")
os.makedirs(os.path.dirname(jar_path), exist_ok=True)

# Use jar command
os.chdir(BUILD)
files_to_jar = ["com", "css", "js", "static", "META-INF", "atlassian-plugin.xml"]
existing = [f for f in files_to_jar if os.path.exists(f)]
print(f"Files to include: {existing}")

cmd = [JAR, "cfm", jar_path, os.path.join("META-INF", "MANIFEST.MF")] + existing
result = subprocess.run(cmd, capture_output=True, timeout=30,
                       encoding='gbk', errors='replace')
if result.returncode != 0:
    print("JAR BUILD FAILED:")
    print(result.stderr)
    exit(1)

# Verify
print(f"\n=== JAR Built: {os.path.getsize(jar_path)} bytes ===")

# Check contents
print("\nJAR contents:")
with zipfile.ZipFile(jar_path, 'r') as z:
    for name in z.namelist():
        print(f"  {name}")

print("\n=== MANIFEST ===")
with zipfile.ZipFile(jar_path, 'r') as z:
    with z.open('META-INF/MANIFEST.MF') as mf:
        print(mf.read().decode('utf-8'))

print("\n-- BUILD SUCCESS --")
