package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class ImagesDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/images.html");
        int v1 = html.indexOf("/images-design-v1.css");
        int v2 = html.indexOf("/images-design-v2.css");
        assertTrue(v1 >= 0, "missing images-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndBanFree() throws Exception {
        String css = read("static/images-design-v2.css");
        assertEquals(3, css.chars().filter(c -> c == '{').count(), "expected 3 rules");
        assertEquals(css.chars().filter(c -> c == '{').count(), css.chars().filter(c -> c == '}').count(), "braces must balance");
        for (String banned : new String[] {"linear-gradient", "backdrop-filter", "!important", "Inter"}) {
            assertTrue(!css.contains(banned), "banned string present: " + banned);
        }
    }

    @Test
    void cssCoversKeySelectors() throws Exception {
        String css = read("static/images-design-v2.css");
        for (String sel : new String[] {".fld select", ".byok-preview", "#img-ref"}) {
            assertTrue(css.contains(sel), "missing selector: " + sel);
        }
    }
}
