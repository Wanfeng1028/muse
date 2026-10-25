package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RunDetailDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV3AfterV2() throws Exception {
        String html = read("static/run-detail.html");
        int v2 = html.indexOf("/run-detail-design-v2.css");
        int v3 = html.indexOf("/run-detail-design-v3.css");
        assertTrue(v2 >= 0, "missing run-detail-design-v2.css link");
        assertTrue(v3 > v2, "design layer v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/run-detail-design-v3.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversPageHeadAndHtmlDropsInlineStyles() throws Exception {
        String css = read("static/run-detail-design-v3.css");
        assertTrue(css.contains(".rund-head-main"), "missing rund-head-main selector");
        assertTrue(css.contains("flex: 1"), "missing head flex rule");
        assertTrue(css.contains("min-width: 0"), "missing head min-width rule");
        assertTrue(css.contains(".rund-meta"), "missing rund-meta selector");
        assertTrue(css.contains("margin-top: 6px"), "missing meta margin rule");
        String html = read("static/run-detail.html");
        assertTrue(html.contains("class=\"rund-head-main\""), "head div must carry rund-head-main class");
        assertTrue(html.contains("class=\"meta-grid rund-meta\""), "runMeta must carry rund-meta class");
        assertTrue(!html.contains("style=\"flex:1;min-width:0\""), "head div must not keep inline flex style");
        assertTrue(!html.contains("style=\"margin-top:6px\""), "runMeta must not keep inline margin style");
    }
}
