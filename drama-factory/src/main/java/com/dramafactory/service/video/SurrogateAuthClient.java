package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.UnixDomainSocketAddress;
import java.nio.channels.Channels;
import java.nio.channels.SocketChannel;
import java.nio.charset.StandardCharsets;
import java.util.AbstractMap;
import java.util.Map;
import java.util.Set;

/**
 * 从本机 authd Unix socket 获取动态凭证 surrogate，并封装为 HTTP 头。
 *
 * <p>协议说明：向 {@code JARVIS_AUTHD_SOCK}（缺省 {@code /run/hatch/auth/authd.sock}）
 * 发送原始 HTTP 请求，读取响应并解析 JSON 体，取出 surrogate 凭证。</p>
 *
 * <p>注意：surrogate 值属于敏感凭证，任何情况下都不得写入日志。</p>
 */
@Component
public class SurrogateAuthClient {

    /** authd socket 路径环境变量名。 */
    private static final String SOCKET_ENV = "JARVIS_AUTHD_SOCK";

    /** authd socket 缺省路径。 */
    private static final String DEFAULT_SOCKET_PATH = "/run/hatch/auth/authd.sock";

    /** 允许请求的 host 白名单。 */
    private static final Set<String> ALLOWED_HOSTS = Set.of(
            "apihub.agnes-ai.com",
            "apihub.agens-ai.com",
            "chatapi.weixin.qq.com",
            "dashscope.aliyuncs.com"
    );

    /** 默认凭证名称（Agnes），保持原有单参数方法的行为不变。 */
    private static final String DEFAULT_CREDENTIAL_NAME = "custom.agnes-ai";

    /** bearer_header 放置方式的标识。 */
    private static final String PLACEMENT_BEARER_HEADER = "bearer_header";

    /** 自定义头字段名（placement 为对象时使用）。 */
    private static final String PLACEMENT_CUSTOM_HEADER = "custom_header";

    private final ObjectMapper objectMapper;

    private final SocketExchange socketExchange;

    /**
     * Unix socket 交换接缝：生产环境走真实 SocketChannel，测试注入桩。
     * 包可见，仅供测试使用。
     */
    @FunctionalInterface
    interface SocketExchange {
        String exchange(String socketPath, String credentialName) throws IOException;
    }

    /**
     * 构造器注入 ObjectMapper（Spring Boot 自带）。
     *
     * @param objectMapper Jackson 解析器
     */
    @Autowired
    public SurrogateAuthClient(ObjectMapper objectMapper) {
        this(objectMapper, null);
    }

    /**
     * 包可见构造器：测试注入 socket 交换桩。
     */
    SurrogateAuthClient(ObjectMapper objectMapper, SocketExchange socketExchange) {
        this.objectMapper = objectMapper;
        this.socketExchange = socketExchange != null ? socketExchange : this::realExchange;
    }

    /**
     * 根据目标 URL 获取认证头。
     *
     * <p>先校验 URL 的 host 必须在白名单内，然后通过 Unix socket 向 authd 请求 surrogate，
     * 并根据 placement 决定返回的头名称与头值。</p>
     *
     * @param url 目标请求地址
     * @return 头名称到取值的映射条目；bearer_header 时返回 ("Authorization", "Bearer " + surrogate)；
     *         自定义头时返回 (custom_header 值, surrogate)
     * @throws IllegalArgumentException 当 url 为 null、无法解析或 host 不在白名单时抛出
     */
    public Map.Entry<String, String> authHeader(String url) {
        return authHeader(url, DEFAULT_CREDENTIAL_NAME);
    }

    /**
     * 根据目标 URL 与指定凭证名称获取认证头。
     *
     * @param url            目标请求地址
     * @param credentialName authd 中的凭证名称，例如 custom.qwen-cloud-cn、custom.weixin-chatapi
     * @return 头名称到取值的映射条目
     * @throws IllegalArgumentException 当 url 为 null、无法解析、host 不在白名单或 credentialName 为空时抛出
     */
    public Map.Entry<String, String> authHeader(String url, String credentialName) {
        if (url == null || url.isBlank()) {
            throw new IllegalArgumentException("url 不能为空");
        }
        if (credentialName == null || credentialName.isBlank()) {
            throw new IllegalArgumentException("credentialName 不能为空");
        }
        String host;
        try {
            host = URI.create(url).getHost();
        } catch (Exception e) {
            throw new IllegalArgumentException("无法解析 url 的 host: " + url);
        }
        if (host == null || !ALLOWED_HOSTS.contains(host)) {
            throw new IllegalArgumentException("url 的 host 不在白名单内: " + host);
        }
        return requestSurrogateHeader(credentialName);
    }

    /**
     * 通过 Unix socket 向 authd 请求指定凭证的 surrogate，并构造认证头。
     *
     * @param credentialName authd 中的凭证名称
     * @return 头名称与头值组成的条目
     */
    private Map.Entry<String, String> requestSurrogateHeader(String credentialName) {
        String socketPath = System.getenv(SOCKET_ENV);
        if (socketPath == null || socketPath.isBlank()) {
            socketPath = DEFAULT_SOCKET_PATH;
        }

        String rawResponse;
        try {
            rawResponse = socketExchange.exchange(socketPath, credentialName);
        } catch (IOException e) {
            throw new IllegalStateException("与 authd 通信失败", e);
        }
        HttpResponse parsed = parseHttpResponse(rawResponse);

        if (parsed.statusCode != 200) {
            throw new IllegalStateException("authd 返回非 200 状态码: " + parsed.statusCode);
        }

        return extractHeader(parsed.body);
    }

    /**
     * 建立 Unix domain socket 连接，发送原始 HTTP 请求并读取完整响应。
     *
     * @param socketPath socket 路径
     * @return 原始 HTTP 响应字符串（ISO-8859-1 解码，保留字节完整性）
     */
    private String realExchange(String socketPath, String credentialName) throws IOException {
        UnixDomainSocketAddress address = UnixDomainSocketAddress.of(socketPath);
        String body = "{\"name\":\"" + credentialName + "\"}";
        byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);

        StringBuilder headerBuilder = new StringBuilder();
        headerBuilder.append("POST /v1/credentials/surrogate HTTP/1.1\r\n");
        headerBuilder.append("Host: authd.local\r\n");
        headerBuilder.append("Content-Type: application/json\r\n");
        headerBuilder.append("Content-Length: ").append(bodyBytes.length).append("\r\n");
        headerBuilder.append("Connection: close\r\n");
        headerBuilder.append("\r\n");

        byte[] headerBytes = headerBuilder.toString().getBytes(StandardCharsets.ISO_8859_1);

        try (SocketChannel channel = SocketChannel.open(address)) {
            OutputStream out = Channels.newOutputStream(channel);
            out.write(headerBytes);
            out.write(bodyBytes);
            out.flush();

            InputStream in = Channels.newInputStream(channel);
            ByteArrayOutputStream buffer = new ByteArrayOutputStream();
            byte[] chunk = new byte[4096];
            int read;
            while ((read = in.read(chunk)) != -1) {
                buffer.write(chunk, 0, read);
            }
            return buffer.toString(StandardCharsets.ISO_8859_1);
        }
    }

    /**
     * 将原始 HTTP 响应拆分为状态码与响应体。
     *
     * @param rawResponse 原始响应字符串
     * @return 解析后的状态码与响应体
     */
    private HttpResponse parseHttpResponse(String rawResponse) {
        int separator = rawResponse.indexOf("\r\n\r\n");
        if (separator < 0) {
            throw new IllegalStateException("authd 响应格式非法：缺少头体分隔符");
        }
        String headerPart = rawResponse.substring(0, separator);
        String bodyPart = rawResponse.substring(separator + 4);

        String[] headerLines = headerPart.split("\r\n");
        if (headerLines.length == 0) {
            throw new IllegalStateException("authd 响应格式非法：缺少状态行");
        }
        String statusLine = headerLines[0];
        String[] statusTokens = statusLine.split(" ", 3);
        if (statusTokens.length < 2) {
            throw new IllegalStateException("authd 响应格式非法：状态行无效");
        }
        int statusCode;
        try {
            statusCode = Integer.parseInt(statusTokens[1].trim());
        } catch (NumberFormatException e) {
            throw new IllegalStateException("authd 响应格式非法：状态码无法解析");
        }
        return new HttpResponse(statusCode, bodyPart);
    }

    /**
     * 从响应体中解析凭证，并构造认证头条目。
     *
     * @param body JSON 响应体
     * @return 头名称与头值组成的条目
     */
    private Map.Entry<String, String> extractHeader(String body) {
        JsonNode root;
        try {
            root = objectMapper.readTree(body);
        } catch (IOException e) {
            throw new IllegalStateException("authd 响应 JSON 解析失败", e);
        }
        JsonNode credentials = root.path("credentials");
        if (!credentials.isArray() || credentials.isEmpty()) {
            throw new IllegalStateException("authd 响应中缺少 credentials 数组");
        }
        JsonNode entry = credentials.get(0);
        String surrogate = entry.path("surrogate").asText(null);
        if (surrogate == null || surrogate.isBlank()) {
            throw new IllegalStateException("authd 响应中缺少 surrogate 值");
        }
        JsonNode placement = entry.path("placement");

        if (placement.isTextual() && PLACEMENT_BEARER_HEADER.equals(placement.asText())) {
            return new AbstractMap.SimpleImmutableEntry<>("Authorization", "Bearer " + surrogate);
        }
        if (placement.isObject()) {
            String customHeader = placement.path(PLACEMENT_CUSTOM_HEADER).asText(null);
            if (customHeader == null || customHeader.isBlank()) {
                throw new IllegalStateException("authd 响应中 placement 缺少 custom_header");
            }
            return new AbstractMap.SimpleImmutableEntry<>(customHeader, surrogate);
        }
        throw new IllegalStateException("authd 响应中 placement 格式不受支持");
    }

    /**
     * HTTP 响应内部载体：状态码 + 响应体。
     */
    private static final class HttpResponse {
        private final int statusCode;
        private final String body;

        private HttpResponse(int statusCode, String body) {
            this.statusCode = statusCode;
            this.body = body;
        }
    }
}
