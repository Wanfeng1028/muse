package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ImagesDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterInlineStyle() throws Exception {
        String html = read("static/images.html");
        int harness = html.indexOf("/harness.css");
        int inlineEnd = html.indexOf("</style>");
        int layer = html.indexOf("/images-design-v1.css");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(inlineEnd > harness, "missing inline style block");
        assertTrue(layer > inlineEnd, "design layer must be linked after inline style block");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/images-design-v1.css");
        assertEquals(8, css.chars().filter(c -> c == '{').count(), "expected 8 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/images-design-v1.css");
        for (String sel : new String[] {".page-head h1", ".page-head .page-sub", ".card-title", ".fld > label", ".fld textarea", ".gen-foot", "#img-generate", "#img-hint"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
