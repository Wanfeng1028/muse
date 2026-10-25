package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class LoginDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterAppAndAuth() throws Exception {
        String html = read("static/login.html");
        int app = html.indexOf("/app.css");
        int auth = html.indexOf("/auth.css");
        int layer = html.indexOf("/login-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(auth >= 0, "missing auth.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > auth, "design layer must be linked after auth.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/login-design-v1.css");
        assertEquals(15, css.chars().filter(c -> c == '{').count(), "expected 15 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--border) solid") && !css.contains("var(--border-soft) solid"),
                "color token must not stand in for border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/login-design-v1.css");
        for (String sel : new String[] {
                ".auth-page", ".auth-wrap", ".login-hero h1", ".login-hero p",
                ".seg", ".seg a.on", "form.login-form", ".field input",
                ".field .eye-btn", ".form-error", ".btn-primary", ".forgot-row a",
                ".divider", ".btn-oauth", ".agree", ".modal-panel",
                ".modal-title", ".modal-text"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
