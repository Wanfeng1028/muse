package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class CostLedgerDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterAppCss() throws Exception {
        String html = read("static/cost-ledger.html");
        int app = html.indexOf("/app.css");
        int layer = html.indexOf("/cost-ledger-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/cost-ledger-design-v1.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversCostLedgerPageElements() throws Exception {
        String css = read("static/cost-ledger-design-v1.css");
        for (String selector : new String[]{"#budgetCard", "#budgetBar", "#kpiRow", "#trendChart", "#providerBars", "#entryRows"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
    }

    @Test
    void cssDoesNotChangeHeaderOrProviderRowLayout() throws Exception {
        String css = read("static/cost-ledger-design-v1.css");
        assertTrue(!css.contains(".card-header.justify-content-between"), "must not override trend header layout");
        assertTrue(!css.contains("#providerBars .d-flex {"), "must not override provider row layout");
    }
}
