package com.dramaauth.admin;

import com.dramaauth.service.AuthService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

/**
 * 管理员备份端点测试（MockMvc，拦截器链完整生效）。
 *
 * <p>用 MockMvc 替代 TestRestTemplate：RANDOM_PORT 下 TestRestTemplate 的 HTTP 客户端
 * 在本环境触发 Micrometer observation 的 status -1 断言，MockMvc 直接走 DispatcherServlet
 * 更稳定，且 AuthInterceptor 照样执行。</p>
 */
@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "AUTH_JWT_SECRET=dummy-backup-test-secret-0123456789abcdef",
        "spring.datasource.url=jdbc:h2:file:./target/backup-test-db/auth;DB_CLOSE_DELAY=-1",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class BackupEndpointTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private AuthService authService;

    private String registerAndLogin(String email, String password) {
        authService.register(email, password, email);
        AuthService.TokenPair tokenPair = authService.login(email, password, "test-device", "127.0.0.1");
        return tokenPair.accessToken();
    }

    @Test
    void backup_requiresAdmin() throws Exception {
        // 首个注册用户为 ADMIN，随后注册的为 USER
        registerAndLogin("admin@test.com", "admin-pass-123");
        String userToken = registerAndLogin("user@test.com", "user-pass-123");

        mockMvc.perform(post("/api/auth/admin/backup")
                        .header("Authorization", "Bearer " + userToken))
                .andExpect(status().isForbidden());
    }

    @Test
    void backup_adminSuccess() throws Exception {
        String adminToken = registerAndLogin("admin2@test.com", "admin-pass-456");

        mockMvc.perform(post("/api/auth/admin/backup")
                        .header("Authorization", "Bearer " + adminToken))
                .andExpect(status().isOk())
                .andExpect(content().contentTypeCompatibleWith("application/octet-stream"));
    }

    @Test
    void backup_noToken_unauthorized() throws Exception {
        mockMvc.perform(post("/api/auth/admin/backup"))
                .andExpect(status().isUnauthorized());
    }
}
