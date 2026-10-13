package com.dramafactory.config;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.PasswordAuthentication;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.util.List;

/**
 * 出口代理配置：从环境变量读取代理并设为 JVM 全局代理。
 *
 * <p>背景：部分运行环境（如本开发 VM）所有出站流量必须经由 egress 代理，
 * Python 的 urllib 会自动读取 {@code HTTPS_PROXY} 环境变量，但 Java 的
 * {@code HttpClient} 默认不读。没有代理时，对外 HTTPS（如微信 ChatAPI、
 * DashScope）会因直连被拦截而报 "Unrecognized SSL message"。</p>
 *
 * <p>行为：仅当 {@code HTTPS_PROXY} / {@code https_proxy} 环境变量存在时生效；
 * 无该变量时保持直连，生产部署不受影响。代理账号密码只从环境变量读取，
 * 不打日志、不进仓库。</p>
 *
 * <p>实现上同时设置系统属性与显式 {@link ProxySelector#setDefault}，
 * 确保所有 {@code HttpClient}（无论何时构造）都走代理。</p>
 */
public final class EgressProxyConfig {

    private static final Logger log = LoggerFactory.getLogger(EgressProxyConfig.class);

    private EgressProxyConfig() {
    }

    /**
     * 在 {@code SpringApplication.run} 之前调用，确保所有 Bean 构造
     * {@code HttpClient} 之前代理已就绪。
     */
    public static void configureFromEnv() {
        String proxyUrl = System.getenv("HTTPS_PROXY");
        if (proxyUrl == null || proxyUrl.isBlank()) {
            proxyUrl = System.getenv("https_proxy");
        }
        if (proxyUrl == null || proxyUrl.isBlank()) {
            log.info("未检测到 HTTPS_PROXY，直连外网");
            return;
        }
        try {
            URI uri = new URI(proxyUrl.trim());
            String host = uri.getHost();
            int port = uri.getPort() > 0 ? uri.getPort() : 3128;
            if (host == null || host.isBlank()) {
                log.warn("代理地址解析失败，跳过代理配置");
                return;
            }

            // 系统属性：兼容依赖默认 ProxySelector 的代码
            System.setProperty("https.proxyHost", host);
            System.setProperty("https.proxyPort", String.valueOf(port));
            System.setProperty("http.proxyHost", host);
            System.setProperty("http.proxyPort", String.valueOf(port));
            System.setProperty("http.nonProxyHosts", "localhost|127.0.0.1");

            // 显式默认 ProxySelector：所有 HttpClient 无条件走代理（除本地地址）
            ProxySelector.setDefault(new ProxySelector() {
                private final Proxy proxy = new Proxy(Proxy.Type.HTTP,
                        new InetSocketAddress(host, port));

                @Override
                public List<Proxy> select(URI uri) {
                    String h = uri.getHost();
                    // URI.getHost() 对 IPv6 字面量返回带方括号的 "[::1]"，先去掉括号再比对
                    if (h != null && h.startsWith("[") && h.endsWith("]")) {
                        h = h.substring(1, h.length() - 1);
                    }
                    if (h == null || h.equalsIgnoreCase("localhost")
                            || h.equals("127.0.0.1") || h.equals("::1")) {
                        return List.of(Proxy.NO_PROXY);
                    }
                    return List.of(proxy);
                }

                @Override
                public void connectFailed(URI uri, SocketAddress sa, java.io.IOException ioe) {
                    log.warn("代理连接失败 {}: {}", uri, ioe.getMessage());
                }
            });

            String userInfo = uri.getUserInfo();
            if (userInfo != null && !userInfo.isBlank()) {
                String[] parts = userInfo.split(":", 2);
                String user = parts[0];
                String password = parts.length > 1 ? parts[1] : "";
                Authenticator.setDefault(new Authenticator() {
                    @Override
                    protected PasswordAuthentication getPasswordAuthentication() {
                        if (getRequestorType() == RequestorType.PROXY) {
                            return new PasswordAuthentication(user, password.toCharArray());
                        }
                        return null;
                    }
                });
            }
            log.info("已启用出口代理 {}:{}（来自 HTTPS_PROXY），已安装显式 ProxySelector", host, port);
        } catch (Exception e) {
            log.warn("解析 HTTPS_PROXY 失败，降级为直连: {}", e.getMessage());
        }
    }
}
