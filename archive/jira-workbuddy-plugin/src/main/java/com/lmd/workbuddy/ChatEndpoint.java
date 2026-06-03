package com.lmd.workbuddy;

import com.google.gson.*;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * ChatEndpoint — AI 对话端点 (纯透传网关 + SSE 流式)
 * Java 层只做字节流搬运工，零 JSON 解析，零业务逻辑。
 */
public class ChatEndpoint extends HttpServlet {

    @Override
    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        // SSE 流式响应，不是普通 JSON
        resp.setContentType("text/event-stream");
        resp.setCharacterEncoding("UTF-8");
        resp.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");
        resp.setHeader("X-Accel-Buffering", "no");  // 禁用 nginx 代理缓冲
        resp.setHeader("Connection", "keep-alive");
        resp.setBufferSize(0);  // 禁用 Servlet 容器输出缓冲

        Gson gson = new Gson();
        JsonObject jsonReq;
        try {
            jsonReq = gson.fromJson(readBody(req), JsonObject.class);
        } catch (Exception e) {
            resp.getWriter().write("data: {\"error\": \"Invalid JSON\"}\n\n");
            return;
        }

        // 构建发给 AI Bridge 的配置
        JsonObject configObj = new JsonObject();
        safePut(configObj, "notion_key", ConfigService.getNotionKey());
        safePut(configObj, "notion_db", ConfigService.getNotionDb());
        safePut(configObj, "gdrive_key", ConfigService.getGDriveKey());
        safePut(configObj, "gdrive_folders", ConfigService.getGDriveFolders());

        // 注入当前 Jira 用户身份（用作缓存隔离 + 审计）
        String username = req.getRemoteUser();
        if (username != null && !username.isEmpty()) {
            configObj.addProperty("_wbUser", username);
        }

        String pip = ConfigService.get("proxy.ip");
        String pport = ConfigService.get("proxy.port");
        if (pip != null && !pip.isEmpty() && pport != null && !pport.isEmpty()) {
            configObj.addProperty("proxy", "http://" + pip + ":" + pport);
        }
        jsonReq.add("config", configObj);

        // 透传到 AI Bridge
        String bridgeUrl = ConfigService.getBridgeUrlOrDefault() + "/v1/chat/completions";

        try {
            // 先发一条 SSE 注释，让前端立即感知连接建立
            OutputStream clientOs = resp.getOutputStream();
            clientOs.write(":connected\n\n".getBytes(StandardCharsets.UTF_8));
            clientOs.flush();

            HttpURLConnection c = (HttpURLConnection) new URL(bridgeUrl).openConnection();
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setConnectTimeout(5000);
            c.setReadTimeout(300000);  // 5 分钟超时：AI 推理可能较慢
            c.setRequestProperty("Content-Type", "application/json");

            // 写入请求体
            try (OutputStream os = c.getOutputStream()) {
                os.write(jsonReq.toString().getBytes(StandardCharsets.UTF_8));
            }

            // 核心：纯字节流搬运，读到什么立刻 flush 给前端
            try (InputStream is = c.getInputStream()) {
                byte[] buffer = new byte[1024];
                int bytesRead;
                while ((bytesRead = is.read(buffer)) != -1) {
                    clientOs.write(buffer, 0, bytesRead);
                    clientOs.flush();
                }
            }
        } catch (Exception e) {
            resp.getWriter().write("data: {\"error\": \"AI 桥接服务断开\"}\n\n");
        }
    }

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        resp.setContentType("application/json;charset=UTF-8");
        String uri = req.getRequestURI();
        if (uri != null && uri.contains("/ping")) {
            resp.getWriter().write("{\"status\":\"ok\"}");
        } else {
            resp.getWriter().write("{\"info\":\"WorkBuddy Chat API v3 (SSE Streaming)\"}");
        }
    }

    // ── Helpers ──────────────────────────────────────────

    private void safePut(JsonObject obj, String key, String value) {
        if (value != null && !value.isEmpty()) obj.addProperty(key, value);
    }

    private String readBody(HttpServletRequest req) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader r = req.getReader()) { String l; while ((l = r.readLine()) != null) sb.append(l); }
        return sb.toString();
    }
}
