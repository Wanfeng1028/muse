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

class CostLedgerDesignV3Test {

    private String readStatic(String name) throws IOException {
        try (InputStream in = new ClassPathResource("static/" + name).getInputStream()) {
            return StreamUtils.copyToString(in, StandardCharsets.UTF_8);
        }
    }

    @Test
    void costLedgerHtmlReferencesV3AfterV2() throws IOException {
        String html = readStatic("cost-ledger.html");
        int v2 = html.indexOf("/cost-ledger-design-v2.css");
        int v3 = html.indexOf("/cost-ledger-design-v3.css");
        assertNotEquals(-1, v2, "cost-ledger.html must reference /cost-ledger-design-v2.css");
        assertNotEquals(-1, v3, "cost-ledger.html must reference /cost-ledger-design-v3.css");
        assertTrue(v3 > v2, "/cost-ledger-design-v3.css must be referenced after /cost-ledger-design-v2.css");
    }

    @Test
    void costLedgerDesignV3CssIsSingleCleanRule() throws IOException {
        String css = readStatic("cost-ledger-design-v3.css");
        assertTrue(css.contains(".cl-budget-meta"), "cost-ledger-design-v3.css must contain the .cl-budget-meta rule");
        assertTrue(css.contains("gap: 8px"), "cost-ledger-design-v3.css must contain gap: 8px");

        int open = css.length() - css.replace("{", "").length();
        int close = css.length() - css.replace("}", "").length();
        assertEquals(1, open, "cost-ledger-design-v3.css must contain exactly one rule");
        assertEquals(open, close, "cost-ledger-design-v3.css braces must be balanced");

        String lowered = css.toLowerCase(Locale.ROOT);
        assertFalse(lowered.contains("linear-gradient"), "banned: linear-gradient");
        assertFalse(lowered.contains("backdrop-filter"), "banned: backdrop-filter");
        assertFalse(lowered.contains("!important"), "banned: !important");
        assertFalse(css.contains("Inter"), "banned: Inter");
    }

    @Test
    void costLedgerHtmlUsesClassInsteadOfInlineGap() throws IOException {
        String html = readStatic("cost-ledger.html");
        assertTrue(html.contains("cl-budget-meta"), "cost-ledger.html must use the cl-budget-meta class");
        assertFalse(html.contains("style=\"gap:8px\""), "old inline style=\"gap:8px\" must be removed from cost-ledger.html");
    }
}
