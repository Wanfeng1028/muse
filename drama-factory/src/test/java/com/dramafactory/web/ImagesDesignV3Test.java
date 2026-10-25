package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ImagesDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesV3AfterV2() throws Exception {
        String html = read("static/images.html");
        int v2 = html.indexOf("/images-design-v2.css");
        int v3 = html.indexOf("/images-design-v3.css");
        assertTrue(v2 >= 0, "missing v2 link");
        assertTrue(v3 > v2, "v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/images-design-v3.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        assertTrue(css.contains(".img-gen-body"), "missing selector");
        assertTrue(css.contains("padding: 16px 20px"), "missing padding value");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void htmlMigrated() throws Exception {
        String html = read("static/images.html");
        assertTrue(!html.contains("padding:16px 20px"), "old inline padding still present");
        assertTrue(html.contains("img-gen-body"), "gen body class missing");
    }
}
