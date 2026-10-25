package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ToolsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesV2AfterV1() throws Exception {
        String html = read("static/tools.html");
        int v1 = html.indexOf("/tools-design-v1.css");
        int v2 = html.indexOf("/tools-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/tools-design-v2.css");
        assertEquals(4, css.chars().filter(c -> c == '{').count(), "expected 4 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversSelectorsAndJsMigrated() throws Exception {
        String css = read("static/tools-design-v2.css");
        for (String sel : new String[] {"#tag-asset-list", "#rename-list", ".tool-asset-name", ".tool-log-cell"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
        String html = read("static/tools.html");
        assertTrue(!html.contains("style=\"max-height"), "old inline scroll style still present");
        String js = read("static/tools.js");
        assertTrue(js.contains("tool-asset-name"), "label class missing");
        assertTrue(js.contains("tool-log-cell"), "log cell class missing");
        for (String old : new String[] {"style.maxWidth", "style.textOverflow", "style.whiteSpace"}) {
            assertTrue(!js.contains(old), "old inline style assignment still present: " + old);
        }
        assertTrue(!js.contains("label.style.overflow"), "old label overflow assignment still present");
    }
}
