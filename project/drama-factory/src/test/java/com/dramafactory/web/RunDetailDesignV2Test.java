package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class RunDetailDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/run-detail.html");
        int v1 = html.indexOf("/run-detail-design-v1.css");
        int v2 = html.indexOf("/run-detail-design-v2.css");
        assertTrue(v1 >= 0, "missing run-detail-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/run-detail-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversEmptyStatesAndJsDropsInlineStyles() throws Exception {
        String css = read("static/run-detail-design-v2.css");
        assertTrue(css.contains(".rund-empty-text"), "missing rund-empty-text selector");
        assertTrue(css.contains(".rund-no-preview"), "missing rund-no-preview selector");
        assertTrue(css.contains("padding: 24px"), "missing no-preview padding rule");
        assertTrue(css.contains("text-align: center"), "missing no-preview centering rule");
        String js = read("static/run-detail.js");
        assertTrue(js.contains("rund-empty-text"), "js must add rund-empty-text class");
        assertTrue(js.contains("rund-no-preview"), "js must add rund-no-preview class");
        assertTrue(!js.contains("style=\"font-size:13px\""), "no-shots empty line must not keep inline font size");
        assertTrue(!js.contains("style=\"padding:24px;text-align:center\""), "no-preview boxes must not keep inline padding and centering");
    }
}
