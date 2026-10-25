package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class DeconstructDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterInlineStyle() throws Exception {
        String html = read("static/deconstruct.html");
        int app = html.indexOf("/app.css");
        int styleClose = html.indexOf("</style>");
        int layer = html.indexOf("/deconstruct-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(styleClose >= 0, "missing inline style block");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > styleClose, "design layer must be linked after inline style block");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/deconstruct-design-v1.css");
        assertEquals(14, css.chars().filter(c -> c == '{').count(), "expected 14 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--border) solid"), "border token is a color, not a border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/deconstruct-design-v1.css");
        for (String sel : new String[] {".dc-kicker", ".page-head h1", ".card", ".card-header h3", ".form-label", ".form-select", ".btn", "#dcEmpty", "#dcDetailCard h4", ".dc-timeline", ".dc-frame", ".dc-meta", ".dc-prompt"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
