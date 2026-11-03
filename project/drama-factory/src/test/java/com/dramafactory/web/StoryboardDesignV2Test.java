package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class StoryboardDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/storyboard.html");
        int v1 = html.indexOf("/storyboard-design-v1.css");
        int v2 = html.indexOf("/storyboard-design-v2.css");
        assertTrue(v1 >= 0, "missing storyboard-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/storyboard-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversInlineStylesAndJsHtmlDropInlineStyles() throws Exception {
        String css = read("static/storyboard-design-v2.css");
        assertTrue(css.contains(".sb-dialogue"), "missing sb-dialogue selector");
        assertTrue(css.contains("white-space: pre-wrap"), "missing dialogue pre-wrap rule");
        assertTrue(css.contains("#skillSelect"), "missing skillSelect selector");
        assertTrue(css.contains("max-width: 200px"), "missing skill select max-width rule");
        assertTrue(css.contains(".sb-toast-wrap"), "missing sb-toast-wrap selector");
        assertTrue(css.contains("z-index: 1080"), "missing toast z-index rule");
        String js = read("static/storyboard.js");
        assertTrue(js.contains("sb-dialogue"), "js must add sb-dialogue class");
        assertTrue(!js.contains("style=\"white-space:pre-wrap;\""), "dialogue must not keep inline pre-wrap");
        String html = read("static/storyboard.html");
        assertTrue(html.contains("sb-toast-wrap"), "html must add sb-toast-wrap class");
        assertTrue(!html.contains("style=\"max-width:200px\""), "skill select must not keep inline max-width");
        assertTrue(!html.contains("style=\"z-index: 1080;\""), "toast wrap must not keep inline z-index");
    }
}
