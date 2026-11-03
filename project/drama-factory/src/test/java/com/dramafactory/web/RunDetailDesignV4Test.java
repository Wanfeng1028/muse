package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RunDetailDesignV4Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV4AfterV3() throws Exception {
        String html = read("static/run-detail.html");
        int v3 = html.indexOf("/run-detail-design-v3.css");
        int v4 = html.indexOf("/run-detail-design-v4.css");
        assertTrue(v3 >= 0, "missing v3 link");
        assertTrue(v4 > v3, "v4 must be linked after v3");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/run-detail-design-v4.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversDetailErrorIconAndJsHasNoIconInline() throws Exception {
        String css = read("static/run-detail-design-v4.css");
        assertTrue(css.contains("#detailBody .error-box svg"), "missing selector: #detailBody .error-box svg");
        assertTrue(css.contains("width: 15px"), "missing 15px width");
        assertTrue(css.contains("vertical-align: -2px"), "missing -2px vertical-align");
        String js = read("static/run-detail.js");
        assertTrue(!js.contains("width:15px;height:15px"), "error icon inline style must be gone");
        assertTrue(js.contains("data-lucide=\"alert-triangle\""), "icon element must remain");
    }
}
