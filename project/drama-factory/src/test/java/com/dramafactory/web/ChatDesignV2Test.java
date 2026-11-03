package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ChatDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/chat.html");
        int v1 = html.indexOf("/chat-design-v1.css");
        int v2 = html.indexOf("/chat-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/chat-design-v2.css");
        assertEquals(2, css.chars().filter(c -> c == '{').count(), "expected 2 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversFieldAndLog() throws Exception {
        String css = read("static/chat-design-v2.css");
        assertTrue(css.contains(".chat-field"), "missing selector: .chat-field");
        assertTrue(css.contains("min-width: 200px"), "missing 200px min-width");
        assertTrue(css.contains("#chatLog"), "missing selector: #chatLog");
        assertTrue(css.contains("min-height: 320px"), "missing 320px min-height");
        assertTrue(css.contains("max-height: 52vh"), "missing 52vh max-height");
        assertTrue(css.contains("overflow-y: auto"), "missing overflow-y auto");
    }

    @Test
    void htmlHasNoInlineStylesLeft() throws Exception {
        String html = read("static/chat.html");
        assertTrue(!html.contains("style=\"min-width:200px;\""), "field inline style must be gone");
        assertTrue(!html.contains("style=\"min-height:320px; max-height:52vh; overflow-y:auto;\""), "chatLog inline style must be gone");
        assertTrue(html.contains("flex-fill chat-field"), "field divs must carry chat-field class");
    }
}
