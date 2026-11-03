package com.dramaauth.service;

import com.dramaauth.exception.ApiException;
import com.dramaauth.model.OAuthAccount;
import com.dramaauth.model.User;
import com.dramaauth.repository.OAuthAccountRepository;
import com.dramaauth.repository.UserRepository;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.time.Duration;
import java.util.Base64;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 第三方 OAuth 登录。
 *
 * <p>诚实声明：无真实应用凭证时对应渠道返回 501 OAUTH_NOT_CONFIGURED，
 * handshake 未实测，不伪造"已验证"。
 */
@Service
public class OAuthService {

    /** 支持的渠道 */
    public static final java.util.List<String> PROVIDERS = java.util.List.of("google", "github", "apple");

    private final UserRepository userRepository;
    private final OAuthAccountRepository oauthRepository;
    private final com.dramaauth.repository.SessionRepository sessionRepository;
    private final JwtService jwtService;
    private final ObjectMapper mapper = new ObjectMapper();
    private final HttpClient http = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(10)).build();

    /** state 防 CSRF：内存存 10 分钟 */
    private final ConcurrentHashMap<String, Long> states = new ConcurrentHashMap<>();

    private final String googleClientId;
    private final String googleClientSecret;
    private final String googleRedirectUri;
    private final String githubClientId;
    private final String githubClientSecret;
    private final String githubRedirectUri;
    private final String appleClientId;
    private final String appleTeamId;
    private final String appleKeyId;
    private final String applePrivateKey;
    private final String appleRedirectUri;

    public OAuthService(UserRepository userRepository, OAuthAccountRepository oauthRepository,
                        com.dramaauth.repository.SessionRepository sessionRepository,
                        JwtService jwtService,
                        @Value("${oauth.google.client-id:}") String googleClientId,
                        @Value("${oauth.google.client-secret:}") String googleClientSecret,
                        @Value("${oauth.google.redirect-uri:}") String googleRedirectUri,
                        @Value("${oauth.github.client-id:}") String githubClientId,
                        @Value("${oauth.github.client-secret:}") String githubClientSecret,
                        @Value("${oauth.github.redirect-uri:}") String githubRedirectUri,
                        @Value("${oauth.apple.client-id:}") String appleClientId,
                        @Value("${oauth.apple.team-id:}") String appleTeamId,
                        @Value("${oauth.apple.key-id:}") String appleKeyId,
                        @Value("${oauth.apple.private-key:}") String applePrivateKey,
                        @Value("${oauth.apple.redirect-uri:}") String appleRedirectUri) {
        this.userRepository = userRepository;
        this.oauthRepository = oauthRepository;
        this.sessionRepository = sessionRepository;
        this.jwtService = jwtService;
        this.googleClientId = googleClientId;
        this.googleClientSecret = googleClientSecret;
        this.googleRedirectUri = googleRedirectUri;
        this.githubClientId = githubClientId;
        this.githubClientSecret = githubClientSecret;
        this.githubRedirectUri = githubRedirectUri;
        this.appleClientId = appleClientId;
        this.appleTeamId = appleTeamId;
        this.appleKeyId = appleKeyId;
        this.applePrivateKey = applePrivateKey;
        this.appleRedirectUri = appleRedirectUri;
    }

    public record OAuthUserInfo(String providerUserId, String email, String nickname, String avatarUrl) {
    }

    /** 生成授权 URL；未配置抛 501 */
    public String authUrl(String provider) {
        String state = UUID.randomUUID().toString();
        states.put(state, System.currentTimeMillis() + 10 * 60 * 1000);
        return switch (provider) {
            case "google" -> {
                requireConfigured(!googleClientId.isBlank(), "google");
                yield "https://accounts.google.com/o/oauth2/v2/auth"
                        + "?client_id=" + enc(googleClientId)
                        + "&redirect_uri=" + enc(googleRedirectUri)
                        + "&response_type=code&scope=" + enc("openid email profile")
                        + "&state=" + enc(state);
            }
            case "github" -> {
                requireConfigured(!githubClientId.isBlank(), "github");
                yield "https://github.com/login/oauth/authorize"
                        + "?client_id=" + enc(githubClientId)
                        + "&redirect_uri=" + enc(githubRedirectUri)
                        + "&scope=" + enc("user:email")
                        + "&state=" + enc(state);
            }
            case "apple" -> {
                requireConfigured(!appleClientId.isBlank(), "apple");
                yield "https://appleid.apple.com/auth/authorize"
                        + "?client_id=" + enc(appleClientId)
                        + "&redirect_uri=" + enc(appleRedirectUri)
                        + "&response_type=code&scope=" + enc("name email")
                        + "&response_mode=query&state=" + enc(state);
            }
            default -> throw new ApiException(HttpStatus.NOT_FOUND, "NOT_FOUND", "不支持的渠道");
        };
    }

    /**
     * 回调：校验 state → code 换 token → 取用户信息 → find-or-create 用户 → 签发自家 JWT。
     * 返回 {accessToken, refreshToken}（会话 device 记为 oauth/{provider}）。
     */
    @Transactional
    public AuthService.TokenPair callback(String provider, String code, String state, String ip) {
        checkState(state);
        OAuthUserInfo info = switch (provider) {
            case "google" -> {
                requireConfigured(!googleClientId.isBlank(), "google");
                yield googleUserInfo(exchangeCode(
                        "https://oauth2.googleapis.com/token",
                        "code=" + enc(code)
                                + "&client_id=" + enc(googleClientId)
                                + "&client_secret=" + enc(googleClientSecret)
                                + "&redirect_uri=" + enc(googleRedirectUri)
                                + "&grant_type=authorization_code"));
            }
            case "github" -> {
                requireConfigured(!githubClientId.isBlank(), "github");
                yield githubUserInfo(exchangeCode(
                        "https://github.com/login/oauth/access_token",
                        "code=" + enc(code)
                                + "&client_id=" + enc(githubClientId)
                                + "&client_secret=" + enc(githubClientSecret)
                                + "&redirect_uri=" + enc(githubRedirectUri)));
            }
            case "apple" -> {
                requireConfigured(!appleClientId.isBlank() && !applePrivateKey.isBlank(), "apple");
                yield appleUserInfo(exchangeCode(
                        "https://appleid.apple.com/auth/token",
                        "code=" + enc(code)
                                + "&client_id=" + enc(appleClientId)
                                + "&client_secret=" + enc(appleClientSecret())
                                + "&redirect_uri=" + enc(appleRedirectUri)
                                + "&grant_type=authorization_code"));
            }
            default -> throw new ApiException(HttpStatus.NOT_FOUND, "NOT_FOUND", "不支持的渠道");
        };
        User user = findOrCreate(provider.toUpperCase(), info);
        // OAuth 登录直接签发（会话由 AuthService.issueTokens 经反射？不——此处简化：复用 login 后的签发逻辑）
        return issueOAuthTokens(user, provider, ip);
    }

    /* ==================== 内部 ==================== */

    private void requireConfigured(boolean ok, String provider) {
        if (!ok) {
            throw new ApiException(HttpStatus.NOT_IMPLEMENTED, "OAUTH_NOT_CONFIGURED",
                    provider + " OAuth 未配置（缺 client-id/secret），handshake 未实测");
        }
    }

    private void checkState(String state) {
        Long exp = states.remove(state);
        if (state == null || exp == null || exp < System.currentTimeMillis()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "BAD_STATE", "state 校验失败");
        }
    }

    private String enc(String s) {
        return URLEncoder.encode(s == null ? "" : s, StandardCharsets.UTF_8);
    }

    /** code 换 token，返回 token 响应 map */
    private Map<String, Object> exchangeCode(String tokenUrl, String formBody) {
        try {
            HttpRequest req = HttpRequest.newBuilder(URI.create(tokenUrl))
                    .timeout(Duration.ofSeconds(15))
                    .header("Content-Type", "application/x-www-form-urlencoded")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(formBody))
                    .build();
            HttpResponse<String> res = http.send(req, HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() < 200 || res.statusCode() >= 300) {
                throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "code 换 token 失败");
            }
            return mapper.readValue(res.body(), new TypeReference<Map<String, Object>>() {
            });
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "OAuth 通信失败");
        }
    }

    private String get(String url, String bearer) {
        try {
            HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(15))
                    .header("Accept", "application/json");
            if (bearer != null) {
                b.header("Authorization", "Bearer " + bearer);
            }
            HttpResponse<String> res = http.send(b.GET().build(), HttpResponse.BodyHandlers.ofString());
            if (res.statusCode() < 200 || res.statusCode() >= 300) {
                throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "获取用户信息失败");
            }
            return res.body();
        } catch (ApiException e) {
            throw e;
        } catch (Exception e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "OAuth 通信失败");
        }
    }

    private OAuthUserInfo googleUserInfo(Map<String, Object> tokenRes) {
        try {
            String at = String.valueOf(tokenRes.get("access_token"));
            Map<String, Object> me = mapper.readValue(
                    get("https://www.googleapis.com/oauth2/v3/userinfo", at),
                    new TypeReference<Map<String, Object>>() {
                    });
            return new OAuthUserInfo(String.valueOf(me.get("sub")),
                    str(me.get("email")), str(me.get("name")), str(me.get("picture")));
        } catch (Exception e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "Google 用户信息解析失败");
        }
    }

    private OAuthUserInfo githubUserInfo(Map<String, Object> tokenRes) {
        try {
            String at = String.valueOf(tokenRes.get("access_token"));
            Map<String, Object> me = mapper.readValue(
                    get("https://api.github.com/user", at),
                    new TypeReference<Map<String, Object>>() {
                    });
            String email = str(me.get("email"));
            if (email.isEmpty()) {
                java.util.List<Map<String, Object>> emails = mapper.readValue(
                        get("https://api.github.com/user/emails", at),
                        new TypeReference<java.util.List<Map<String, Object>>>() {
                        });
                for (Map<String, Object> em : emails) {
                    if (Boolean.TRUE.equals(em.get("primary")) && Boolean.TRUE.equals(em.get("verified"))) {
                        email = str(em.get("email"));
                        break;
                    }
                }
            }
            return new OAuthUserInfo(String.valueOf(me.get("id")), email,
                    str(me.get("login")), str(me.get("avatar_url")));
        } catch (Exception e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "GitHub 用户信息解析失败");
        }
    }

    private OAuthUserInfo appleUserInfo(Map<String, Object> tokenRes) {
        try {
            // Apple 在 token 响应里直接给 id_token（JWT），解析其 claims
            String idToken = String.valueOf(tokenRes.get("id_token"));
            String[] parts = idToken.split("\\.");
            Map<String, Object> claims = mapper.readValue(
                    Base64.getUrlDecoder().decode(parts[1]),
                    new TypeReference<Map<String, Object>>() {
                    });
            return new OAuthUserInfo(String.valueOf(claims.get("sub")),
                    str(claims.get("email")), "", "");
        } catch (Exception e) {
            throw new ApiException(HttpStatus.BAD_GATEWAY, "OAUTH_FAILED", "Apple 用户信息解析失败");
        }
    }

    /**
     * Apple client_secret：ES256 JWT（team_id/key_id/p8 私钥），10 分钟有效。
     * 纯 JDK 实现，无需第三方库。
     */
    String appleClientSecret() {
        try {
            long now = System.currentTimeMillis() / 1000;
            String header = b64("{\"alg\":\"ES256\",\"kid\":\"" + appleKeyId + "\"}");
            String payload = b64("{\"iss\":\"" + appleTeamId + "\",\"iat\":" + now
                    + ",\"exp\":" + (now + 600) + ",\"aud\":\"https://appleid.apple.com\""
                    + ",\"sub\":\"" + appleClientId + "\"}");
            String signingInput = header + "." + payload;
            byte[] p8 = Base64.getMimeDecoder().decode(applePrivateKey
                    .replace("-----BEGIN PRIVATE KEY-----", "")
                    .replace("-----END PRIVATE KEY-----", "")
                    .replaceAll("\\s", ""));
            PrivateKey key = KeyFactory.getInstance("EC")
                    .generatePrivate(new PKCS8EncodedKeySpec(p8));
            Signature sig = Signature.getInstance("SHA256withECDSA");
            sig.initSign(key);
            sig.update(signingInput.getBytes(StandardCharsets.UTF_8));
            byte[] der = sig.sign();
            return signingInput + "." + b64(rawEcdsa(der));
        } catch (Exception e) {
            throw new ApiException(HttpStatus.INTERNAL_SERVER_ERROR, "OAUTH_FAILED", "Apple client_secret 生成失败");
        }
    }

    /** DER 转 raw R||S（各 32 字节，P-256） */
    private byte[] rawEcdsa(byte[] der) throws Exception {
        // 简单 DER 解析：SEQ { INT r, INT s }
        int i = 2; // 跳过 0x30 len
        if ((der[1] & 0x80) != 0) {
            i = 2 + (der[1] & 0x7F);
        }
        if (der[i++] != 0x02) throw new IllegalArgumentException("bad der");
        int rLen = der[i++] & 0xFF;
        byte[] r = java.util.Arrays.copyOfRange(der, i, i + rLen);
        i += rLen;
        if (der[i++] != 0x02) throw new IllegalArgumentException("bad der");
        int sLen = der[i++] & 0xFF;
        byte[] sBytes = java.util.Arrays.copyOfRange(der, i, i + sLen);
        byte[] raw = new byte[64];
        System.arraycopy(stripLeading(r), 0, raw, 32 - Math.min(32, stripLeading(r).length),
                Math.min(32, stripLeading(r).length));
        byte[] s2 = stripLeading(sBytes);
        System.arraycopy(s2, 0, raw, 64 - Math.min(32, s2.length), Math.min(32, s2.length));
        return raw;
    }

    private byte[] stripLeading(byte[] b) {
        int i = 0;
        while (i < b.length - 1 && b[i] == 0) i++;
        return java.util.Arrays.copyOfRange(b, i, b.length);
    }

    private String b64(String s) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    private String b64(byte[] b) {
        return Base64.getUrlEncoder().withoutPadding().encodeToString(b);
    }

    private String str(Object o) {
        return o == null ? "" : String.valueOf(o);
    }

    /** find-or-create：已绑定直接返回用户；同邮箱用户则绑定；否则新建 */
    private User findOrCreate(String provider, OAuthUserInfo info) {
        return oauthRepository.findByProviderAndProviderUserId(provider, info.providerUserId())
                .map(OAuthAccount::getUser)
                .orElseGet(() -> {
                    User user = null;
                    if (!info.email().isEmpty()) {
                        user = userRepository.findByEmail(info.email().toLowerCase()).orElse(null);
                    }
                    if (user == null) {
                        user = new User();
                        user.setEmail(info.email().isEmpty()
                                ? provider.toLowerCase() + "_" + info.providerUserId() + "@oauth.local"
                                : info.email().toLowerCase());
                        user.setNickname(info.nickname().isEmpty() ? provider + "用户" : info.nickname());
                        user.setAvatarUrl(info.avatarUrl().isEmpty() ? null : info.avatarUrl());
                        user.setRole(userRepository.count() == 0 ? "ADMIN" : "USER");
                        user = userRepository.save(user);
                    }
                    OAuthAccount oa = new OAuthAccount();
                    oa.setUser(user);
                    oa.setProvider(provider);
                    oa.setProviderUserId(info.providerUserId());
                    oa.setEmail(info.email());
                    oauthRepository.save(oa);
                    return user;
                });
    }

    /** OAuth 登录签发：access + refresh（会话记 oauth 渠道） */
    private AuthService.TokenPair issueOAuthTokens(User user, String provider, String ip) {
        JwtService.AccessToken at = jwtService.createAccessToken(user.getId(), user.getRole());
        JwtService.RefreshToken rt = jwtService.createRefreshToken(user.getId());
        com.dramaauth.model.UserSession s = new com.dramaauth.model.UserSession();
        s.setUser(user);
        s.setTokenJti(rt.jti());
        s.setAccessJti(at.jti());
        s.setDeviceInfo("oauth/" + provider);
        s.setIp(ip);
        s.setExpiresAt(java.time.LocalDateTime.now().plusSeconds(7 * 24 * 3600));
        sessionRepository.save(s);
        return new AuthService.TokenPair(at.token(), rt.token(), 900);
    }
}
