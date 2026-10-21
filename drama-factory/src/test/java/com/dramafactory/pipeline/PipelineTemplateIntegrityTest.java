package com.dramafactory.pipeline;

import org.junit.jupiter.api.Test;
import java.util.List;
import java.util.stream.Collectors;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PipelineTemplateIntegrityTest {

    @Test
    void service_loadsThirteen() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        assertEquals(13, service.listTemplates().size());
    }

    @Test
    void names_sortedAsExpected() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        List<String> names = service.listTemplates().stream()
                .map(PipelineTemplate::getName)
                .collect(Collectors.toList());
        assertEquals(List.of(
                "animated-explainer",
                "animation",
                "avatar-spokesperson",
                "character-animation",
                "cinematic",
                "clip-factory",
                "documentary-montage",
                "hybrid",
                "localization-dub",
                "novel-to-drama",
                "podcast-repurpose",
                "screen-demo",
                "talking-head"
        ), names);
    }

    @Test
    void getTemplate_animation_fields() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        PipelineTemplate template = service.getTemplate("animation");
        assertEquals("1.0", template.getVersion());
        assertEquals("animation", template.getCategory());
        assertFalse(template.getDescription().isEmpty());
        assertFalse(template.getStages().isEmpty());
    }

    @Test
    void getTemplate_unknown_throws() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        assertThrows(TemplateNotFoundException.class, () -> service.getTemplate("no-such"));
    }

    @Test
    void everyTemplate_hasDescriptionAndStages() {
        PipelineTemplateService service = new PipelineTemplateService(new PipelineTemplateLoader());
        for (PipelineTemplate template : service.listTemplates()) {
            assertFalse(template.getDescription().isEmpty(), "Description empty for " + template.getName());
            assertFalse(template.getStages().isEmpty(), "Stages empty for " + template.getName());
        }
    }

    @Test
    void loader_parse_missingName_throws() {
        PipelineTemplateLoader loader = new PipelineTemplateLoader();
        assertThrows(IllegalArgumentException.class, () -> loader.parse("version: \"1.0\"\nstages:\n  - name: s\n"));
    }

    @Test
    void loader_parse_blankAndMissingStages_throws() {
        PipelineTemplateLoader loader = new PipelineTemplateLoader();
        assertThrows(IllegalArgumentException.class, () -> loader.parse("   "));
        assertThrows(IllegalArgumentException.class, () -> loader.parse("name: x\nversion: \"1.0\"\n"));
    }
}