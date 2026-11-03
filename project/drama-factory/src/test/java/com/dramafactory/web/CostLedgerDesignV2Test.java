package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class CostLedgerDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/cost-ledger.html");
        int v1 = html.indexOf("/cost-ledger-design-v1.css");
        int v2 = html.indexOf("/cost-ledger-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/cost-ledger-design-v2.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversNumericCells() throws Exception {
        String css = read("static/cost-ledger-design-v2.css");
        assertTrue(css.contains(".cl-num"), "missing selector: .cl-num");
        assertTrue(css.contains("font-variant-numeric: tabular-nums"), "missing tabular-nums");
    }

    @Test
    void jsUsesClassNotInlineStyle() throws Exception {
        String js = read("static/cost-ledger.js");
        long count = js.split("cl-num", -1).length - 1;
        assertEquals(4, count, "expected 4 cl-num usages in js");
        assertTrue(!js.contains("style=\"font-variant-numeric"), "inline tabular-nums style must be gone");
    }
}
