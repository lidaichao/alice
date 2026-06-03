package com.lmd.workbuddy;

import javax.servlet.ServletException;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.io.InputStream;
import java.io.FileInputStream;
import java.io.File;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

/**
 * ChatDialogServlet — 提供共享聊天对话框 UI 片段
 * 
 * 公开端点（无需登录），chat.js 和 admin.html 共同加载。
 * 优先从文件系统读取（支持热部署），回退到 classpath（冷启动）。
 */
public class ChatDialogServlet extends HttpServlet {

    @Override
    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        resp.setContentType("text/html;charset=UTF-8");
        resp.setHeader("Cache-Control", "no-cache, no-store, must-revalidate");

        byte[] bytes = null;

        // 优先从文件系统读取（热部署路径）
        try {
            File f = new File(System.getProperty("catalina.base"),
                "webapps/static/chat-dialog.html");
            if (f.exists()) {
                bytes = Files.readAllBytes(f.toPath());
            }
        } catch (Exception e) {
            // 文件不存在或无权限，回退
        }

        // 回退到 classpath（OSGi bundle 内资源）
        if (bytes == null) {
            try (InputStream is = getClass().getClassLoader().getResourceAsStream("static/chat-dialog.html")) {
                if (is != null) {
                    bytes = is.readAllBytes();
                }
            }
        }

        if (bytes == null) {
            resp.getWriter().write("<!-- chat-dialog.html not found -->");
            return;
        }

        // 注入当前 Jira 用户到前端全局变量（服务端渲染，不可篡改）
        String username = req.getRemoteUser();
        if (username == null || username.isEmpty()) {
            username = "anonymous";
        }
        String html = new String(bytes, StandardCharsets.UTF_8);
        String inject = "<script>window._wbUser=\"" + htmlEscape(username) + "\";window._wbUserName=\"" + htmlEscape(username) + "\";</script>\n";
        html = inject + html;
        resp.getWriter().write(html);
    }

    private String htmlEscape(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\"", "\\\"").replace("<", "\\u003c").replace("\n", "\\n");
    }
}
