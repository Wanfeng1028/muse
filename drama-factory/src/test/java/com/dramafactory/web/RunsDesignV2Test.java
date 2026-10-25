package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RunsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/runs.html");
        int v1 = html.indexOf("/runs-design-v1.css");
        int v2 = html.indexOf("/runs-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/runs-design-v2.css");
        assertEquals(2, css.chars().filter(c -> c == '{').count(), "expected 2 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversErrorIconAndEmpty() throws Exception {
        String css = read("static/runs-design-v2.css");
        assertTrue(css.contains(".error-box svg"), "missing selector: .error-box svg");
        assertTrue(css.contains("width: 15px"), "missing 15px width");
        assertTrue(css.contains("vertical-align: -2px"), "missing -2px vertical-align");
        assertTrue(css.contains("#planArea .empty"), "missing selector: #planArea .empty");
        assertTrue(css.contains("padding: 24px"), "missing 24px padding");
    }

    @Test
    void jsHasNoInlineStylesLeft() throws Exception {
        String js = read("static/runs.js");
        assertTrue(!js.contains("width:15px;height:15px"), "icon inline style must be gone");
        assertTrue(!js.contains("style=\"padding:24px\""), "empty inline padding must be gone");
    }
}
