package com.dramafactory.service.skill;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;

@Service
public class SkillHubClient {

    private static final Logger log = LoggerFactory.getLogger(SkillHubClient.class);
    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final int MAX_SNIPPET = 300;

    public interface SkillHttpGateway {
        record GatewayResponse(int statusCode, byte[] body) {}
        GatewayResponse get(String url) throws Exception;
    }

    public record HubSkill(String id, String name, String version, String description,
                           String author, String license, String packageUrl, String sha256) {}

    private final String baseUrl;
    private final SkillHttpGateway gateway;

    @org.springframework.beans.factory.annotation.Autowired
    public SkillHubClient(@Value("${drama.skillhub.base-url:}") String baseUrl) {
        this(baseUrl, defaultGateway());
    }

    SkillHubClient(String baseUrl, SkillHttpGateway gateway) {
        this.baseUrl = normalize(baseUrl);
        this.gateway = gateway;
    }

    private static String normalize(String raw) {
        if (raw == null) {
            return "";
        }
        String s = raw.trim();
        while (s.endsWith("/")) {
            s = s.substring(0, s.length() - 1);
        }
        return s;
    }

    private static SkillHttpGateway defaultGateway() {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
        return url -> {
            HttpRequest request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();
            HttpResponse<byte[]> response = client.send(request, HttpResponse.BodyHandlers.ofByteArray());
            return new SkillHttpGateway.GatewayResponse(response.statusCode(), response.body());
        };
    }

    public boolean isEnabled() {
        return !baseUrl.isEmpty();
    }

    public List<HubSkill> fetchSkills() {
        if (!isEnabled()) {
            return List.of();
        }
        String manifestUrl = baseUrl + "/manifest.json";
        SkillHttpGateway.GatewayResponse response = doGet(manifestUrl, "manifest");
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException("获取 skillhub manifest 失败，状态码=" + response.statusCode()
                    + "，响应=" + snippet(response.body()));
        }
        JsonNode root;
        try {
            root = MAPPER.readTree(response.body());
        } catch (IOException e) {
            throw new IllegalStateException("解析 skillhub manifest 失败: " + e.getMessage(), e);
        }
        JsonNode skillsNode = root.get("skills");
        if (skillsNode == null || !skillsNode.isArray()) {
            throw new IllegalStateException("manifest 缺少 skills 数组");
        }
        List<HubSkill> result = new ArrayList<>();
        for (JsonNode node : skillsNode) {
            String id = text(node, "id");
            if (id.isEmpty()) {
                log.warn("跳过 skillhub manifest 中缺少 id 的条目: {}", node);
                continue;
            }
            String packageUrl = text(node, "packageUrl");
            String resolved = resolvePackageUrl(packageUrl);
            result.add(new HubSkill(
                    id,
                    text(node, "name"),
                    text(node, "version"),
                    text(node, "description"),
                    text(node, "author"),
                    text(node, "license"),
                    resolved,
                    text(node, "sha256")
            ));
        }
        return result;
    }

    public Path downloadPackage(HubSkill skill, Path stagingDir) {
        String id = skill.id();
        if (skill.packageUrl() == null || skill.packageUrl().isEmpty()) {
            throw new IllegalStateException("skill " + id + " 缺少 packageUrl");
        }
        SkillHttpGateway.GatewayResponse response = doGet(skill.packageUrl(), "skill " + id);
        if (response.statusCode() < 200 || response.statusCode() >= 300) {
            throw new IllegalStateException("下载 skill 包失败: id=" + id + " status=" + response.statusCode());
        }
        Path zipPath = stagingDir.resolve(id + "-" + skill.version() + ".zip");
        byte[] body = response.body() == null ? new byte[0] : response.body();
        try {
            Files.write(zipPath, body);
        } catch (IOException e) {
            throw new IllegalStateException("写入 skill 包失败: id=" + id, e);
        }
        String sha = skill.sha256();
        if (sha != null && !sha.isEmpty()) {
            MessageDigest digest;
            try {
                digest = MessageDigest.getInstance("SHA-256");
            } catch (NoSuchAlgorithmException e) {
                throw new IllegalStateException("SHA-256 算法不可用", e);
            }
            byte[] actualBytes;
            try {
                actualBytes = digest.digest(Files.readAllBytes(zipPath));
            } catch (IOException e) {
                throw new IllegalStateException("读取 skill 包失败: id=" + id, e);
            }
            StringBuilder hexBuilder = new StringBuilder(actualBytes.length * 2);
            for (byte b : actualBytes) {
                hexBuilder.append(String.format("%02x", b));
            }
            String actual = hexBuilder.toString();
            String expected = sha.toLowerCase();
            if (!actual.equals(expected)) {
                try {
                    Files.deleteIfExists(zipPath);
                } catch (IOException ignored) {
                }
                throw new IllegalStateException("skill 包校验失败: id=" + id);
            }
        }
        return zipPath;
    }

    private SkillHttpGateway.GatewayResponse doGet(String url, String what) {
        try {
            return gateway.get(url);
        } catch (Exception e) {
            throw new IllegalStateException("请求 skillhub 失败 (" + what + "): " + e.getMessage(), e);
        }
    }

    private static String text(JsonNode node, String field) {
        JsonNode v = node.get(field);
        return v == null || v.isNull() ? "" : v.asText("");
    }

    private String resolvePackageUrl(String packageUrl) {
        if (packageUrl == null || packageUrl.isEmpty()) {
            return "";
        }
        if (packageUrl.startsWith("http://") || packageUrl.startsWith("https://")) {
            return packageUrl;
        }
        try {
            return URI.create(baseUrl + "/").resolve(packageUrl).toString();
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException("skill packageUrl 非法: " + packageUrl);
        }
    }

    private static String snippet(byte[] body) {
        if (body == null) {
            return "";
        }
        String s = new String(body, StandardCharsets.UTF_8);
        return s.length() > MAX_SNIPPET ? s.substring(0, MAX_SNIPPET) + "..." : s;
    }
}
