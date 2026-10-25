package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class PromptsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/prompts.html");
        int v1 = html.indexOf("/prompts-design-v1.css");
        int v2 = html.indexOf("/prompts-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/prompts-design-v2.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversDetailPreAndHtmlHasNoOldInline() throws Exception {
        String css = read("static/prompts-design-v2.css");
        assertTrue(css.contains(".prompt-detail-pre"), "missing selector: .prompt-detail-pre");
        assertTrue(css.contains("white-space: pre-wrap"), "missing pre-wrap value");
        String html = read("static/prompts.html");
        assertTrue(html.contains("class=\"prompt-detail-pre\""), "pre must carry prompt-detail-pre class");
        assertTrue(!html.contains("<pre id=\"promptDetailContent\" style="), "old inline pre-wrap must be gone");
    }
}
