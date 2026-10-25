package com.dramafactory.web;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class QcDesignV2Test {

    private String readStatic(String name) throws IOException {
        try (InputStream in = new ClassPathResource("static/" + name).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void qcHtmlReferencesV2AfterV1() throws IOException {
        String html = readStatic("qc.html");
        int v1 = html.indexOf("/qc-design-v1.css");
        int v2 = html.indexOf("/qc-design-v2.css");
        assertNotEquals(-1, v1, "qc.html must reference /qc-design-v1.css");
        assertNotEquals(-1, v2, "qc.html must reference /qc-design-v2.css");
        assertTrue(v2 > v1, "/qc-design-v2.css must be referenced after /qc-design-v1.css");
    }

    @Test
    void qcDesignV2CssIsSingleCleanRule() throws IOException {
        String css = readStatic("qc-design-v2.css");
        assertTrue(css.contains("#qcVideo"), "qc-design-v2.css must contain the #qcVideo rule");
        assertTrue(css.contains("max-height: 480px"), "qc-design-v2.css must contain max-height: 480px");

        int open = css.length() - css.replace("{", "").length();
        int close = css.length() - css.replace("}", "").length();
        assertEquals(1, open, "qc-design-v2.css must contain exactly one rule");
        assertEquals(open, close, "qc-design-v2.css braces must be balanced");

        String lowered = css.toLowerCase(Locale.ROOT);
        assertFalse(lowered.contains("linear-gradient"), "banned: linear-gradient");
        assertFalse(lowered.contains("backdrop-filter"), "banned: backdrop-filter");
        assertFalse(lowered.contains("!important"), "banned: !important");
        assertFalse(css.contains("Inter"), "banned: Inter");
    }

    @Test
    void qcHtmlDropsOldInlineStyle() throws IOException {
        String html = readStatic("qc.html");
        assertFalse(html.contains("width:100%;max-height:480px"), "old inline style must be removed from qc.html");
    }
}
