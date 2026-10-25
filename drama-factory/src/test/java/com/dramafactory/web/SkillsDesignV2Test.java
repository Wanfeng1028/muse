package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class SkillsDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/skills.html");
        int v1 = html.indexOf("/skills-design-v1.css");
        int v2 = html.indexOf("/skills-design-v2.css");
        assertTrue(v1 >= 0, "missing skills-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/skills-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversInstalledRowsAndJsDropsInlineImportant() throws Exception {
        String css = read("static/skills-design-v2.css");
        assertTrue(css.contains("#installedList .installed-row"), "missing installed-row selector");
        assertTrue(css.contains("#installedList .installed-row:last-child"), "missing last-child selector");
        String js = read("static/skills.js");
        assertTrue(js.contains("installed-row"), "js must add installed-row class");
        assertTrue(!js.contains("border-color: var(--border-soft) !important"), "installed row must not keep inline important border color");
        assertTrue(!js.contains("border-bottom py-2 installed-row"), "installed row must not keep tabler border-bottom utility, v2 css owns the border");
    }
}
