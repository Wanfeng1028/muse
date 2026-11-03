package com.dramafactory.pipeline;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;
import java.util.List;
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
@AutoConfigureMockMvc
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:noveltodrama;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop"})
class NovelToDramaTemplateDeepTest {

    @Autowired
    private PipelineTemplateService pipelineTemplateService;

    @Test
    void listTemplates_containsNovelToDrama() {
        List<PipelineTemplate> templates = pipelineTemplateService.listTemplates();
        assertThat(templates).extracting(PipelineTemplate::getName).contains("novel-to-drama");
    }

    @Test
    void getTemplate_novelToDrama_isNotNull() {
        PipelineTemplate template = pipelineTemplateService.getTemplate("novel-to-drama");
        assertThat(template).isNotNull();
    }

    @Test
    void validateTemplate_novelToDrama_returnsEmptyList() {
        PipelineTemplate template = pipelineTemplateService.getTemplate("novel-to-drama");
        List<String> problems = pipelineTemplateService.validateTemplate(template);
        assertThat(problems).isEmpty();
    }

    @Test
    void novelToDramaTemplate_hasSevenStages() {
        PipelineTemplate template = pipelineTemplateService.getTemplate("novel-to-drama");
        assertThat(template.getStages()).hasSize(7);
    }

    @Test
    void novelToDramaTemplate_coversKeyStages() {
        PipelineTemplate template = pipelineTemplateService.getTemplate("novel-to-drama");
        List<String> stageNames = template.getStages().stream()
                .map(PipelineStage::getName)
                .toList();
        assertThat(stageNames).contains("rewrite", "extract", "storyboard", "media_gen", "compose");
    }

    @Test
    void getTemplate_nonExistent_throwsException() {
        assertThatThrownBy(() -> pipelineTemplateService.getTemplate("non-existent-template"))
                .isInstanceOf(TemplateNotFoundException.class);
    }
}
