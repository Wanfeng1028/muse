/*
 * 覆盖说明：
 * - com.dramafactory.config.CurrentUser#currentUserId 第 3 行 !(attrs instanceof ServletRequestAttributes) 的 true 臂
 *   → currentUser_noRequestContext_returnsLocal
 * - com.dramafactory.config.CurrentUser#currentUserId 第 8 行 request == null 的 true 臂
 *   → currentUser_nullRequest_returnsLocal
 * - com.dramafactory.model.PromptRecipe#onCreate 第 6 行 usageCount == null 的 true 臂
 *   与第 9 行 visibility == null 的 true 臂
 *   → promptRecipe_onCreate_defaultsNulls
 * - com.dramafactory.service.SceneService#delete 第 3 行 !existsById(id) 的 true 臂
 *   → sceneService_delete_missing_throws
 * - com.dramafactory.config.JwtVerifier#verify 中 !(exp instanceof Number) 的 true 臂
 *   → jwtVerifier_stringExp_rejected
 */
package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.config.JwtVerifier;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.SceneRepository;
import org.junit.jupiter.api.Test;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class BranchCatchUp2Test {

    @Test
    void currentUser_noRequestContext_returnsLocal() {
        RequestContextHolder.resetRequestAttributes();
        assertEquals("local", new CurrentUser().currentUserId());
    }

    @Test
    void currentUser_nullRequest_returnsLocal() {
        ServletRequestAttributes attrsMock = mock(ServletRequestAttributes.class);
        when(attrsMock.getRequest()).thenReturn(null);
        RequestContextHolder.setRequestAttributes(attrsMock);
        try {
            assertEquals("local", new CurrentUser().currentUserId());
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    @Test
    void promptRecipe_onCreate_defaultsNulls() {
        PromptRecipe r = new PromptRecipe();
        r.onCreate();
        assertEquals(0L, r.getUsageCount());
        assertEquals(RecipeVisibility.PUBLIC, r.getVisibility());
    }

    @Test
    void sceneService_delete_missing_throws() {
        SceneRepository repo = mock(SceneRepository.class);
        EpisodeRepository epRepo = mock(EpisodeRepository.class);
        SceneService service = new SceneService(repo, epRepo);
        when(repo.existsById(9L)).thenReturn(false);
        assertThrows(ResourceNotFoundException.class, () -> service.delete(9L));
    }

    private static String b64(String s) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(s.getBytes(StandardCharsets.UTF_8));
    }

    private static String signWithStringExp(String secret) throws Exception {
        String h = b64("{\"alg\":\"HS256\",\"typ\":\"JWT\"}");
        String p = b64("{\"sub\":\"42\",\"role\":\"USER\",\"jti\":\"t\",\"iat\":1700000000,\"exp\":\"9999999999\"}");
        Mac mac = Mac.getInstance("HmacSHA256");
        mac.init(new SecretKeySpec(secret.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
        String sig = Base64.getUrlEncoder().withoutPadding()
                .encodeToString(mac.doFinal((h + "." + p).getBytes(StandardCharsets.UTF_8)));
        return h + "." + p + "." + sig;
    }

    @Test
    void jwtVerifier_stringExp_rejected() throws Exception {
        String secret = "unit-test-secret-0123456789abcdef";
        JwtVerifier v = new JwtVerifier(secret);
        assertThat(v.verify(signWithStringExp(secret))).isNull();
    }
}
