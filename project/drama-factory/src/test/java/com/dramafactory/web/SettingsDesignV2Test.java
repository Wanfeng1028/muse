package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class SettingsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/settings.html");
        int harness = html.indexOf("/harness.css");
        int v1 = html.indexOf("/settings-design-v1.css");
        int v2 = html.indexOf("/settings-design-v2.css");
        assertTrue(harness >= 0, "missing harness.css link");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
        assertTrue(v2 > harness, "v2 must be linked after harness.css");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/settings-design-v2.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
        assertTrue(!css.contains("var(--hairline) solid"), "hairline token is a color, not a border width");
    }

    @Test
    void cssCoversRetryButton() throws Exception {
        String css = read("static/settings-design-v2.css");
        assertTrue(css.contains("#settings-retry"), "missing selector: #settings-retry");
        assertTrue(css.contains("font-size: 13px"), "missing 13px font-size");
        assertTrue(css.contains("border-radius: 8px"), "missing 8px radius");
    }
}
