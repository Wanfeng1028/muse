package com.dramafactory.config;

import java.io.IOException;
import java.net.Authenticator;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.URI;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

class EgressProxyConfigTest {

    private static final String[] PROXY_PROPERTIES = {
            "https.proxyHost",
            "https.proxyPort",
            "http.proxyHost",
            "http.proxyPort",
            "http.nonProxyHosts"
    };

    private ProxySelector savedProxySelector;
    private Authenticator savedAuthenticator;
    private String[] savedProperties;

    @BeforeEach
    void saveGlobalState() {
        savedProxySelector = ProxySelector.getDefault();
        savedAuthenticator = Authenticator.getDefault();
        savedProperties = new String[PROXY_PROPERTIES.length];
        for (int i = 0; i < PROXY_PROPERTIES.length; i++) {
            savedProperties[i] = System.getProperty(PROXY_PROPERTIES[i]);
        }
    }

    @AfterEach
    void restoreGlobalState() {
        for (int i = 0; i < PROXY_PROPERTIES.length; i++) {
            if (savedProperties[i] == null) {
                System.clearProperty(PROXY_PROPERTIES[i]);
            } else {
                System.setProperty(PROXY_PROPERTIES[i], savedProperties[i]);
            }
        }
        ProxySelector.setDefault(savedProxySelector);
        Authenticator.setDefault(savedAuthenticator);
    }

    @Test
    void noEnv_noSideEffects() {
        EgressProxyConfig.configureFromEnv(Map.of());

        for (String key : PROXY_PROPERTIES) {
            assertThat(System.getProperty(key)).isNull();
        }
        assertThat(ProxySelector.getDefault()).isSameAs(savedProxySelector);
        assertThat(Authenticator.getDefault()).isSameAs(savedAuthenticator);
    }

    @Test
    void blankUppercase_fallsBackToLowercase() {
        EgressProxyConfig.configureFromEnv(Map.of(
                "HTTPS_PROXY", "  ",
                "https_proxy", "http://p1:3128"));

        assertThat(System.getProperty("https.proxyHost")).isEqualTo("p1");
    }

    @Test
    void uppercasePreferredOverLowercase() {
        EgressProxyConfig.configureFromEnv(Map.of(
                "HTTPS_PROXY", "http://p1:3128",
                "https_proxy", "http://p2:3128"));

        assertThat(System.getProperty("https.proxyHost")).isEqualTo("p1");
    }

    @Test
    void malformedUri_noThrow() {
        assertThatCode(() -> EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://[::1")))
                .doesNotThrowAnyException();

        assertThat(System.getProperty("https.proxyHost")).isNull();
    }

    @Test
    void noHost_warnNoProxy() {
        assertThatCode(() -> EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http:///nopath")))
                .doesNotThrowAnyException();

        assertThat(System.getProperty("https.proxyHost")).isNull();
    }

    @Test
    void validNoAuth_setsProperties() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://proxy.example:8080"));

        assertThat(System.getProperty("https.proxyHost")).isEqualTo("proxy.example");
        assertThat(System.getProperty("https.proxyPort")).isEqualTo("8080");
        assertThat(System.getProperty("http.proxyHost")).isEqualTo("proxy.example");
        assertThat(System.getProperty("http.proxyPort")).isEqualTo("8080");
        assertThat(System.getProperty("http.nonProxyHosts")).isEqualTo("localhost|127.0.0.1");
    }

    @Test
    void defaultPort3128() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://proxy.example"));

        assertThat(System.getProperty("https.proxyPort")).isEqualTo("3128");
    }

    @Test
    void select_normalHost_returnsProxy() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://proxy.example:8080"));

        List<Proxy> selected = ProxySelector.getDefault().select(URI.create("https://example.com/x"));

        assertThat(selected).hasSize(1);
        Proxy proxy = selected.get(0);
        assertThat(proxy.type()).isEqualTo(Proxy.Type.HTTP);
        InetSocketAddress address = (InetSocketAddress) proxy.address();
        assertThat(address.getHostString()).isEqualTo("proxy.example");
        assertThat(address.getPort()).isEqualTo(8080);
    }

    @Test
    void select_localHosts_noProxy() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://proxy.example:8080"));

        ProxySelector selector = ProxySelector.getDefault();
        assertThat(selector.select(URI.create("http://localhost:8080/x"))).isEqualTo(List.of(Proxy.NO_PROXY));
        assertThat(selector.select(URI.create("http://127.0.0.1:8080/x"))).isEqualTo(List.of(Proxy.NO_PROXY));
        assertThat(selector.select(URI.create("http://[::1]/x"))).isEqualTo(List.of(Proxy.NO_PROXY));
    }

    @Test
    void userInfo_installsAuthenticator() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://u:p@proxy.example:8080"));

        assertThat(Authenticator.getDefault()).isNotNull();
    }

    @Test
    void connectFailed_noThrow() {
        EgressProxyConfig.configureFromEnv(Map.of("HTTPS_PROXY", "http://proxy.example:8080"));

        ProxySelector selector = ProxySelector.getDefault();
        assertThatCode(() -> selector.connectFailed(
                URI.create("https://example.com/"),
                new InetSocketAddress("proxy.example", 8080),
                new IOException("x")))
                .doesNotThrowAnyException();
    }
}
