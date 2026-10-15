package com.dramafactory.service;

import com.dramafactory.service.video.SurrogateAuthClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * CredentialResolver 分支覆盖测试。
 *
 * <p>不启动 Spring，纯 Mockito 单元测试。</p>
 */
class CredentialResolverBranchTest {

    private SettingsService settings;
    private SurrogateAuthClient surrogate;
    private CredentialResolver resolver;
    private Map<String, String> store;

    @BeforeEach
    void setUp() {
        settings = Mockito.mock(SettingsService.class);
        surrogate = Mockito.mock(SurrogateAuthClient.class);
        store = new LinkedHashMap<>();
        when(settings.loadAll()).thenReturn(store);
        resolver = new CredentialResolver(settings, surrogate);
    }

    // ---------- dashscopeAuth ----------

    /**
     * dashscopeAuth 有 key 分支：覆盖 L61（key != null）与 L108（readKey trim）。
     * settings 中 "dashscope.api-key" 带前后空格，应被 trim 后拼接。
     */
    @Test
    void dashscopeAuth_withKeyWithSpaces_returnsBearerTrimmed() {
        store.put("dashscope.api-key", " sk-dash ");
        Map.Entry<String, String> result = resolver.dashscopeAuth("https://example.com/v1");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer sk-dash", result.getValue());
        verify(surrogate, never()).authHeader(anyString(), anyString());
    }

    /**
     * dashscopeAuth 无 key 分支：覆盖 L61（key == null）→ L62（走 surrogate 双参版本）。
     */
    @Test
    void dashscopeAuth_withoutKey_fallsBackToSurrogate() {
        Map.Entry<String, String> expected = Map.entry("Authorization", "Bearer surrogate-dash");
        when(surrogate.authHeader("https://example.com/v1", "custom.qwen-cloud-cn")).thenReturn(expected);

        Map.Entry<String, String> result = resolver.dashscopeAuth("https://example.com/v1");

        assertEquals(expected, result);
        verify(surrogate).authHeader("https://example.com/v1", "custom.qwen-cloud-cn");
    }

    // ---------- agnesAuth ----------

    /**
     * agnesAuth 有 key 分支：覆盖 L71（key != null）。
     */
    @Test
    void agnesAuth_withKey_returnsBearer() {
        store.put("agnes.api-key", "sk-agnes");
        Map.Entry<String, String> result = resolver.agnesAuth("https://agnes.example/v1");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer sk-agnes", result.getValue());
        verify(surrogate, never()).authHeader(anyString());
    }

    /**
     * agnesAuth 无 key 分支：覆盖 L71（key == null）→ L72（surrogate 单参版本）。
     */
    @Test
    void agnesAuth_withoutKey_fallsBackToSurrogateSingleArg() {
        Map.Entry<String, String> expected = Map.entry("Authorization", "Bearer surrogate-agnes");
        when(surrogate.authHeader("https://agnes.example/v1")).thenReturn(expected);

        Map.Entry<String, String> result = resolver.agnesAuth("https://agnes.example/v1");

        assertEquals(expected, result);
        verify(surrogate).authHeader("https://agnes.example/v1");
    }

    // ---------- dashscopeByokAuth ----------

    /**
     * dashscopeByokAuth 卡片 key 分支：覆盖 L85（cardKey != null && !isBlank）。
     * 应完全跳过 settings.loadAll()。
     */
    @Test
    void dashscopeByokAuth_withCardKey_skipsSettings() {
        Map.Entry<String, String> result = resolver.dashscopeByokAuth(" card-k1 ", "https://example.com/v1");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer card-k1", result.getValue());
        verify(settings, never()).loadAll();
        verify(surrogate, never()).authHeader(anyString(), anyString());
    }

    /**
     * dashscopeByokAuth cardKey == null：覆盖 L85 短路，走 L86 settings key 分支。
     */
    @Test
    void dashscopeByokAuth_nullCardKey_usesSettingsKey() {
        store.put("dashscope.api-key", "sk-settings-dash");
        Map.Entry<String, String> result = resolver.dashscopeByokAuth(null, "https://example.com/v1");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer sk-settings-dash", result.getValue());
        verify(surrogate, never()).authHeader(anyString(), anyString());
    }

    /**
     * dashscopeByokAuth cardKey == ""：覆盖 L85 isBlank 短路，走 L86 settings key 分支。
     */
    @Test
    void dashscopeByokAuth_blankCardKey_usesSettingsKey() {
        store.put("dashscope.api-key", "sk-settings-dash");
        Map.Entry<String, String> result = resolver.dashscopeByokAuth("", "https://example.com/v1");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer sk-settings-dash", result.getValue());
        verify(surrogate, never()).authHeader(anyString(), anyString());
    }

    /**
     * dashscopeByokAuth 空白 cardKey + settings 空：覆盖 L86（key == null）→ L87（surrogate 双参）。
     */
    @Test
    void dashscopeByokAuth_blankCardKeyAndEmptySettings_fallsBackToSurrogate() {
        Map.Entry<String, String> expected = Map.entry("Authorization", "Bearer surrogate-byok");
        when(surrogate.authHeader("https://example.com/v1", "custom.qwen-cloud-cn")).thenReturn(expected);

        Map.Entry<String, String> result = resolver.dashscopeByokAuth("   ", "https://example.com/v1");

        assertEquals(expected, result);
        verify(surrogate).authHeader("https://example.com/v1", "custom.qwen-cloud-cn");
    }

    // ---------- minimaxAuth ----------

    /**
     * minimaxAuth 卡片 key 分支：覆盖 L96（cardKey != null && !isBlank）与 L97（key != null）。
     */
    @Test
    void minimaxAuth_withCardKey_returnsBearerTrimmed() {
        Map.Entry<String, String> result = resolver.minimaxAuth(" mk1 ");
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer mk1", result.getValue());
        verify(settings, never()).loadAll();
    }

    /**
     * minimaxAuth cardKey == null 走 settings 分支：覆盖 L96 短路 → L97（key != null）。
     */
    @Test
    void minimaxAuth_nullCardKey_usesSettingsKey() {
        store.put("minimax.api-key", "sk-minimax-settings");
        Map.Entry<String, String> result = resolver.minimaxAuth(null);
        assertEquals("Authorization", result.getKey());
        assertEquals("Bearer sk-minimax-settings", result.getValue());
    }

    /**
     * minimaxAuth 无任何 key：覆盖 L96 短路 + L97（key == null）→ L98 返回 null。
     */
    @Test
    void minimaxAuth_noKeys_returnsNull() {
        assertNull(resolver.minimaxAuth(null));
    }

    // ---------- didAuth ----------

    /**
     * didAuth 卡片 key 分支：覆盖 L100（cardKey != null && !isBlank）与 L101/L102（Basic 编码）。
     */
    @Test
    void didAuth_withCardKey_returnsBasicEncoded() {
        String expected = "Basic " + Base64.getEncoder()
                .encodeToString(("did-k" + ":").getBytes(StandardCharsets.UTF_8));
        Map.Entry<String, String> result = resolver.didAuth("did-k");
        assertEquals("Authorization", result.getKey());
        assertEquals(expected, result.getValue());
        verify(settings, never()).loadAll();
    }

    /**
     * didAuth cardKey == null 走 settings 分支：覆盖 L100 短路 → L101（key != null）→ L102。
     */
    @Test
    void didAuth_nullCardKey_usesSettingsKey() {
        store.put("did.api-key", "did-s");
        String expected = "Basic " + Base64.getEncoder()
                .encodeToString(("did-s" + ":").getBytes(StandardCharsets.UTF_8));
        Map.Entry<String, String> result = resolver.didAuth(null);
        assertEquals("Authorization", result.getKey());
        assertEquals(expected, result.getValue());
    }

    /**
     * didAuth 无任何 key：覆盖 L101（key == null）→ L102 返回 null。
     */
    @Test
    void didAuth_noKeys_returnsNull() {
        assertNull(resolver.didAuth(null));
    }

    // ---------- readKey 空白值 ----------

    /**
     * readKey 空白值分支：覆盖 L108（value.isBlank()）→ 返回 null，进而 chatAuth 走 surrogate。
     */
    @Test
    void chatAuth_blankSettingsValue_fallsBackToSurrogate() {
        store.put("deepseek.api-key", "   ");
        Map.Entry<String, String> expected = Map.entry("Authorization", "Bearer surrogate-chat");
        when(surrogate.authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi")).thenReturn(expected);

        Map.Entry<String, String> result = resolver.chatAuth();

        assertEquals(expected, result);
        verify(surrogate).authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi");
    }
}
