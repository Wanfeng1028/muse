package com.dramafactory.service;

import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.apache.hc.client5.http.auth.AuthCache;
import org.apache.hc.client5.http.auth.AuthScope;
import org.apache.hc.client5.http.auth.UsernamePasswordCredentials;
import org.apache.hc.client5.http.classic.methods.HttpPost;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.auth.BasicAuthCache;
import org.apache.hc.client5.http.impl.auth.BasicScheme;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.classic.CloseableHttpResponse;
import org.apache.hc.client5.http.protocol.HttpClientContext;
import org.apache.hc.core5.http.ClassicHttpResponse;
import org.apache.hc.core5.http.ContentType;
import org.apache.hc.core5.http.HttpHost;
import org.apache.hc.core5.http.io.entity.EntityUtils;
import org.apache.hc.core5.http.io.entity.StringEntity;
import org.apache.hc.core5.util.Timeout;

/**
 * 大模型 HTTP 传输层（包可见工具类）。
 *
 * <p>为什么不用 JDK 自带的 {@link java.net.http.HttpClient}：JDK 只支持"被动式"代理认证
 * （先发无认证 CONNECT，等代理返回 407 后再带凭证重试）；而本沙箱的出口代理要求 CONNECT
 * 请求<b>预先</b>携带 {@code Proxy-Authorization}，对无认证的 CONNECT 直接返回策略文本而非 407，
 * 导致 JDK 的被动式流程永远走不通。Apache HttpClient 5 可通过 {@link AuthCache} 预置
 * {@link BasicScheme}，实现"预先代理认证"。</p>
 *
 * <p>代理信息每次调用时实时从环境变量 {@code HTTPS_PROXY} / {@code https_proxy} 读取，
 * 格式形如 {@code http://user:pass@host:port}。凭证绝不写入日志或异常信息。</p>
 */
final class LlmTransport {

    private static final Logger log = LoggerFactory.getLogger(LlmTransport.class);

    private LlmTransport() {
    }

    /** 代理规格：host/port 必填；user/pass 可为 null（无代理认证）。 */
    record ProxySpec(String host, int port, String user, String pass) {
    }

    /**
     * 解析代理字符串（纯函数，无 IO）。
     *
     * @param raw 形如 {@code http://user:pass@host:port} 的原始字符串
     * @return 解析结果；raw 为空/空白、URI 非法或 host 为空时返回 empty
     */
    static Optional<ProxySpec> parseProxy(String raw) {
        if (raw == null || raw.isBlank()) {
            return Optional.empty();
        }
        URI uri;
        try {
            uri = URI.create(raw.trim());
        } catch (IllegalArgumentException e) {
            return Optional.empty();
        }
        String host = uri.getHost();
        if (host == null || host.isBlank()) {
            return Optional.empty();
        }
        int port = uri.getPort();
        if (port <= 0) {
            port = 3128;
        }
        String user = null;
        String pass = null;
        String userInfo = uri.getUserInfo();
        if (userInfo != null && !userInfo.isBlank()) {
            int idx = userInfo.indexOf(':');
            if (idx >= 0) {
                user = userInfo.substring(0, idx);
                pass = userInfo.substring(idx + 1);
            } else {
                user = userInfo;
                pass = "";
            }
        }
        return Optional.of(new ProxySpec(host, port, user, pass));
    }

    /**
     * 从环境变量 Map 中解析代理：按 "HTTPS_PROXY"、"https_proxy" 顺序取第一个可解析的非空值。
     *
     * @param env 环境变量表（可为 null）
     * @return 解析结果；全部缺失或解析失败时返回 empty
     */
    static Optional<ProxySpec> resolveProxy(Map<String, String> env) {
        if (env == null) {
            return Optional.empty();
        }
        String[] keys = {"HTTPS_PROXY", "https_proxy"};
        for (String key : keys) {
            String raw = env.get(key);
            if (raw == null || raw.isBlank()) {
                continue;
            }
            Optional<ProxySpec> parsed = parseProxy(raw);
            if (parsed.isPresent()) {
                return parsed;
            }
        }
        return Optional.empty();
    }

    /** 从真实进程环境变量解析代理。 */
    static Optional<ProxySpec> resolveProxy() {
        return resolveProxy(System.getenv());
    }

    /** 把代理规格转换为 Apache HttpClient 的 HttpHost。 */
    static HttpHost toHttpHost(ProxySpec spec) {
        return new HttpHost(spec.host(), spec.port());
    }

    /**
     * 构建请求配置（纯函数）。
     *
     * @param proxy          可为 null（直连）
     * @param timeoutSeconds 连接与响应超时（秒）
     */
    static RequestConfig buildRequestConfig(HttpHost proxy, int timeoutSeconds) {
        RequestConfig.Builder builder = RequestConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(timeoutSeconds))
                .setResponseTimeout(Timeout.ofSeconds(timeoutSeconds));
        if (proxy != null) {
            builder.setProxy(proxy);
        }
        return builder.build();
    }

    /**
     * 构建 HttpPost（纯函数，不发请求）。
     *
     * @param authHeader 可为 null
     */
    static HttpPost buildPost(String url, String jsonBody, Map.Entry<String, String> authHeader) {
        HttpPost post = new HttpPost(url);
        post.setEntity(new StringEntity(jsonBody, ContentType.APPLICATION_JSON));
        if (authHeader != null) {
            post.setHeader(authHeader.getKey(), authHeader.getValue());
        }
        return post;
    }

    /**
     * 执行 POST 并解析响应（可注入 client 的 seam，纯逻辑测试用）。
     * 异常信息绝不包含代理凭证。
     */
    /**
     * HTTP 执行函数式接口：把"发请求"与"解析响应"解耦，供无 socket 的契约测试注入。
     * 生产路径传 {@code (post, ctx) -> client.execute(post, ctx)}。
     */
    @FunctionalInterface
    interface HttpExecutor {
        ClassicHttpResponse execute(HttpPost post, HttpClientContext ctx) throws IOException;
    }

    static String postJson(String url, String jsonBody,
                           Map.Entry<String, String> authHeader, int timeoutSeconds,
                           HttpExecutor executor) {
        try {
            HttpPost post = buildPost(url, jsonBody, authHeader);
            HttpClientContext ctx = HttpClientContext.create();
            try (ClassicHttpResponse response = executor.execute(post, ctx)) {
                int status = response.getCode();
                String body = response.getEntity() == null
                        ? ""
                        : EntityUtils.toString(response.getEntity(), StandardCharsets.UTF_8);

                if (status < 200 || status >= 300) {
                    String preview = body.length() > 300 ? body.substring(0, 300) : body;
                    throw new RuntimeException("大模型接口返回非 2xx: " + status + ", body=" + preview);
                }
                return body;
            }
        } catch (RuntimeException e) {
            // 已是业务异常，直接透传（其 msg 不含凭证）
            throw e;
        } catch (Exception e) {
            // 绝不把 userinfo/密码写入异常信息
            throw new RuntimeException("调用大模型接口失败: " + e.getMessage(), e);
        }
    }

    /**
     * 经出口代理向指定 URL POST JSON，并返回响应体字符串（UTF-8）。
     *
     * @param url            目标地址（HTTPS）
     * @param jsonBody       请求体 JSON 字符串
     * @param authHeader     可选的额外请求头（如 {@code Authorization}），可为 {@code null}
     * @param timeoutSeconds 连接/响应超时（秒）
     * @return 响应体字符串
     * @throws RuntimeException 代理缺失、非 2xx 或任何 IO 异常（不包含代理凭证）
     */
    static String postJson(String url, String jsonBody,
                           Map.Entry<String, String> authHeader, int timeoutSeconds) {

        // 1. 实时读取代理环境变量（HTTPS_PROXY 优先，其次 https_proxy），解析为 ProxySpec
        Optional<ProxySpec> specOpt = resolveProxy();
        HttpHost proxy = null;
        String user = null;
        String pass = null;
        if (specOpt.isEmpty()) {
            log.info("未检测到出口代理，直连目标");
        } else {
            ProxySpec spec = specOpt.get();
            user = spec.user();
            pass = spec.pass();
            proxy = toHttpHost(spec);
        }

        // 2. 超时与代理配置
        RequestConfig requestConfig = buildRequestConfig(proxy, timeoutSeconds);

        CloseableHttpClient client = null;
        try {
            HttpClientContext ctx = HttpClientContext.create();
            if (user != null) {

                // 预先代理认证：把 BasicScheme 预置到 AuthCache，使首个 CONNECT 即带 Proxy-Authorization
                org.apache.hc.client5.http.auth.CredentialsProvider creds =
                        new org.apache.hc.client5.http.impl.auth.BasicCredentialsProvider();
                ((org.apache.hc.client5.http.impl.auth.BasicCredentialsProvider) creds)
                        .setCredentials(new AuthScope(proxy),
                                new UsernamePasswordCredentials(user, pass.toCharArray()));

                AuthCache authCache = new BasicAuthCache();
                authCache.put(proxy, new BasicScheme());

                ctx.setCredentialsProvider(creds);
                ctx.setAuthCache(authCache);

                client = HttpClients.custom()
                        .setProxy(proxy)
                        .setDefaultCredentialsProvider(creds)
                        .setDefaultRequestConfig(requestConfig)
                        .build();
            } else if (proxy != null) {
                client = HttpClients.custom()
                        .setProxy(proxy)
                        .setDefaultRequestConfig(requestConfig)
                        .build();
            } else {
                // 直连：无代理环境
                client = HttpClients.custom()
                        .setDefaultRequestConfig(requestConfig)
                        .build();
            }

            final CloseableHttpClient finalClient = client;
            return postJson(url, jsonBody, authHeader, timeoutSeconds,
                    (p, c) -> finalClient.execute(p, c));
        } catch (RuntimeException e) {
            // 已是业务异常，直接透传（其 msg 不含凭证）
            throw e;
        } catch (Exception e) {
            // 绝不把 userinfo/密码写入异常信息
            throw new RuntimeException("调用大模型接口失败: " + e.getMessage(), e);
        } finally {

            if (client != null) {
                try {
                    client.close();
                } catch (Exception ignored) {
                    // 忽略关闭异常
                }
            }
        }
    }
}
