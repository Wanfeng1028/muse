package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AgentsDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV3AfterV2() throws Exception {
        String html = read("static/agents.html");
        int v2 = html.indexOf("/agents-design-v2.css");
        int v3 = html.indexOf("/agents-design-v3.css");
        assertTrue(v2 >= 0, "missing agents-design-v2.css link");
        assertTrue(v3 > v2, "design layer v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/agents-design-v3.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversKeyRowAndHtmlDropsInlineStyle() throws Exception {
        String css = read("static/agents-design-v3.css");
        assertTrue(css.contains(".pv-key-row"), "missing pv-key-row selector");
        assertTrue(css.contains("display: flex"), "missing key row flex rule");
        assertTrue(css.contains("gap: 8px"), "missing key row gap rule");
        String html = read("static/agents.html");
        assertTrue(html.contains("class=\"pv-key-row\""), "key row div must carry pv-key-row class");
        assertTrue(!html.contains("style=\"display:flex;gap:8px\""), "key row div must not keep inline flex style");
    }
}
