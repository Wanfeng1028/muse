package com.dramafactory.pipeline;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * 使用 SnakeYAML 将 YAML 文本解析为 {@link PipelineTemplate}，并做必填校验。
 * <p>YAML 使用 snake_case 键名，本类手动映射到 POJO 字段，不使用自动 bean 绑定。</p>
 */
@Component
public class PipelineTemplateLoader {

    /**
     * 解析 YAML 文本为模板对象。
     *
     * @param yamlText YAML 文本
     * @return 解析并校验后的模板
     * @throws IllegalArgumentException 当 YAML 为空或缺少必填字段时
     */
    public PipelineTemplate parse(String yamlText) {
        if (yamlText == null || yamlText.isBlank()) {
            throw new IllegalArgumentException("YAML 文本为空，无法解析模板");
        }
        Yaml yaml = new Yaml(new SafeConstructor(new LoaderOptions()));
        Object root = yaml.load(yamlText);
        return convertRoot(root);
    }

    /**
     * 从输入流读取 UTF-8 文本并解析为模板对象。
     *
     * @param in 输入流
     * @return 解析并校验后的模板
     * @throws IllegalArgumentException 当输入流为空或缺少必填字段时
     */
    public PipelineTemplate load(InputStream in) {
        if (in == null) {
            throw new IllegalArgumentException("输入流为空，无法解析模板");
        }
        try {
            InputStreamReader reader = new InputStreamReader(in, StandardCharsets.UTF_8);
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[4096];
            int n;
            while ((n = reader.read(buf)) != -1) {
                sb.append(buf, 0, n);
            }
            return parse(sb.toString());
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("读取模板流失败: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    private PipelineTemplate convertRoot(Object root) {
        if (!(root instanceof Map)) {
            throw new IllegalArgumentException("YAML 根节点必须是映射结构");
        }
        Map<String, Object> map = (Map<String, Object>) root;

        String name = asString(map.get("name"));
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("模板缺少必填字段: name");
        }
        String version = asString(map.get("version"));
        if (version == null || version.isBlank()) {
            throw new IllegalArgumentException("模板缺少必填字段: version");
        }
        Object stagesObj = map.get("stages");
        if (!(stagesObj instanceof List) || ((List<?>) stagesObj).isEmpty()) {
            throw new IllegalArgumentException("模板缺少必填字段或为空: stages");
        }

        PipelineTemplate template = new PipelineTemplate();
        template.setName(name);
        template.setVersion(version);
        template.setDescription(asString(map.get("description")));
        template.setCategory(asString(map.get("category")));
        template.setStages(convertStages((List<?>) stagesObj, "stages"));
        return template;
    }

    @SuppressWarnings("unchecked")
    private List<PipelineStage> convertStages(List<?> raw, String path) {
        List<PipelineStage> result = new ArrayList<>();
        for (int i = 0; i < raw.size(); i++) {
            Object item = raw.get(i);
            if (!(item instanceof Map)) {
                throw new IllegalArgumentException(path + "[" + i + "] 不是映射结构");
            }
            result.add(convertStage((Map<String, Object>) item, path + "[" + i + "]"));
        }
        return result;
    }

    @SuppressWarnings("unchecked")
    private PipelineStage convertStage(Map<String, Object> map, String path) {
        String stageName = asString(map.get("name"));
        if (stageName == null || stageName.isBlank()) {
            throw new IllegalArgumentException(path + " 缺少必填字段: name");
        }
        PipelineStage stage = new PipelineStage();
        stage.setName(stageName);
        stage.setProduces(asStringList(pick(map, "produces", "produces")));
        stage.setRequiredArtifactsIn(asStringList(pick(map, "requiredArtifactsIn", "required_artifacts_in")));
        stage.setCheckpointRequired(asBoolean(pick(map, "checkpointRequired", "checkpoint_required")));
        stage.setHumanApprovalDefault(asBoolean(pick(map, "humanApprovalDefault", "human_approval_default")));
        stage.setReviewFocus(asStringList(pick(map, "reviewFocus", "review_focus")));
        stage.setSuccessCriteria(asStringList(pick(map, "successCriteria", "success_criteria")));

        Object sub = pick(map, "subStages", "sub_stages");
        if (sub instanceof List && !((List<?>) sub).isEmpty()) {
            stage.setSubStages(convertStages((List<?>) sub, path + ".subStages"));
        } else {
            stage.setSubStages(new ArrayList<>());
        }
        return stage;
    }

    /**
     * 取值时同时兼容 camelCase 与 snake_case 两种键名，优先 camelCase。
     */
    private Object pick(Map<String, Object> map, String camelKey, String snakeKey) {
        if (map.containsKey(camelKey)) {
            return map.get(camelKey);
        }
        return map.get(snakeKey);
    }

    private String asString(Object value) {
        if (value == null) {
            return null;
        }
        String s = String.valueOf(value).trim();
        return s.isEmpty() ? null : s;
    }

    private boolean asBoolean(Object value) {
        if (value == null) {
            return false;
        }
        if (value instanceof Boolean b) {
            return b;
        }
        return Boolean.parseBoolean(String.valueOf(value).trim());
    }

    private List<String> asStringList(Object value) {
        List<String> list = new ArrayList<>();
        if (value instanceof List<?> raw) {
            for (Object item : raw) {
                if (item != null) {
                    String s = String.valueOf(item).trim();
                    if (!s.isEmpty()) {
                        list.add(s);
                    }
                }
            }
        }
        return list;
    }
}
