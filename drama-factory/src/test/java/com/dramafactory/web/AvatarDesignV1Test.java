package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AvatarDesignV1Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerAfterInlineStyle() throws Exception {
        String html = read("static/avatar.html");
        int harness = html.indexOf("/harness.css");
        int inlineStyle = html.indexOf("</style>");
        int layer = html.indexOf("/avatar-design-v1.css");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(inlineStyle >= 0, "missing inline style block");
        assertTrue(layer > harness, "design layer must be linked after harness.css");
        assertTrue(layer > inlineStyle, "design layer must be linked after inline style block");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/avatar-design-v1.css");
        assertEquals(15, css.chars().filter(c -> c == '{').count(), "expected 15 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--hairline) solid") && !css.contains("var(--hairline) dashed")
                && !css.contains("var(--border) solid") && !css.contains("var(--border) dashed"),
                "color token must not stand in for border width");
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/avatar-design-v1.css");
        for (String sel : new String[] {".page-head .page-title", ".page-head .page-sub", ".card-title", ".fld>label", ".fld textarea", ".fld select", ".byok-empty", ".gen-foot .btn"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
