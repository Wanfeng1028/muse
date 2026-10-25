package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class MusicDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesV2AfterV1() throws Exception {
        String html = read("static/music.html");
        int v1 = html.indexOf("/music-design-v1.css");
        int v2 = html.indexOf("/music-design-v2.css");
        assertTrue(v1 >= 0, "missing v1 link");
        assertTrue(v2 > v1, "v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/music-design-v2.css");
        assertEquals(1, css.chars().filter(c -> c == '{').count(), "expected 1 rule");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        assertTrue(css.contains(".mus-gen-body"), "missing selector");
        assertTrue(css.contains("padding: 16px 20px"), "missing padding value");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void htmlMigrated() throws Exception {
        String html = read("static/music.html");
        assertTrue(!html.contains("padding:16px 20px"), "old inline padding still present");
        assertTrue(html.contains("mus-gen-body"), "gen body class missing");
    }
}
