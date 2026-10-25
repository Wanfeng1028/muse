package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class UsageDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterInlineStyle() throws Exception {
        String html = read("static/usage.html");
        int app = html.indexOf("/app.css");
        int harness = html.indexOf("/harness.css");
        int styleClose = html.indexOf("</style>");
        int layer = html.indexOf("/usage-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
        assertTrue(styleClose >= 0 && layer > styleClose, "design layer must be linked after the inline style block");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/usage-design-v1.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversUsagePageElements() throws Exception {
        String css = read("static/usage-design-v1.css");
        for (String selector : new String[]{".page-head h1", ".filter-row", ".filter-row .form-select", "#btn-refresh", ".section-head h2", ".kpi-card", ".kpi-value", ".kpi-hint", ".bar-track", ".bar-value", ".state-box", "table.data-table th", "table.data-table td"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
    }
}
