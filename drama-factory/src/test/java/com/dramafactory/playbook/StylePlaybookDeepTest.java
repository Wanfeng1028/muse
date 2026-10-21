package com.dramafactory.playbook;

import java.util.List;
import java.util.Optional;

import org.junit.jupiter.api.Assertions;
import org.junit.jupiter.api.Test;

class StylePlaybookDeepTest {

    @Test
    void service_count_isFive() {
        StylePlaybookService service = new StylePlaybookService(new StylePlaybookLoader());
        Assertions.assertEquals(5, service.count());
    }

    @Test
    void list_sortedByName() {
        StylePlaybookService service = new StylePlaybookService(new StylePlaybookLoader());
        List<StylePlaybook> list = service.listPlaybooks();
        List<String> names = list.stream().map(StylePlaybook::getName).toList();
        Assertions.assertEquals(
                List.of("anime-ghibli", "clean-professional", "flat-motion-graphics", "minimalist-diagram", "premium-minimalist"),
                names);
    }

    @Test
    void get_animeGhibli_fields() {
        StylePlaybookService service = new StylePlaybookService(new StylePlaybookLoader());
        Optional<StylePlaybook> opt = service.getPlaybook("anime-ghibli");
        Assertions.assertTrue(opt.isPresent());
        StylePlaybook playbook = opt.get();
        Assertions.assertEquals("Anime Ghibli", playbook.getDisplayName());
        Assertions.assertEquals("custom", playbook.getCategory());
        Assertions.assertTrue(playbook.getMood().contains("warm"));
        Assertions.assertFalse(playbook.getBestFor().isEmpty());
        Assertions.assertTrue(playbook.getSections().containsKey("visual_language"));
        Assertions.assertFalse(playbook.getSections().containsKey("identity"));
    }

    @Test
    void get_unknown_empty() {
        StylePlaybookService service = new StylePlaybookService(new StylePlaybookLoader());
        Assertions.assertTrue(service.getPlaybook("no-such").isEmpty());
        Assertions.assertTrue(service.getPlaybook(null).isEmpty());
    }

    @Test
    void loader_parse_blank_throws() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.parse("", "x"));
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.parse("   ", "x"));
    }

    @Test
    void loader_parse_nonMap_throws() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.parse("- a\n- b\n", "x"));
    }

    @Test
    void loader_parse_missingIdentity_throws() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.parse("category: x\n", "x"));
    }

    @Test
    void loader_parse_missingIdentityName_throws() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.parse("identity:\n  category: custom\n", "x"));
    }

    @Test
    void loader_parse_minimal_ok() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        StylePlaybook playbook = loader.parse("identity:\n  name: \"最小手册\"\n", "mini");
        Assertions.assertEquals("mini", playbook.getName());
        Assertions.assertEquals("最小手册", playbook.getDisplayName());
        Assertions.assertNull(playbook.getTasteProfile());
        Assertions.assertNull(playbook.getCategory());
    }

    @Test
    void loader_load_nullStream_throws() {
        StylePlaybookLoader loader = new StylePlaybookLoader();
        Assertions.assertThrows(IllegalArgumentException.class, () -> loader.load(null, "x"));
    }
}