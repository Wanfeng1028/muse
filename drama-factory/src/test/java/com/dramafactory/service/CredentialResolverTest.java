package com.dramafactory.service;

import com.dramafactory.service.video.SurrogateAuthClient;
import org.junit.jupiter.api.Test;

import java.util.AbstractMap;
import java.util.LinkedHashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CredentialResolverTest {

    @Test
    void chatAuthWithKeyReturnsBearer() {
        SettingsService settings = mock(SettingsService.class);
        SurrogateAuthClient surrogate = mock(SurrogateAuthClient.class);
        Map<String, String> all = new LinkedHashMap<>();
        all.put("deepseek.api-key", "sk-test-1234");
        when(settings.loadAll()).thenReturn(all);

        CredentialResolver resolver = new CredentialResolver(settings, surrogate);
        Map.Entry<String, String> header = resolver.chatAuth();
        assertEquals("Authorization", header.getKey());
        assertEquals("Bearer sk-test-1234", header.getValue());
    }

    @Test
    void chatAuthWithoutKeyUsesSurrogate() {
        SettingsService settings = mock(SettingsService.class);
        SurrogateAuthClient surrogate = mock(SurrogateAuthClient.class);
        when(settings.loadAll()).thenReturn(new LinkedHashMap<>());
        Map.Entry<String, String> fixed = new AbstractMap.SimpleEntry<>("Authorization", "Bearer surrogate");
        when(surrogate.authHeader(anyString(), anyString())).thenReturn(fixed);

        CredentialResolver resolver = new CredentialResolver(settings, surrogate);
        Map.Entry<String, String> header = resolver.chatAuth();
        assertEquals("Bearer surrogate", header.getValue());
    }

    @Test
    void surrogateReturnsNullPropagates() {
        SettingsService settings = mock(SettingsService.class);
        SurrogateAuthClient surrogate = mock(SurrogateAuthClient.class);
        when(settings.loadAll()).thenReturn(new LinkedHashMap<>());
        when(surrogate.authHeader(anyString())).thenReturn(null);

        CredentialResolver resolver = new CredentialResolver(settings, surrogate);
        assertNull(resolver.agnesAuth("https://example.com"));
    }

    @Test
    void dashscopeWithKeyReturnsBearer() {
        SettingsService settings = mock(SettingsService.class);
        SurrogateAuthClient surrogate = mock(SurrogateAuthClient.class);
        Map<String, String> all = new LinkedHashMap<>();
        all.put("dashscope.api-key", "dash-xyz");
        when(settings.loadAll()).thenReturn(all);

        CredentialResolver resolver = new CredentialResolver(settings, surrogate);
        Map.Entry<String, String> header = resolver.dashscopeAuth("https://example.com");
        assertEquals("Bearer dash-xyz", header.getValue());
    }
}
