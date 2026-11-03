package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class QcDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterHarness() throws Exception {
        String html = read("static/qc.html");
        int app = html.indexOf("/app.css");
        int harness = html.indexOf("/harness.css");
        int layer = html.indexOf("/qc-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/qc-design-v1.css");
        assertEquals(15, css.chars().filter(c -> c == '{').count(), "expected 15 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--hairline) solid"), "hairline token is a color, not a border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/qc-design-v1.css");
        for (String sel : new String[] {".page-head h1", "#qcCard", ".card-title", "#qcStatusBadge", "#qcNote", "#approveBtn", "#rejectBtn"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
