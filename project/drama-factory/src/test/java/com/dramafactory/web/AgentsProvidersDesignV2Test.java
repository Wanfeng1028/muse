package com.dramafactory.web;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

class AgentsProvidersDesignV2Test {

    private static String read(String path) throws Exception {
        try (var in = new ClassPathResource(path).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void htmlReferencesDesignLayerV2AfterV1() throws Exception {
        String html = read("static/agents.html");
        int v1 = html.indexOf("/agents-design-v1.css");
        int v2 = html.indexOf("/agents-design-v2.css");
        assertTrue(v1 >= 0, "missing agents-design-v1.css link");
        assertTrue(v2 > v1, "design layer v2 must be linked after v1");
    }

    @Test
    void cssIsBalancedAndHasNoBannedDeclarations() throws Exception {
        String css = read("static/agents-design-v2.css");
        long open = css.chars().filter(c -> c == '{').count();
        long close = css.chars().filter(c -> c == '}').count();
        assertEquals(open, close, "unbalanced braces");
        assertTrue(!css.contains("linear-gradient"), "no gradients");
        assertTrue(!css.contains("backdrop-filter"), "no glassmorphism");
        assertTrue(!css.contains("!important"), "no important");
    }

    @Test
    void cssCoversProviderRowsAndJsDropsInlineStyles() throws Exception {
        String css = read("static/agents-design-v2.css");
        for (String selector : new String[]{".pv-preset-row", ".pv-name", ".pv-head-actions", ".pv-meta", ".pv-model-add-row", ".pv-test-result", ".pv-model-row", ".pv-model-id", ".pv-model-name", ".pv-model-id-text", ".pv-model-actions", ".pv-test-fail"}) {
            assertTrue(css.contains(selector), "missing selector: " + selector);
        }
        String js = read("static/providers.js");
        for (String cls : new String[]{"pv-preset-row", "pv-name", "pv-head-actions", "pv-meta", "pv-model-add-row", "pv-model-id", "pv-model-name", "pv-model-id-text", "pv-model-actions", "pv-test-fail"}) {
            assertTrue(js.contains(cls), "js must add class: " + cls);
        }
        for (String inline : new String[]{"style=\"margin:4px 0 20px", "style=\"font-weight:600\"", "style=\"display:flex;align-items:center;gap:8px\"", "style=\"display:flex;flex-wrap:wrap;gap:12px", "style=\"margin-top:8px\"", "style=\"display:flex;align-items:center;gap:10px", "style=\"min-width:160px\"", "style=\"font-weight:600;font-size:13px\"", "style=\"font-size:12px;color:var(--text-3)\"", "style=\"margin-left:auto", "style=\"background:var(--red-soft)\""}) {
            assertTrue(!js.contains(inline), "js must not keep inline style: " + inline);
        }
        assertTrue(js.contains("entry[0]"), "data-driven test badge keeps inline colors");
    }
}
