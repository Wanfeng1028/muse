package com.dramafactory.playbook;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.List;
import java.util.Optional;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

/**
 * 风格手册服务测试。
 */
@SpringBootTest
class StylePlaybookServiceTest {

    @Autowired
    private StylePlaybookService service;

    @Test
    void countIsFive() {
        assertEquals(5, service.count());
    }

    @Test
    void listPlaybooksContainsAllNames() {
        List<StylePlaybook> list = service.listPlaybooks();
        Set<String> names = list.stream().map(StylePlaybook::getName).collect(Collectors.toSet());
        assertTrue(names.containsAll(Set.of(
                "anime-ghibli",
                "clean-professional",
                "flat-motion-graphics",
                "minimalist-diagram",
                "premium-minimalist"
        )));
        assertEquals(5, names.size());
    }

    @Test
    void getPlaybookByName() {
        Optional<StylePlaybook> playbook = service.getPlaybook("clean-professional");
        assertTrue(playbook.isPresent());
        assertEquals("Clean Professional", playbook.get().getDisplayName());
    }

    @Test
    void getPlaybookNotFound() {
        assertTrue(service.getPlaybook("nope").isEmpty());
    }
}
