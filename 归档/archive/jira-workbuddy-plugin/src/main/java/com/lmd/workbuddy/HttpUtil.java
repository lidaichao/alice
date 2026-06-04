package com.lmd.workbuddy;

import javax.servlet.http.HttpServletRequest;
import java.io.*;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Shared HTTP utilities used by AdminServlet, ChatEndpoint, and future endpoints.
 * Eliminates duplicate httpGet/httpPost/esc methods across the codebase.
 */
public final class HttpUtil {

    private HttpUtil() {} // utility class

    // ── String helpers ──────────────────────────────

    /** JSON-safe string escaping */
    public static String esc(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "");
    }

    /** HTML-safe string escaping */
    public static String escHtml(String s) {
        if (s == null) return "";
        return s.replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace("\"", "&quot;")
                .replace("'", "&#39;");
    }

    /** Read full request body as String */
    public static String readBody(HttpServletRequest req) throws IOException {
        StringBuilder sb = new StringBuilder();
        try (BufferedReader reader = req.getReader()) {
            String line;
            while ((line = reader.readLine()) != null) sb.append(line);
        }
        return sb.toString();
    }

    // ── HTTP GET ─────────────────────────────────────

    /** Simple GET without auth */
    public static String httpGet(String url, int timeoutMs) throws Exception {
        return httpGet(url, null, null, null, timeoutMs);
    }

    /** GET with Bearer token + optional Notion version */
    public static String httpGet(String url, String bearerToken, String notionVersion,
                                  String authHeaderName, int timeoutMs) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setConnectTimeout(timeoutMs);
        c.setReadTimeout(timeoutMs);
        if (bearerToken != null) {
            c.setRequestProperty("Authorization", "Bearer " + bearerToken);
        }
        if (notionVersion != null) {
            c.setRequestProperty("Notion-Version", notionVersion);
        }
        int code = c.getResponseCode();
        InputStream is = code >= 400 ? c.getErrorStream() : c.getInputStream();
        if (is == null) {
            throw new IOException("HTTP " + code + " for " + url);
        }
        try (is) {
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        }
    }

    // ── HTTP POST ────────────────────────────────────

    /** POST with JSON body and Bearer auth */
    public static String httpPost(String url, String jsonBody, String bearerToken,
                                   String notionVersion, int timeoutMs) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        c.setRequestMethod("POST");
        c.setDoOutput(true);
        c.setConnectTimeout(timeoutMs);
        c.setReadTimeout(timeoutMs);
        c.setRequestProperty("Authorization", "Bearer " + bearerToken);
        c.setRequestProperty("Content-Type", "application/json");
        if (notionVersion != null) {
            c.setRequestProperty("Notion-Version", notionVersion);
        }
        try (OutputStream os = c.getOutputStream()) {
            os.write(jsonBody.getBytes(StandardCharsets.UTF_8));
        }
        int code = c.getResponseCode();
        InputStream is = code >= 400 ? c.getErrorStream() : c.getInputStream();
        if (is == null) {
            throw new IOException("HTTP " + code + " for " + url);
        }
        try (is) {
            return new String(is.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
