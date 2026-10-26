package com.dramaauth.service;

import com.dramaauth.exception.ApiException;
import com.dramaauth.metrics.AuthMetrics;
import com.dramaauth.model.User;
import com.dramaauth.model.UserSession;
import com.dramaauth.repository.SessionRepository;
import com.dramaauth.repository.UserRepository;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

/**
 * 账号核心服务：注册/登录/刷新/会话/资料/密码/邮箱。
 * 安全：密码只存 PBKDF2 hash；登录防爆破（同 email+ip 15 分钟 5 次失败 → 429）；
 * 敏感操作（改密码/改邮箱）必须重新验证密码；改密码后撤销其他会话。
 */
@Service
public class AuthService {

    /** 登录失败计数窗口 */
    private static final int MAX_FAILS = 5;
    private static final long WINDOW_SECONDS = 15 * 60;

    private final UserRepository userRepository;
    private final SessionRepository sessionRepository;
    private final PasswordService passwordService;
    private final JwtService jwtService;
    private final AuthMetrics metrics;

    /** 单机内存限流（多机部署时换 Redis，见 DEPLOY.md） */
    private final ConcurrentHashMap<String, Attempt> attempts = new ConcurrentHashMap<>();

    public AuthService(UserRepository userRepository, SessionRepository sessionRepository,
                       PasswordService passwordService, JwtService jwtService, AuthMetrics metrics) {
        this.userRepository = userRepository;
        this.sessionRepository = sessionRepository;
        this.passwordService = passwordService;
        this.jwtService = jwtService;
        this.metrics = metrics;
    }

    /* ==================== DTO ==================== */

    public record UserDto(Long id, String email, String nickname, String avatarUrl, String role, String language, String theme) {
    }

    public record TokenPair(String accessToken, String refreshToken, long expiresIn) {
    }

    public record SessionDto(Long id, String deviceInfo, String ip,
                             LocalDateTime createdAt, LocalDateTime expiresAt, boolean current) {
    }

    /* ==================== 注册 ==================== */

    @Transactional
    public UserDto register(String email, String password, String nickname) {
        email = norm(email).toLowerCase();
        nickname = norm(nickname);
        checkPasswordStrength(password);
        if (nickname.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", "昵称不能为空");
        }
        if (userRepository.existsByEmail(email)) {
            throw new ApiException(HttpStatus.CONFLICT, "EMAIL_EXISTS", "邮箱已被注册");
        }
        User u = new User();
        u.setEmail(email);
        u.setPasswordHash(passwordService.hash(password));
        u.setNickname(nickname);
        // 首个注册的用户为管理员
        u.setRole(userRepository.count() == 0 ? "ADMIN" : "USER");
        UserDto dto = toDto(userRepository.save(u));
        metrics.recordRegistration();
        return dto;
    }

    /* ==================== 登录 ==================== */

    @Transactional
    public TokenPair login(String email, String password, String deviceInfo, String ip) {
        email = norm(email).toLowerCase();
        String key = email + "|" + ip;
        checkRateLimit(key);
        User u = userRepository.findByEmail(email).orElse(null);
        // 不区分"用户不存在/密码错"，防枚举；失败统一计数
        if (u == null || !"ACTIVE".equals(u.getStatus())
                || u.getPasswordHash() == null
                || !passwordService.matches(password, u.getPasswordHash())) {
            recordFail(key);
            metrics.recordLogin(false);
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "邮箱或密码错误");
        }
        attempts.remove(key);
        metrics.recordLogin(true);
        return issueTokens(u, deviceInfo, ip);
    }

    /* ==================== 刷新 ==================== */

    @Transactional
    public TokenPair refresh(String refreshToken) {
        try {
            Map<String, Object> claims = jwtService.parseAndValidate(refreshToken);
            if (!"REFRESH".equals(claims.get("role"))) {
                throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "非法的 refresh token");
            }
            String jti = String.valueOf(claims.get("jti"));
            UserSession s = sessionRepository.findByTokenJti(jti).orElse(null);
            if (s == null || s.isRevoked() || s.getExpiresAt().isBefore(LocalDateTime.now())) {
                throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "会话已失效");
            }
            // 轮换：旧 jti 作废，签发新对
            s.setRevoked(true);
            sessionRepository.save(s);
            metrics.recordRefresh(true);
            return issueTokens(s.getUser(), s.getDeviceInfo(), s.getIp());
        } catch (ApiException e) {
            metrics.recordRefresh(false);
            throw e;
        }
    }

    /* ==================== 登出 ==================== */

    @Transactional
    public void logout(String accessToken) {
        Map<String, Object> claims = jwtService.parseAndValidate(accessToken);
        String accessJti = String.valueOf(claims.get("jti"));
        sessionRepository.findByAccessJti(accessJti).ifPresent(s -> {
            s.setRevoked(true);
            sessionRepository.save(s);
        });
    }

    /* ==================== 资料 ==================== */

    @Transactional(readOnly = true)
    public UserDto me(Long userId) {
        return toDto(requireUser(userId));
    }

    private static final Set<String> SUPPORTED_LANGUAGES = Set.of("zh-CN", "en");

    private static final Set<String> SUPPORTED_THEMES = Set.of("system", "light", "dark");

    @Transactional
    public UserDto updateProfile(Long userId, String nickname, String avatarUrl, String language, String theme) {
        User u = requireUser(userId);
        if (nickname != null && !nickname.trim().isEmpty()) {
            u.setNickname(nickname.trim());
        }
        if (avatarUrl != null) {
            String v = avatarUrl.trim();
            // 禁字母头像：单字母直接 400
            if (v.length() == 1 && Character.isLetter(v.charAt(0))) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", "头像不许使用单字母");
            }
            u.setAvatarUrl(v.isEmpty() ? null : v);
        }
        if (language != null) {
            String lang = language.trim();
            if (!SUPPORTED_LANGUAGES.contains(lang)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", "不支持的语言");
            }
            u.setLanguage(lang);
        }
        if (theme != null) {
            String th = theme.trim();
            if (!SUPPORTED_THEMES.contains(th)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "BAD_REQUEST", "不支持的主题");
            }
            u.setTheme(th);
        }
        return toDto(userRepository.save(u));
    }

    private String normalizeLanguage(String language) {
        return language == null ? "zh-CN" : language;
    }

    private String normalizeTheme(String theme) {
        return theme == null ? "system" : theme;
    }

    /* ==================== 改密码（敏感操作） ==================== */

    @Transactional
    public void changePassword(Long userId, String oldPassword, String newPassword) {
        User u = requireUser(userId);
        if (u.getPasswordHash() == null || !passwordService.matches(oldPassword, u.getPasswordHash())) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "原密码错误");
        }
        checkPasswordStrength(newPassword);
        u.setPasswordHash(passwordService.hash(newPassword));
        userRepository.save(u);
        // 撤销该用户所有其他会话
        revokeAllSessions(userId);
    }

    /* ==================== 改邮箱（敏感操作） ==================== */

    @Transactional
    public UserDto changeEmail(Long userId, String newEmail, String password) {
        User u = requireUser(userId);
        if (u.getPasswordHash() == null || !passwordService.matches(password, u.getPasswordHash())) {
            throw new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_CREDENTIALS", "密码错误");
        }
        newEmail = norm(newEmail).toLowerCase();
        if (userRepository.existsByEmail(newEmail)) {
            throw new ApiException(HttpStatus.CONFLICT, "EMAIL_EXISTS", "邮箱已被占用");
        }
        u.setEmail(newEmail);
        return toDto(userRepository.save(u));
    }

    /* ==================== 会话管理 ==================== */

    @Transactional(readOnly = true)
    public List<SessionDto> listSessions(Long userId) {
        List<SessionDto> result = new ArrayList<>();
        for (UserSession s : sessionRepository.findByUserIdOrderByCreatedAtDesc(userId)) {
            result.add(new SessionDto(s.getId(), s.getDeviceInfo(), s.getIp(),
                    s.getCreatedAt(), s.getExpiresAt(), !s.isRevoked()
                    && s.getExpiresAt().isAfter(LocalDateTime.now())));
        }
        return result;
    }

    @Transactional
    public void revokeSession(Long userId, Long sessionId) {
        UserSession s = sessionRepository.findById(sessionId)
                .filter(x -> x.getUser().getId().equals(userId))
                .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "NOT_FOUND", "会话不存在"));
        s.setRevoked(true);
        sessionRepository.save(s);
    }

    /* ==================== 内部 ==================== */

    private TokenPair issueTokens(User u, String deviceInfo, String ip) {
        JwtService.AccessToken at = jwtService.createAccessToken(u.getId(), u.getRole());
        JwtService.RefreshToken rt = jwtService.createRefreshToken(u.getId());
        UserSession s = new UserSession();
        s.setUser(u);
        s.setTokenJti(rt.jti());
        s.setAccessJti(at.jti());
        s.setDeviceInfo(deviceInfo == null ? null : deviceInfo.substring(0, Math.min(255, deviceInfo.length())));
        s.setIp(ip);
        s.setExpiresAt(LocalDateTime.now().plusSeconds(7 * 24 * 3600));
        sessionRepository.save(s);
        return new TokenPair(at.token(), rt.token(), 900);
    }

    private void revokeAllSessions(Long userId) {
        List<UserSession> actives = sessionRepository.findByUserIdAndRevokedFalse(userId);
        for (UserSession s : actives) {
            s.setRevoked(true);
        }
        sessionRepository.saveAll(actives);
    }

    private User requireUser(Long userId) {
        return userRepository.findById(userId)
                .filter(u -> "ACTIVE".equals(u.getStatus()))
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "INVALID_TOKEN", "用户不存在或已禁用"));
    }

    private UserDto toDto(User u) {
        return new UserDto(u.getId(), u.getEmail(), u.getNickname(), u.getAvatarUrl(), u.getRole(),
                normalizeLanguage(u.getLanguage()), normalizeTheme(u.getTheme()));
    }

    private String norm(String s) {
        return s == null ? "" : s.trim();
    }

    /** 密码强度：≥8 位，含字母和数字 */
    private void checkPasswordStrength(String password) {
        if (password == null || password.length() < 8
                || !password.matches(".*[A-Za-z].*") || !password.matches(".*[0-9].*")) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "WEAK_PASSWORD", "密码至少 8 位，且包含字母和数字");
        }
    }

    private void checkRateLimit(String key) {
        Attempt a = attempts.get(key);
        long now = System.currentTimeMillis() / 1000;
        if (a != null && now - a.windowStart < WINDOW_SECONDS && a.fails >= MAX_FAILS) {
            throw new ApiException(HttpStatus.TOO_MANY_REQUESTS, "TOO_MANY_ATTEMPTS", "尝试次数过多，请 15 分钟后再试");
        }
    }

    private void recordFail(String key) {
        long now = System.currentTimeMillis() / 1000;
        attempts.compute(key, (k, a) -> {
            if (a == null || now - a.windowStart >= WINDOW_SECONDS) {
                return new Attempt(1, now);
            }
            return new Attempt(a.fails + 1, a.windowStart);
        });
    }

    private record Attempt(int fails, long windowStart) {
    }
}
