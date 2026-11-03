package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class CanvasDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterApp() throws Exception {
        String html = read("static/canvas.html");
        int app = html.indexOf("/app.css");
        int layer = html.indexOf("/canvas-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/canvas-design-v1.css");
        assertEquals(6, css.chars().filter(c -> c == '{').count(), "expected 6 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--border) solid") && !css.contains("var(--border-soft) solid"),
                "color token must not stand in for border width");
        for (String forbidden : new String[] {"timeline-strip", "shot-card", "modal-box", "toast-item", "field-row", "empty-block", "badge-status"}) {
            assertTrue(!css.contains(forbidden), "layer must not restyle inline-covered component: " + forbidden);
        }
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/canvas-design-v1.css");
        for (String sel : new String[] {".page-head h1", ".card", ".card-title", ".card-body p.text-secondary", ".page-head-actions .btn", ".canvas-toolbar .form-select"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
