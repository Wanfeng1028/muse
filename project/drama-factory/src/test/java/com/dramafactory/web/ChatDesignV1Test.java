package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ChatDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterApp() throws Exception {
        String html = read("static/chat.html");
        int app = html.indexOf("/app.css");
        int layer = html.indexOf("/chat-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/chat-design-v1.css");
        assertEquals(10, css.chars().filter(c -> c == '{').count(), "expected 10 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--border) solid") && !css.contains("var(--border-soft) solid"),
                "color token must not stand in for border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/chat-design-v1.css");
        for (String sel : new String[] {".page-head h1", ".card", ".form-label", ".form-select", "#chatLog", ".chip", ".quota-note", "#toast"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
