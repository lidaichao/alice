package com.lmd.workbuddy;

import com.atlassian.jira.component.ComponentAccessor;
import com.atlassian.sal.api.auth.LoginUriProvider;
import com.atlassian.sal.api.user.UserManager;
import com.google.gson.*;
import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.stream.Collectors;

/**
 * AdminServlet — 配置管理页 + API 端点
 * 
 * HTML 由 static/admin.html（= test_suite.html）提供，不做任何手写。
 * 后端只负责：鉴权 + save + test + proxy 转发。
 */
public class AdminServlet extends HttpServlet {
    private UserManager userManager;
    private LoginUriProvider loginUriProvider;
    private Gson gson = new Gson();

    @Override
    public void init() throws ServletException {
        super.init();
        this.userManager = ComponentAccessor.getOSGiComponentInstanceOfType(UserManager.class);
        this.loginUriProvider = ComponentAccessor.getOSGiComponentInstanceOfType(LoginUriProvider.class);
    }

    // ═══ Routing ═══════════════════════════════════════════
    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        if (!checkAdmin(req, resp)) return;
        String action = req.getParameter("action");
        if ("test".equals(action))      { handleTest(req, resp); return; }
        if ("proxy".equals(action))     { handleProxy(req, resp); return; }
        serveStaticHtml(resp);
    }

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        if (!checkAdmin(req, resp)) return;
        String action = req.getParameter("action");
        if ("save".equals(action))      { handleSave(req, resp); return; }
        if ("test".equals(action))      { handleTest(req, resp); return; }
        if ("proxy".equals(action))     { handleProxy(req, resp); return; }
        serveStaticHtml(resp);
    }

    // ═══ Static HTML ════════════════════════════════════════
    private void serveStaticHtml(HttpServletResponse resp) throws IOException {
        resp.setContentType("text/html;charset=UTF-8");
        resp.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        byte[] bytes = null;

        // 优先从文件系统读取（热部署路径）
        try {
            File f = new File(System.getProperty("catalina.base"),
                "webapps/static/admin.html");
            if (f.exists()) {
                bytes = Files.readAllBytes(f.toPath());
            }
        } catch (Exception e) { /* fallback */ }

        // 回退到 classpath（OSGi bundle 资源）
        if (bytes == null) {
            try (InputStream is = getClass().getClassLoader().getResourceAsStream("static/admin.html")) {
                if (is != null) {
                    bytes = is.readAllBytes();
                }
            }
        }

        if (bytes == null) {
            resp.getWriter().write("<h1>admin.html not found</h1>");
            return;
        }
        resp.getWriter().write(new String(bytes, StandardCharsets.UTF_8));
    }

    // ═══ Save ═══════════════════════════════════════════════
    private void handleSave(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        saveIf("svn.url", req.getParameter("svn_url"));
        saveIf("svn.user", req.getParameter("svn_user"));
        saveIf("svn.pass", req.getParameter("svn_pass"));
        saveIf("fisheye.url", req.getParameter("fs_url"));
        saveMasked("notion.key", req.getParameter("notion_key"), ConfigService.getNotionKey());
        saveIf("notion.db", req.getParameter("notion_db"));
        saveMasked("gdrive.key", req.getParameter("gdrive_key"), ConfigService.getGDriveKey());
        saveIf("gdrive.folders", req.getParameter("gdrive_folders"));
        saveIf("ai.url", req.getParameter("ai_url"));
        saveIf("ai.model", req.getParameter("ai_model"));
        saveMasked("ai.key", req.getParameter("ai_key"), ConfigService.getAiKey());
        saveIf("ai.max_tokens", req.getParameter("ai_max_tokens"));
        saveIf("ai.temp", req.getParameter("ai_temp"));
        saveIf("proxy.ip", req.getParameter("proxy_ip"));
        saveIf("proxy.port", req.getParameter("proxy_port"));
        saveIf("roles.config", req.getParameter("roles_config"));
        saveIf("quick.config", req.getParameter("quick_config"));
        saveIf("bridge.url", req.getParameter("bridge_url"));
        resp.setContentType("application/json;charset=UTF-8");
        resp.getWriter().write("{\"ok\":true}");
    }

    // ═══ Test ═══════════════════════════════════════════════
    private void handleTest(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        resp.setContentType("application/json;charset=UTF-8");
        PrintWriter w = resp.getWriter();
        String type = req.getParameter("type");

        try {
            // SVN — config already saved, just acknowledge
            if ("svn".equals(type)) { w.write("{\"ok\":true,\"msg\":\"SVN 配置已保存\"}"); return; }

            // Notion connection test
            if ("notion".equals(type)) {
                String nk = nvl(req.getParameter("notion_key"), ConfigService.getNotionKey());
                if (nk == null || nk.isEmpty()) { w.write(jsonErr("请先填写 Notion API Key")); return; }
                try {
                    String nr = httpGet("https://api.notion.com/v1/users/me", nk, 10000);
                    JsonObject robj = gson.fromJson(nr, JsonObject.class);
                    if (robj.has("type")) {
                        String name = robj.has("name") ? robj.get("name").getAsString() : robj.get("type").getAsString();
                        w.write(jsonOk("已连接: " + name));
                    } else if (robj.has("message")) {
                        w.write(jsonErr(robj.get("message").getAsString()));
                    } else {
                        w.write(jsonErr("Unknown response"));
                    }
                } catch (Exception e) { w.write(jsonErr(e.getMessage())); }
                return;
            }

            // Notion auto-detect databases
            if ("notion_auto".equals(type)) {
                String nk = nvl(req.getParameter("notion_key"), ConfigService.getNotionKey());
                if (nk == null || nk.isEmpty()) { w.write(jsonErr("请先填写 Notion API Key")); return; }
                try {
                    String body = "{\"page_size\":20}";
                    String sr = httpPostJson("https://api.notion.com/v1/search", body, nk, 15000);
                    JsonObject srobj = gson.fromJson(sr, JsonObject.class);
                    if (srobj.has("message")) { w.write(jsonErr(srobj.get("message").getAsString())); return; }
                    JsonArray results = srobj.getAsJsonArray("results");
                    StringBuilder sb = new StringBuilder("[");
                    int count = 0;
                    for (int i = 0; i < results.size(); i++) {
                        JsonObject obj = results.get(i).getAsJsonObject();
                        if (!"database".equals(obj.has("object") ? obj.get("object").getAsString() : "")) continue;
                        String title = "";
                        if (obj.has("title")) {
                            JsonArray ta = obj.getAsJsonArray("title");
                            if (ta.size() > 0 && ta.get(0).getAsJsonObject().has("plain_text"))
                                title = ta.get(0).getAsJsonObject().get("plain_text").getAsString();
                        }
                        if (count > 0) sb.append(",");
                        sb.append("{\"id\":\"").append(obj.get("id").getAsString()).append("\",\"title\":\"").append(esc(title)).append("\"}");
                        count++;
                    }
                    sb.append("]");
                    w.write(sb.toString());
                } catch (Exception e) { w.write(jsonErr(e.getMessage())); }
                return;
            }

            // Google Drive test — forward to AI Bridge (better proxy support)
            if ("gdrive".equals(type)) {
                try {
                    String pr = httpGetRaw(ConfigService.getBridgeUrlOrDefault() + "/proxy/gdrive/list", 15000);
                    if (pr.contains("kind") || pr.contains("ok")) { w.write(jsonOk("连接成功")); }
                    else { w.write(jsonErr(pr.length() > 100 ? pr.substring(0, 100) : pr)); }
                } catch (SocketTimeoutException e) { w.write(jsonErr("连接超时（需要代理: 填写代理 IP 和端口）")); }
                catch (Exception e) { w.write(jsonErr(e.getMessage())); }
                return;
            }

            // AI connection test
            if ("ai".equals(type)) {
                String aiUrl = nvl(req.getParameter("ai_url"), ConfigService.getAiUrl());
                if (aiUrl == null || aiUrl.isEmpty()) aiUrl = "https://api.deepseek.com/v1/chat/completions";
                String aiKey = nvl(req.getParameter("ai_key"), ConfigService.getAiKey());
                if (aiKey != null && aiKey.contains("\u2022\u2022\u2022\u2022")) aiKey = ConfigService.getAiKey();
                if (aiKey == null || aiKey.isEmpty()) { w.write(jsonErr("请先填写 AI API Key")); return; }
                try {
                    String testBody = "{\"model\":\"deepseek-chat\",\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"max_tokens\":5}";
                    String mr = httpPostJson(aiUrl, testBody, aiKey, 20000);
                    if (mr.contains("choices")) { w.write(jsonOk("连接成功")); }
                    else { w.write(jsonErr("响应异常: " + mr.substring(0, 120))); }
                } catch (Exception e) { w.write(jsonErr(e.getMessage())); }
                return;
            }

            // AI model list
            if ("ai_models".equals(type)) {
                w.write("[\"deepseek-chat\"]");
                return;
            }

            // Local IP detection
            if ("local_ip".equals(type)) {
                try {
                    w.write("{\"ip\":\"" + InetAddress.getLocalHost().getHostAddress() + "\"}");
                } catch (Exception e) {
                    w.write("{\"ip\":\"127.0.0.1\"}");
                }
                return;
            }

            w.write("{}");
        } catch (Exception e) {
            w.write(jsonErr(e.getMessage()));
        }
    }

    // ═══ Proxy (forward to AI Bridge on localhost:9099) ═════
    private void handleProxy(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        resp.setContentType("application/json;charset=UTF-8");
        String path = req.getParameter("path");
        if (path == null || path.isEmpty()) { resp.getWriter().write("{\"error\":\"Missing path\"}"); return; }

        // Read request body if POST
        String body = null;
        if ("POST".equalsIgnoreCase(req.getMethod())) {
            body = req.getReader().lines().collect(Collectors.joining());
        }

        // Forward to AI Bridge
        try {
            String targetUrl = ConfigService.getBridgeUrlOrDefault() + path;
            String result;
            if (body != null && !body.isEmpty()) {
                result = httpPostRaw(targetUrl, body, 30000);
            } else {
                result = httpGetRaw(targetUrl, 15000);
            }
            resp.getWriter().write(result);
        } catch (Exception e) {
            resp.getWriter().write("{\"error\":\"" + esc(e.getMessage()) + "\"}");
        }
    }

    // ═══ Auth ═══════════════════════════════════════════════
    private boolean checkAdmin(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        String u = userManager.getRemoteUsername(req);
        if (u == null || !userManager.isAdmin(u)) {
            resp.sendRedirect(loginUriProvider.getLoginUri(URI.create("/plugins/servlet/wb-admin")).toASCIIString());
            return false;
        }
        return true;
    }

    // ═══ Config helpers ══════════════════════════════════════
    private void saveIf(String key, String val) { if (val != null) ConfigService.set(key, val); }
    private void saveMasked(String key, String val, String old) {
        if (val != null && !val.isEmpty() && !val.equals(mask(old))) ConfigService.set(key, val);
    }
    private String mask(String s) { return (s != null && s.length() > 8) ? s.substring(0,4) + "\u2022\u2022\u2022\u2022" + s.substring(s.length()-4) : ""; }
    private String nvl(String a, String b) { return (a != null && !a.isEmpty()) ? a : b; }

    // ═══ JSON helpers ════════════════════════════════════════
    private String jsonOk(String msg) { return "{\"ok\":true,\"msg\":\"" + esc(msg) + "\"}"; }
    private String jsonErr(String msg) { return "{\"ok\":false,\"msg\":\"" + esc(msg) + "\"}"; }
    private String esc(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n").replace("\r", "");
    }

    // ═══ HTTP ════════════════════════════════════════════════
    private java.net.Proxy getProxy() {
        String ip = ConfigService.get("proxy.ip");
        String port = ConfigService.get("proxy.port");
        if (ip != null && !ip.isEmpty() && port != null && !port.isEmpty())
            try { return new java.net.Proxy(java.net.Proxy.Type.HTTP, new InetSocketAddress(ip, Integer.parseInt(port))); } catch (Exception e) {}
        return java.net.Proxy.NO_PROXY;
    }

    private String httpGet(String u, String auth, int t) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection(getProxy());
        c.setConnectTimeout(t); c.setReadTimeout(t);
        if (auth != null) {
            c.setRequestProperty("Authorization", "Bearer " + auth);
            c.setRequestProperty("Notion-Version", "2022-06-28");
        }
        try (InputStream is = c.getInputStream()) { return new String(is.readAllBytes(), StandardCharsets.UTF_8); }
    }

    private String httpPostJson(String u, String body, String auth, int t) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection(getProxy());
        c.setRequestMethod("POST"); c.setDoOutput(true);
        c.setConnectTimeout(t); c.setReadTimeout(t);
        c.setRequestProperty("Content-Type", "application/json");
        if (auth != null) {
            c.setRequestProperty("Authorization", "Bearer " + auth);
            c.setRequestProperty("Notion-Version", "2022-06-28");
        }
        try (OutputStream os = c.getOutputStream()) { os.write(body.getBytes(StandardCharsets.UTF_8)); }
        try (InputStream is = c.getInputStream()) { return new String(is.readAllBytes(), StandardCharsets.UTF_8); }
    }

    private String httpGetRaw(String u, int t) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
        c.setConnectTimeout(t); c.setReadTimeout(t);
        try (InputStream is = c.getInputStream()) { return new String(is.readAllBytes(), StandardCharsets.UTF_8); }
    }

    private String httpPostRaw(String u, String body, int t) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(u).openConnection();
        c.setRequestMethod("POST"); c.setDoOutput(true);
        c.setConnectTimeout(t); c.setReadTimeout(t);
        c.setRequestProperty("Content-Type", "application/json");
        try (OutputStream os = c.getOutputStream()) { os.write(body.getBytes(StandardCharsets.UTF_8)); }
        try (InputStream is = c.getInputStream()) { return new String(is.readAllBytes(), StandardCharsets.UTF_8); }
    }
}
