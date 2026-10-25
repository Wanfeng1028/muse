package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class MusicDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterInlineStyle() throws Exception {
        String html = read("static/music.html");
        int app = html.indexOf("/app.css");
        int harness = html.indexOf("/harness.css");
        int styleClose = html.indexOf("</style>");
        int layer = html.indexOf("/music-design-v1.css");
        assertTrue(app >= 0, "missing app.css link");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(styleClose >= 0, "missing inline style block");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
        assertTrue(layer > styleClose, "design layer must be linked after inline style block");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/music-design-v1.css");
        assertEquals(13, css.chars().filter(c -> c == '{').count(), "expected 13 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--hairline) solid"), "hairline token is a color, not a border width");
        assertTrue(!css.contains("var(--border) solid"), "border token is a color, not a border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/music-design-v1.css");
        for (String sel : new String[] {".page-head .page-title", ".page-head .page-sub", "section.card", ".card-head .card-title", ".fld>label", ".fld input[type=text]", ".gen-foot .btn", ".byok-empty"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
