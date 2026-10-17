package com.dramafactory;

import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.SettingsService;
import com.dramafactory.service.video.SurrogateAuthClient;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;

import java.util.AbstractMap;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * CredentialResolver 深度集成测试：覆盖设置中心优先、surrogate 回退、空值边界、幂等与并发读取。
 */
@SpringBootTest(classes = com.dramafactory.service.CredentialResolver.class)
public class CredentialResolverDeepTest {

    @Autowired
    private CredentialResolver credentialResolver;

    @MockBean
    private SettingsService settingsService;

    @MockBean
    private SurrogateAuthClient surrogateAuthClient;

    private Map<String, String> settings;

    @BeforeEach
    public void setUp() {
        settings = new HashMap<>();
        when(settingsService.loadAll()).thenAnswer(invocation -> new HashMap<>(settings));
    }

    @Test
    public void chatAuth_usesSettingsKeyWhenPresent() {
        // given: 设置中心填了 deepseek.api-key
        settings.put("deepseek.api-key", "sk-deepseek-abc");
        // when: 解析聊天鉴权头
        Map.Entry<String, String> header = credentialResolver.chatAuth();
        // then: 直接使用设置 key，不访问 surrogate
        assertNotNull(header);
        assertEquals("Authorization", header.getKey());
        assertEquals("Bearer sk-deepseek-abc", header.getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void chatAuth_fallsBackToSurrogateWhenNoKey() {
        // given: 设置中心没有 deepseek key，surrogate 返回一个头
        Map.Entry<String, String> surrogateHeader =
                new AbstractMap.SimpleEntry<>("Authorization", "Bearer surrogate-token");
        when(surrogateAuthClient.authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi")).thenReturn(surrogateHeader);
        // when: 解析聊天鉴权头
        Map.Entry<String, String> header = credentialResolver.chatAuth();
        // then: 返回 surrogate 的头，且调用参数正确
        assertNotNull(header);
        assertEquals("Bearer surrogate-token", header.getValue());
        verify(surrogateAuthClient, times(1)).authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi");
    }

    @Test
    public void dashscopeAuth_usesSettingsKeyAndSkipsSurrogate() {
        // given: 设置中心填了 dashscope.api-key
        settings.put("dashscope.api-key", "sk-dash-001");
        // when: 解析 dashscope 鉴权头
        Map.Entry<String, String> header = credentialResolver.dashscopeAuth("https://dashscope.aliyuncs.com/api/v1");
        // then: 用设置 key，且 surrogate 未被调用
        assertNotNull(header);
        assertEquals("Bearer sk-dash-001", header.getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void agnesAuth_fallsBackToSurrogateSingleArg() {
        // given: 设置中心无 agnes key，surrogate 单参重载返回头
        Map.Entry<String, String> surrogateHeader =
                new AbstractMap.SimpleEntry<>("Authorization", "Bearer agnes-surrogate");
        when(surrogateAuthClient.authHeader("https://agnes.example.com/v1")).thenReturn(surrogateHeader);
        // when: 解析 agnes 鉴权头
        Map.Entry<String, String> header = credentialResolver.agnesAuth("https://agnes.example.com/v1");
        // then: 返回 surrogate 的头，并校验单参重载被调用
        assertNotNull(header);
        assertEquals("Bearer agnes-surrogate", header.getValue());
        verify(surrogateAuthClient, times(1)).authHeader("https://agnes.example.com/v1");
    }

    @Test
    public void novaiAuth_fallsBackToSurrogateWithCustomChannel() {
        // given: 设置中心无 novai key
        Map.Entry<String, String> surrogateHeader =
                new AbstractMap.SimpleEntry<>("Authorization", "Bearer novai-surrogate");
        when(surrogateAuthClient.authHeader("https://novai.example.com/v1", "custom.novai-api"))
                .thenReturn(surrogateHeader);
        // when: 解析 novai 鉴权头
        Map.Entry<String, String> header = credentialResolver.novaiAuth("https://novai.example.com/v1");
        // then: 走 custom.novai-api 通道
        assertNotNull(header);
        assertEquals("Bearer novai-surrogate", header.getValue());
        verify(surrogateAuthClient, times(1)).authHeader("https://novai.example.com/v1", "custom.novai-api");
    }

    @Test
    public void dashscopeByokAuth_prefersCardKeyOverSettings() {
        // given: 卡片 key 与设置 key 同时存在
        settings.put("dashscope.api-key", "sk-settings-value");
        // when: 用卡片 key 解析 BYOK 鉴权头
        Map.Entry<String, String> header = credentialResolver.dashscopeByokAuth("  sk-card-value  ", "https://x.example.com");
        // then: 卡片 key 优先，且被 trim
        assertNotNull(header);
        assertEquals("Bearer sk-card-value", header.getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void dashscopeByokAuth_blankCardFallsBackToSettings() {
        // given: 卡片 key 为空白，设置中心有 key
        settings.put("dashscope.api-key", "sk-from-settings");
        // when: 用空白卡片 key 解析
        Map.Entry<String, String> header = credentialResolver.dashscopeByokAuth("   ", "https://x.example.com");
        // then: 落到设置中心 key，不调用 surrogate
        assertNotNull(header);
        assertEquals("Bearer sk-from-settings", header.getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void minimaxAuth_returnsNullWhenNoKeyAnywhere() {
        // given: 卡片 key 为空且设置中心没有 minimax key
        // when: 解析 minimax 鉴权头
        Map.Entry<String, String> header = credentialResolver.minimaxAuth(null);
        // then: 无凭证返回 null，且不经过 surrogate（minimax 没有 surrogate 通道）
        assertNull(header);
        verify(surrogateAuthClient, times(0)).authHeader(anyString());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void minimaxAuth_trimsCardKeyAndIgnoresSettings() {
        // given: 卡片 key 前后带空格，设置中心另有 key
        settings.put("minimax.api-key", "sk-settings-minimax");
        // when: 解析 minimax 鉴权头
        Map.Entry<String, String> header = credentialResolver.minimaxAuth("  sk-card-minimax  ");
        // then: 使用 trim 后的卡片 key，忽略设置值
        assertNotNull(header);
        assertEquals("Bearer sk-card-minimax", header.getValue());
    }

    @Test
    public void didAuth_producesBasicHeaderWithKeyAsUsername() {
        // given: 卡片 key 为 did-card-key
        // when: 解析 D-ID 鉴权头
        Map.Entry<String, String> header = credentialResolver.didAuth("did-card-key");
        // then: 生成 Basic 头，用户名是 key、密码为空
        assertNotNull(header);
        assertEquals("Authorization", header.getKey());
        String expected = "Basic " + java.util.Base64.getEncoder()
                .encodeToString("did-card-key:".getBytes(java.nio.charset.StandardCharsets.UTF_8));
        assertEquals(expected, header.getValue());
    }

    @Test
    public void didAuth_returnsNullWhenNoKeyAnywhere() {
        // given: 卡片 key 为 null 且设置中心无 did key
        // when: 解析 D-ID 鉴权头
        Map.Entry<String, String> header = credentialResolver.didAuth(null);
        // then: 无凭证返回 null
        assertNull(header);
        assertEquals(null, header);
    }

    @Test
    public void readKey_treatsBlankSettingValueAsMissing() {
        // given: 设置中心里 deepseek key 是一串空格
        settings.put("deepseek.api-key", "   ");
        Map.Entry<String, String> surrogateHeader =
                new AbstractMap.SimpleEntry<>("Authorization", "Bearer fallback");
        when(surrogateAuthClient.authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi")).thenReturn(surrogateHeader);
        // when: 解析聊天鉴权头
        Map.Entry<String, String> header = credentialResolver.chatAuth();
        // then: 空白值被视为缺失，走 surrogate 回退
        assertNotNull(header);
        assertEquals("Bearer fallback", header.getValue());
        verify(surrogateAuthClient, times(1)).authHeader(
                "https://chatapi.weixin.qq.com/openai/v1/chat/completions",
                "custom.weixin-chatapi");
    }

    @Test
    public void chatAuth_isIdempotentAcrossRepeatedCalls() {
        // given: 设置中心有 deepseek key
        settings.put("deepseek.api-key", "sk-repeat");
        // when: 连续调用两次
        Map.Entry<String, String> first = credentialResolver.chatAuth();
        Map.Entry<String, String> second = credentialResolver.chatAuth();
        // then: 两次结果一致，且 surrogate 从未被调用
        assertNotNull(first);
        assertNotNull(second);
        assertEquals(first.getValue(), second.getValue());
        assertEquals("Bearer sk-repeat", second.getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void concurrentReads_doNotCorruptResult() throws Exception {
        // given: 设置中心有 dashscope key，两个线程同时读
        settings.put("dashscope.api-key", "sk-concurrent");
        final Map.Entry<String, String>[] results = new Map.Entry[2];
        Thread t1 = new Thread(() -> results[0] = credentialResolver.dashscopeAuth("https://a.example.com"));
        Thread t2 = new Thread(() -> results[1] = credentialResolver.dashscopeAuth("https://a.example.com"));
        // when: 并发执行
        t1.start();
        t2.start();
        t1.join();
        t2.join();
        // then: 两个结果都非空且值一致，surrogate 未被调用
        assertNotNull(results[0]);
        assertNotNull(results[1]);
        assertEquals(results[0].getValue(), results[1].getValue());
        assertEquals("Bearer sk-concurrent", results[0].getValue());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void settingsServiceException_propagatesToCaller() {
        // given: settingsService.loadAll 抛异常
        when(settingsService.loadAll()).thenThrow(new IllegalStateException("settings unavailable"));
        // when / then: 异常向上传播，调用方拿到明确错误
        IllegalStateException ex = org.junit.jupiter.api.Assertions.assertThrows(
                IllegalStateException.class, () -> credentialResolver.chatAuth());
        assertEquals("settings unavailable", ex.getMessage());
        verify(surrogateAuthClient, times(0)).authHeader(anyString(), anyString());
    }

    @Test
    public void surrogateException_propagatesToCaller() {
        // given: 设置中心无 key，surrogate 抛异常
        when(surrogateAuthClient.authHeader(eq("https://agnes.example.com/v1"))).thenThrow(
                new RuntimeException("surrogate down"));
        // when / then: 异常向上传播
        RuntimeException ex = org.junit.jupiter.api.Assertions.assertThrows(
                RuntimeException.class, () -> credentialResolver.agnesAuth("https://agnes.example.com/v1"));
        assertEquals("surrogate down", ex.getMessage());
        verify(surrogateAuthClient, times(1)).authHeader("https://agnes.example.com/v1");
    }
}