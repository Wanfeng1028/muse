package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ChatDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV3AfterV2() throws Exception {
        String html = read("static/chat.html");
        int v2 = html.indexOf("/chat-design-v2.css");
        int v3 = html.indexOf("/chat-design-v3.css");
        assertTrue(v2 >= 0, "missing v2 link");
        assertTrue(v3 > v2, "v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/chat-design-v3.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversBothBubblesAndJsHasNoMaxWidth() throws Exception {
        String css = read("static/chat-design-v3.css");
        assertTrue(css.contains(".chat-bubble-user"), "missing selector: .chat-bubble-user");
        assertTrue(css.contains(".chat-msg-assistant"), "missing selector: .chat-msg-assistant");
        assertTrue(css.contains("max-width: 75%"), "missing 75% max-width");
        String js = read("static/chat.js");
        assertTrue(!js.contains("style.maxWidth"), "bubble maxWidth assignment must be gone");
    }
}
