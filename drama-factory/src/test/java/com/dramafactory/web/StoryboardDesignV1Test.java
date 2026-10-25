package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class StoryboardDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterAppCss() throws Exception {
        String html = read("static/storyboard.html");
        int app = html.indexOf("/app.css");
        int layer = html.indexOf("/storyboard-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(layer > app, "design layer must be linked after app.css");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/storyboard-design-v1.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversStoryboardPageElements() throws Exception {
        String css = read("static/storyboard-design-v1.css");
        for (String selector : new String[]{".page-head h1", "#projectSelect.form-select", "#episodeSelect.form-select", "#slateGrid .shot-row", ".shot-no", ".shot-desc", ".shot-sub", ".shot-meta", ".shot-actions .btn", ".card-header .card-title", "#slateGrid .status-pill"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
    }
}
