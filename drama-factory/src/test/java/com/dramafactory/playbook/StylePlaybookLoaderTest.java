package com.dramafactory.playbook;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.io.ClassPathResource;

/**
 * 风格手册加载器测试。
 */
@SpringBootTest
class StylePlaybookLoaderTest {

    @Autowired
    private StylePlaybookLoader loader;

    @Test
    void parsePremiumMinimalist() throws Exception {
        String yaml = readClasspath("style-playbooks/premium-minimalist.yaml");
        StylePlaybook playbook = loader.parse(yaml, "premium-minimalist");
        assertEquals("Premium Minimalist", playbook.getDisplayName());
        assertEquals("minimalist", playbook.getCategory());
        assertNotNull(playbook.getColorPalette());
        assertEquals("#F9FAFB", playbook.getColorPalette().background());
        assertEquals("#111827", playbook.getColorPalette().primary().get(0));
        assertNotNull(playbook.getTasteProfile());
        assertEquals(4, playbook.getTasteProfile().visualVariance());
        assertTrue(playbook.getSections().containsKey("motion"));
    }

    @Test
    void parseAnimeGhibli() throws Exception {
        String yaml = readClasspath("style-playbooks/anime-ghibli.yaml");
        StylePlaybook playbook = loader.parse(yaml, "anime-ghibli");
        assertNull(playbook.getTasteProfile());
        assertNotNull(playbook.getColorPalette());
        assertEquals("#F5F0E8", playbook.getColorPalette().text());
    }

    @Test
    void parseEmptyThrows() {
        assertThrows(IllegalArgumentException.class, () -> loader.parse("", "empty"));
    }

    private String readClasspath(String path) throws Exception {
        try (InputStream in = new ClassPathResource(path).getInputStream()) {
            return new String(in.readAllBytes(), StandardCharsets.UTF_8);
        }
    }
}
