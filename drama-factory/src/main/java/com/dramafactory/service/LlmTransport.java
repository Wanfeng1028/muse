package com.dramafactory.service;

import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Map;

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

        // 1. 实时读取代理环境变量（HTTPS_PROXY 优先，其次 https_proxy）
        URI proxyUri = null;
        String[] envKeys = {"HTTPS_PROXY", "https_proxy"};
        for (String key : envKeys) {
            String raw = System.getenv(key);
            if (raw == null || raw.isBlank()) {
                continue;
            }
            URI candidate;
            try {
                candidate = URI.create(raw.trim());
            } catch (IllegalArgumentException e) {
                continue;
            }
            if (candidate.getHost() != null && !candidate.getHost().isBlank()) {
                proxyUri = candidate;
                break;
            }
        }
        // 无有效代理 → 直连（普通部署环境）；有代理 → 走代理
        HttpHost proxy = null;
        String user = null;
        String pass = null;
        if (proxyUri == null) {
            log.info("未检测到出口代理，直连目标");
        } else {
            String host = proxyUri.getHost();
            int port = proxyUri.getPort();
            if (port <= 0) {
                port = 3128;
            }

            // 2. 解析 userinfo（user:pass）；没有 userinfo 则只设代理、不做代理认证
            String userInfo = proxyUri.getUserInfo();
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

            proxy = new HttpHost(host, port);
        }

        // 3. 超时配置
        RequestConfig.Builder requestConfigBuilder = RequestConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(timeoutSeconds))
                .setResponseTimeout(Timeout.ofSeconds(timeoutSeconds));
        if (proxy != null) {
            requestConfigBuilder.setProxy(proxy);
        }
        RequestConfig requestConfig = requestConfigBuilder.build();

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

            HttpPost post = new HttpPost(url);
            post.setEntity(new StringEntity(jsonBody, ContentType.APPLICATION_JSON));
            if (authHeader != null) {
                post.setHeader(authHeader.getKey(), authHeader.getValue());
            }

            try (CloseableHttpResponse response = client.execute(post, ctx)) {
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
