package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class FinalsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/finals.html");
        int v1 = html.indexOf("/finals-design-v1.css");
        int v2 = html.indexOf("/finals-design-v2.css");
        assertTrue(v1 >= 0, "missing finals-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/finals-design-v2.css");
        assertEquals(13, css.chars().filter(c -> c == '{').count(), "expected 13 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/finals-design-v2.css");
        for (String sel : new String[] {"#finalsList article", "#finalsList article + article", "#finalsList article:last-child", "#finalsList .final-poster", "#finalsList .final-poster img", "#finalsList .final-body", "#finalsList .final-title", "#finalsList .final-meta", "#finalsList .final-sep", "#finalsList .final-note", "#finalsList .final-actions", "#finalsList .btn-quiet", "#finalsList .final-poster video"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }

    @Test
    void jsUsesClassesNotInlineStyles() throws Exception {
        String js = read("static/finals.js");
        assertTrue(!js.contains("cssText"), "finals.js must not set inline styles anymore");
        for (String cls : new String[] {"final-poster", "final-body", "final-title", "final-meta", "final-sep", "final-note", "final-actions"}) {
            assertTrue(js.contains(cls), "missing class hook: " + cls);
        }
    }
}
