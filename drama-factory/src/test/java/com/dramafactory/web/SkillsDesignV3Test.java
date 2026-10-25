package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class SkillsDesignV3Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV3AfterV2() throws Exception {
        String html = read("static/skills.html");
        int v2 = html.indexOf("/skills-design-v2.css");
        int v3 = html.indexOf("/skills-design-v3.css");
        assertTrue(v2 >= 0, "missing skills-design-v2.css link");
        assertTrue(v3 > v2, "design layer v3 must be linked after v2");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/skills-design-v3.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversDetailPreAndJsDropsInlineImportant() throws Exception {
        String css = read("static/skills-design-v3.css");
        assertTrue(css.contains(".skill-detail-pre"), "missing skill-detail-pre selector");
        assertTrue(css.contains("border: 1px solid var(--border)"), "missing border rule");
        assertTrue(css.contains("white-space: pre-wrap"), "missing pre-wrap rule");
        String js = read("static/skills.js");
        assertTrue(js.contains("skill-detail-pre"), "js must add skill-detail-pre class");
        assertTrue(!js.contains("border-color: var(--border) !important"), "detail pre must not keep inline important border color");
        assertTrue(!js.contains("p-2 border rounded\" style=\"white-space: pre-wrap"), "detail pre must not keep tabler border classes plus inline style, v3 css owns the box");
    }
}
