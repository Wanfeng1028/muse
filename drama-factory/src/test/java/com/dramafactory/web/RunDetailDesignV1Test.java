package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RunDetailDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterHarnessCss() throws Exception {
        String html = read("static/run-detail.html");
        int harness = html.indexOf("/harness.css");
        int layer = html.indexOf("/run-detail-design-v1.css");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/run-detail-design-v1.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversRunDetailPageElements() throws Exception {
        String css = read("static/run-detail-design-v1.css");
        for (String selector : new String[]{".page-head h1", "#runMeta.meta-grid .item", ".section .section-title", "#detailBody .timeline .step", ".step-head .name", ".step-head .dur", ".step-body .summary-box", "#artifactsArea .ep-card", ".ep-head .t", "#summaryArea.card", ".drawer-head .t"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
    }
}
