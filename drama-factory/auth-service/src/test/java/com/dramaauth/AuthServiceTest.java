package com.dramaauth;

import com.dramaauth.exception.ApiException;
import com.dramaauth.service.AuthService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.test.context.TestPropertySource;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * auth-service 全流程测试（H2 内存库）。
 * 注意：JWT secret 由测试属性提供，绝不进仓库。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "AUTH_JWT_SECRET=test-secret-for-unit-tests-only-0123456789abcdef",
        "spring.datasource.url=jdbc:h2:mem:authtest;DB_CLOSE_DELAY=-1",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class AuthServiceTest {

    @Autowired
    private AuthService authService;

    @Autowired
    private com.dramaauth.repository.UserRepository userRepository;

    @Autowired
    private com.dramaauth.repository.SessionRepository sessionRepository;

    @Autowired
    private com.dramaauth.repository.OAuthAccountRepository oauthAccountRepository;

    @Test
    void register_firstUserIsAdmin() {
        sessionRepository.deleteAll();
        oauthAccountRepository.deleteAll();
        userRepository.deleteAll();
        AuthService.UserDto u = authService.register("admin@example.com", "Passw0rd1", "站长");
        assertThat(u.role()).isEqualTo("ADMIN");
        assertThat(u.email()).isEqualTo("admin@example.com");
    }

    @Test
    void register_secondUserIsNormal() {
        authService.register("a1@example.com", "Passw0rd1", "甲");
        AuthService.UserDto u = authService.register("b1@example.com", "Passw0rd1", "乙");
        assertThat(u.role()).isEqualTo("USER");
    }

    @Test
    void register_duplicateEmail_409() {
        authService.register("dup@example.com", "Passw0rd1", "甲");
        assertThatThrownBy(() -> authService.register("dup@example.com", "Passw0rd1", "乙"))
                .isInstanceOf(ApiException.class)
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.CONFLICT);
    }

    @Test
    void register_weakPassword_400() {
        assertThatThrownBy(() -> authService.register("w@example.com", "123", "弱"))
                .isInstanceOf(ApiException.class)
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.BAD_REQUEST);
        assertThatThrownBy(() -> authService.register("w2@example.com", "password", "弱"))
                .isInstanceOf(ApiException.class)
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.BAD_REQUEST);
    }

    @Test
    void login_issuesTokenPair() {
        authService.register("login@example.com", "Passw0rd1", "登");
        AuthService.TokenPair pair = authService.login("login@example.com", "Passw0rd1", "test", "127.0.0.1");
        assertThat(pair.accessToken().split("\\.")).hasSize(3);
        assertThat(pair.refreshToken().split("\\.")).hasSize(3);
        assertThat(pair.expiresIn()).isEqualTo(900);
    }

    @Test
    void login_wrongPassword_401_noEnum() {
        authService.register("e1@example.com", "Passw0rd1", "甲");
        // 用户不存在与密码错误返回同样的 401（防枚举）
        assertThatThrownBy(() -> authService.login("nouser@example.com", "Passw0rd1", "t", "1.1.1.1"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
        assertThatThrownBy(() -> authService.login("e1@example.com", "WrongPass1", "t", "1.1.1.1"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
    }

    @Test
    void login_rateLimit_429() {
        authService.register("rl@example.com", "Passw0rd1", "限");
        String ip = "9.9.9.9";
        for (int i = 0; i < 5; i++) {
            try {
                authService.login("rl@example.com", "WrongPass1", "t", ip);
            } catch (ApiException ignored) {
            }
        }
        assertThatThrownBy(() -> authService.login("rl@example.com", "WrongPass1", "t", ip))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.TOO_MANY_REQUESTS);
    }

    @Test
    void refresh_rotatesAndInvalidatesOld() {
        authService.register("rf@example.com", "Passw0rd1", "刷");
        AuthService.TokenPair p1 = authService.login("rf@example.com", "Passw0rd1", "t", "127.0.0.1");
        AuthService.TokenPair p2 = authService.refresh(p1.refreshToken());
        assertThat(p2.accessToken()).isNotEqualTo(p1.accessToken());
        // 旧 refresh 已作废
        assertThatThrownBy(() -> authService.refresh(p1.refreshToken()))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
        // 新 refresh 可用
        AuthService.TokenPair p3 = authService.refresh(p2.refreshToken());
        assertThat(p3.accessToken()).isNotBlank();
    }

    @Test
    void changePassword_requiresOld_andRevokesSessions() {
        AuthService.UserDto u = authService.register("pw@example.com", "Passw0rd1", "改");
        AuthService.TokenPair s1 = authService.login("pw@example.com", "Passw0rd1", "d1", "127.0.0.1");
        AuthService.TokenPair s2 = authService.login("pw@example.com", "Passw0rd1", "d2", "127.0.0.2");
        // 旧密码错误 → 401
        assertThatThrownBy(() -> authService.changePassword(u.id(), "WrongPass1", "NewPassw0rd2"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
        authService.changePassword(u.id(), "Passw0rd1", "NewPassw0rd2");
        // 新密码可登录
        authService.login("pw@example.com", "NewPassw0rd2", "t", "127.0.0.1");
        // 旧会话的 refresh 已被撤销
        assertThatThrownBy(() -> authService.refresh(s1.refreshToken()))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
        assertThatThrownBy(() -> authService.refresh(s2.refreshToken()))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.UNAUTHORIZED);
    }

    @Test
    void sessions_listAndRevoke() {
        AuthService.UserDto u = authService.register("ss@example.com", "Passw0rd1", "会");
        authService.login("ss@example.com", "Passw0rd1", "d1", "127.0.0.1");
        authService.login("ss@example.com", "Passw0rd1", "d2", "127.0.0.2");
        List<AuthService.SessionDto> list = authService.listSessions(u.id());
        assertThat(list).hasSize(2);
        authService.revokeSession(u.id(), list.get(0).id());
        List<AuthService.SessionDto> after = authService.listSessions(u.id());
        assertThat(after.stream().filter(AuthService.SessionDto::current).count()).isEqualTo(1);
    }

    @Test
    void profile_rejectsSingleLetterAvatar() {
        AuthService.UserDto u = authService.register("av@example.com", "Passw0rd1", "头");
        assertThatThrownBy(() -> authService.updateProfile(u.id(), null, "X", null))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.BAD_REQUEST);
        AuthService.UserDto ok = authService.updateProfile(u.id(), "新昵称",
                "https://example.com/avatar.png", null);
        assertThat(ok.nickname()).isEqualTo("新昵称");
    }

    @Autowired
    private com.dramaauth.service.OAuthService oauthService;

    @Test
    void oauth_unconfigured_501() {
        assertThatThrownBy(() -> oauthService.authUrl("google"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.NOT_IMPLEMENTED);
        assertThatThrownBy(() -> oauthService.authUrl("github"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.NOT_IMPLEMENTED);
        assertThatThrownBy(() -> oauthService.authUrl("apple"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.NOT_IMPLEMENTED);
    }

    @Test
    void profile_languageUpdate_ok() {
        AuthService.UserDto u = authService.register("lang1@example.com", "Passw0rd1", "用户一");
        AuthService.UserDto updated = authService.updateProfile(u.id(), null, null, "en");
        assertThat(updated.language()).isEqualTo("en");
        assertThat(updated.nickname()).isEqualTo("用户一");
    }

    @Test
    void profile_languageInvalid_400() {
        AuthService.UserDto u = authService.register("lang2@example.com", "Passw0rd1", "用户二");
        assertThatThrownBy(() -> authService.updateProfile(u.id(), null, null, "fr"))
                .matches(e -> ((ApiException) e).getStatus() == HttpStatus.BAD_REQUEST);
    }

    @Test
    void profile_languageNull_noChange() {
        AuthService.UserDto u = authService.register("lang3@example.com", "Passw0rd1", "用户三");
        authService.updateProfile(u.id(), null, null, "en");
        AuthService.UserDto updated = authService.updateProfile(u.id(), null, null, null);
        assertThat(updated.language()).isEqualTo("en");
    }

    @Test
    void profile_languageDefault_zhCN() {
        AuthService.UserDto u = authService.register("lang4@example.com", "Passw0rd1", "用户四");
        assertThat(u.language()).isEqualTo("zh-CN");
    }
}
