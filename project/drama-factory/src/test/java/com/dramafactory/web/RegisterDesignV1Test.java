package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RegisterDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterAppAndAuth() throws Exception {
        String html = read("static/register.html");
        int app = html.indexOf("/app.css");
        int auth = html.indexOf("/auth.css");
        int layer = html.indexOf("/register-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(auth >= 0, "missing auth.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > auth, "design layer must be linked after auth.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/register-design-v1.css");
        assertEquals(12, css.chars().filter(c -> c == '{').count(), "expected 13 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--border) solid") && !css.contains("var(--border-soft) solid"),
                "color token must not stand in for border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/register-design-v1.css");
        for (String sel : new String[] {
                ".auth-page .login-hero",
                ".auth-page .login-hero h1",
                ".auth-page .login-hero p",
                ".auth-page .seg",
                ".auth-page .seg a",
                ".auth-page .seg a.on",
                ".auth-page .field",
                ".auth-page .field input",
                ".auth-page .field .eye-btn",
                ".auth-page .pw-hint",
                ".auth-page .form-error",
                ".auth-page .btn-primary",
                ".auth-page .agree"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
