package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AgentsDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterHeadInlineStyle() throws Exception {
        String html = read("static/agents.html");
        int app = html.indexOf("/app.css");
        int harness = html.indexOf("/harness.css");
        int styleClose = html.indexOf("</style>");
        int layer = html.indexOf("/agents-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
        assertTrue(styleClose >= 0 && layer > styleClose, "design layer must be linked after the head inline style block");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/agents-design-v1.css");
        assertEquals(18, css.chars().filter(c -> c == '{').count(), "expected 18 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("#"), "no hex colors or id selectors in this layer");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/agents-design-v1.css");
        for (String sel : new String[] {".page-title", ".card-title", ".agent-card", ".meta-key", ".meta-val", ".template-pre"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
