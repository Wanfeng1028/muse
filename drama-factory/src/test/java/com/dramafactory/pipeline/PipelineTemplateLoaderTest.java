package com.dramafactory.pipeline;

import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * PipelineTemplateLoader 纯单元测试，不加载 Spring 上下文。
 * 覆盖 YAML 解析、snake_case 字段映射、默认值填充、非法输入校验及真实模板加载。
 */
class PipelineTemplateLoaderTest {

    private final PipelineTemplateLoader loader = new PipelineTemplateLoader();

    @Test
    void parse_minimalValidYaml_mapsFieldsAndAppliesDefaults() {
        String yaml = """
                name: mini
                version: v1
                description: minimal template
                category: test
                stages:
                  - name: stage-a
                    produces: [out-a]
                    required_artifacts_in: []
                    checkpoint_required: true
                    human_approval_default: false
                    review_focus: [focus-a]
                    success_criteria: [crit-a]
                    sub_stages:
                      - name: sub-a
                        produces: [sub-out]
                  - name: stage-b
                    produces: [out-b]
                """;

        PipelineTemplate template = loader.parse(yaml);

        assertThat(template.getName()).isEqualTo("mini");
        assertThat(template.getVersion()).isEqualTo("v1");
        assertThat(template.getDescription()).isEqualTo("minimal template");
        assertThat(template.getCategory()).isEqualTo("test");
        assertThat(template.getStages()).hasSize(2);

        PipelineStage stageA = template.getStages().get(0);
        assertThat(stageA.getName()).isEqualTo("stage-a");
        assertThat(stageA.getProduces()).containsExactly("out-a");
        assertThat(stageA.getRequiredArtifactsIn()).isEmpty();
        assertThat(stageA.isCheckpointRequired()).isTrue();
        assertThat(stageA.isHumanApprovalDefault()).isFalse();
        assertThat(stageA.getReviewFocus()).containsExactly("focus-a");
        assertThat(stageA.getSuccessCriteria()).containsExactly("crit-a");
        assertThat(stageA.getSubStages()).hasSize(1);
        assertThat(stageA.getSubStages().get(0).getName()).isEqualTo("sub-a");
        assertThat(stageA.getSubStages().get(0).getProduces()).containsExactly("sub-out");

        PipelineStage stageB = template.getStages().get(1);
        assertThat(stageB.getName()).isEqualTo("stage-b");
        assertThat(stageB.getProduces()).containsExactly("out-b");
        // 未声明的集合字段应默认为空而非 null
        assertThat(stageB.getRequiredArtifactsIn()).isNotNull().isEmpty();
        assertThat(stageB.getReviewFocus()).isNotNull().isEmpty();
        assertThat(stageB.getSuccessCriteria()).isNotNull().isEmpty();
        assertThat(stageB.getSubStages()).isNotNull().isEmpty();
        // checkpoint_required 默认 false
        assertThat(stageB.isCheckpointRequired()).isFalse();
        assertThat(stageB.isHumanApprovalDefault()).isFalse();
    }

    @Test
    void parse_missingTopLevelName_throwsIllegalArgumentException() {
        String yaml = """
                version: v1
                stages:
                  - name: stage-a
                """;

        assertThatThrownBy(() -> loader.parse(yaml))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void parse_emptyStages_throwsIllegalArgumentException() {
        String yaml = """
                name: empty-stages
                version: v1
                stages: []
                """;

        assertThatThrownBy(() -> loader.parse(yaml))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void parse_stageMissingName_throwsIllegalArgumentException() {
        String yaml = """
                name: bad-stage
                version: v1
                stages:
                  - produces: [out-a]
                """;

        assertThatThrownBy(() -> loader.parse(yaml))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void load_cinematicClasspathTemplate_hasEightStagesAndSampleSubStage() throws Exception {
        try (InputStream in = getClass().getClassLoader()
                .getResourceAsStream("pipeline-templates/cinematic.yaml")) {
            assertThat(in).as("cinematic.yaml 必须存在于 classpath").isNotNull();

            PipelineTemplate template = loader.load(in);

            assertThat(template.getName()).isEqualTo("cinematic");
            assertThat(template.getStages()).hasSize(8);

            PipelineStage proposal = template.getStages().stream()
                    .filter(s -> "proposal".equals(s.getName()))
                    .findFirst()
                    .orElseThrow(() -> new AssertionError("缺少 proposal stage"));

            List<PipelineStage> subStages = proposal.getSubStages();
            assertThat(subStages).isNotNull().isNotEmpty();
            assertThat(subStages)
                    .extracting(PipelineStage::getName)
                    .contains("sample");
        }
    }
}
