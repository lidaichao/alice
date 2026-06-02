package com.lmd.workbuddy;

import com.atlassian.jira.component.ComponentAccessor;
import com.atlassian.sal.api.pluginsettings.PluginSettings;
import com.atlassian.sal.api.pluginsettings.PluginSettingsFactory;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 配置存储服务 — 所有配置项通过 PluginSettings 持久化到 Jira 内部数据库。
 * 已加入 JVM 级多线程安全缓存，彻底解决高频读取导致的 DB I/O 穿透瓶颈。
 */
public class ConfigService {

    // 高性能内存缓存，生命周期与插件一致
    private static final ConcurrentHashMap<String, String> CACHE = new ConcurrentHashMap<>();
    
    // 防缓存穿透标记：用于缓存"数据库中本来就不存在"的空值，避免重复查库
    private static final String NULL_MARKER = "<WB_NULL>";

    private static PluginSettings getSettings() {
        PluginSettingsFactory factory = ComponentAccessor.getOSGiComponentInstanceOfType(PluginSettingsFactory.class);
        return factory.createGlobalSettings();
    }

    private static String k(String name) { return "com.lmd.workbuddy." + name; }

    public static String get(String name) {
        String cacheKey = k(name);
        
        // computeIfAbsent 保证了高并发下只有一个线程会去查库
        String val = CACHE.computeIfAbsent(cacheKey, key -> {
            Object v = getSettings().get(key);
            return v != null ? v.toString() : NULL_MARKER;
        });
        
        return NULL_MARKER.equals(val) ? null : val;
    }

    public static void set(String name, String value) {
        String cacheKey = k(name);
        if (value == null || value.isEmpty()) {
            getSettings().remove(cacheKey);
            CACHE.put(cacheKey, NULL_MARKER); // 同步更新缓存为 NULL 状态
        } else {
            getSettings().put(cacheKey, value);
            CACHE.put(cacheKey, value);       // 同步更新缓存
        }
    }

    // ---------------- 以下的所有 Getter 和 Setter 保持你的原样不动 ----------------
    
    public static String getSvnUrl() { return get("svn.url"); }
    public static void setSvnUrl(String v) { set("svn.url", v); }

    public static String getSvnUser() { return get("svn.user"); }
    public static void setSvnUser(String v) { set("svn.user", v); }

    public static String getSvnPass() { return get("svn.pass"); }
    public static void setSvnPass(String v) { set("svn.pass", v); }

    public static String getFishEyeUrl() { return get("fisheye.url"); }
    public static void setFishEyeUrl(String v) { set("fisheye.url", v); }

    public static String getNotionKey() { return get("notion.key"); }
    public static void setNotionKey(String v) { set("notion.key", v); }

    public static String getNotionDb() { return get("notion.db"); }
    public static void setNotionDb(String v) { set("notion.db", v); }

    public static String getGDriveKey() { return get("gdrive.key"); }
    public static void setGDriveKey(String v) { set("gdrive.key", v); }

    public static String getGDriveFolders() { return get("gdrive.folders"); }
    public static void setGDriveFolders(String v) { set("gdrive.folders", v); }

    public static String getAiProvider() { return get("ai.provider"); }
    public static void setAiProvider(String v) { set("ai.provider", v); }

    public static String getAiUrl() { return get("ai.url"); }
    public static void setAiUrl(String v) { set("ai.url", v); }

    public static String getAiModel() { return get("ai.model"); }
    public static void setAiModel(String v) { set("ai.model", v); }

    public static String getAiKey() { return get("ai.key"); }
    public static void setAiKey(String v) { set("ai.key", v); }

    public static String getBridgeUrl() { return get("bridge.url"); }
    public static void setBridgeUrl(String v) { set("bridge.url", v); }

    public static String getBridgeUrlOrDefault() {
        String v = get("bridge.url");
        return (v != null && !v.isEmpty()) ? v : "http://localhost:9099";
    }

    public static int getAiMaxTokens() {
        String v = get("ai.max_tokens");
        return (v != null && !v.isEmpty()) ? Integer.parseInt(v) : 4096;
    }
    public static void setAiMaxTokens(int n) { set("ai.max_tokens", String.valueOf(n)); }

    public static double getAiTemp() {
        String v = get("ai.temp");
        return (v != null && !v.isEmpty()) ? Double.parseDouble(v) : 1.0;
    }
    public static void setAiTemp(double n) { set("ai.temp", String.valueOf(n)); }
}
