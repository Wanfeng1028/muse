package com.dramafactory.playbook;

import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Component;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

/**
 * 使用 SnakeYAML 将 YAML 文本解析为 {@link StylePlaybook}，并做必填校验。
 * <p>YAML 使用 snake_case 键名，本类手动映射到 POJO 字段，不使用自动 bean 绑定。</p>
 */
@Component
public class StylePlaybookLoader {

    /**
     * 解析 YAML 文本为风格手册对象。
     *
     * @param yamlText YAML 文本
     * @param name 手册名（文件名去后缀）
     * @return 解析并校验后的风格手册
     * @throws IllegalArgumentException 当 YAML 为空或缺少必填字段时
     */
    public StylePlaybook parse(String yamlText, String name) {
        if (yamlText == null || yamlText.isBlank()) {
            throw new IllegalArgumentException("YAML 文本为空，无法解析风格手册");
        }
        Yaml yaml = new Yaml(new SafeConstructor(new LoaderOptions()));
        Object root = yaml.load(yamlText);
        return convertRoot(root, name);
    }

    /**
     * 从输入流读取 UTF-8 文本并解析为风格手册对象。
     *
     * @param in 输入流
     * @param name 手册名（文件名去后缀）
     * @return 解析并校验后的风格手册
     * @throws IllegalArgumentException 当输入流为空或缺少必填字段时
     */
    public StylePlaybook load(InputStream in, String name) {
        if (in == null) {
            throw new IllegalArgumentException("输入流为空，无法解析风格手册");
        }
        try {
            InputStreamReader reader = new InputStreamReader(in, StandardCharsets.UTF_8);
            StringBuilder sb = new StringBuilder();
            char[] buf = new char[4096];
            int n;
            while ((n = reader.read(buf)) != -1) {
                sb.append(buf, 0, n);
            }
            return parse(sb.toString(), name);
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("读取风格手册流失败: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    private StylePlaybook convertRoot(Object root, String name) {
        if (!(root instanceof Map)) {
            throw new IllegalArgumentException("YAML 根节点必须是映射结构");
        }
        Map<String, Object> map = (Map<String, Object>) root;

        Object identityObj = map.get("identity");
        if (!(identityObj instanceof Map)) {
            throw new IllegalArgumentException("风格手册缺少必填字段: identity");
        }
        Map<String, Object> identity = (Map<String, Object>) identityObj;
        String displayName = asString(identity.get("name"));
        if (displayName == null || displayName.isBlank()) {
            throw new IllegalArgumentException("风格手册 identity 缺少必填字段: name");
        }

        StylePlaybook playbook = new StylePlaybook();
        playbook.setName(name);
        playbook.setDisplayName(displayName);
        playbook.setCategory(asString(identity.get("category")));
        playbook.setMood(asString(identity.get("mood")));
        playbook.setPace(asString(identity.get("pace")));
        playbook.setBestFor(asString(identity.get("best_for")));

        Object tasteObj = map.get("taste_profile");
        if (tasteObj instanceof Map) {
            playbook.setTasteProfile(convertTasteProfile((Map<String, Object>) tasteObj));
        } else {
            playbook.setTasteProfile(null);
        }

        Object visualObj = map.get("visual_language");
        if (visualObj instanceof Map) {
            Object paletteObj = ((Map<String, Object>) visualObj).get("color_palette");
            if (paletteObj instanceof Map) {
                playbook.setColorPalette(convertColorPalette((Map<String, Object>) paletteObj));
            }
        }

        Map<String, Object> sections = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : map.entrySet()) {
            String key = entry.getKey();
            if (!"identity".equals(key) && !"taste_profile".equals(key)) {
                sections.put(key, entry.getValue());
            }
        }
        playbook.setSections(sections);

        return playbook;
    }

    @SuppressWarnings("unchecked")
    private StylePlaybook.TasteProfile convertTasteProfile(Map<String, Object> map) {
        return new StylePlaybook.TasteProfile(
                asString(map.get("design_read")),
                asInteger(map.get("visual_variance")),
                asInteger(map.get("motion_intensity")),
                asInteger(map.get("information_density")),
                asString(map.get("palette_discipline")),
                asString(map.get("layout_variation")),
                asString(map.get("reference_strategy")),
                asStringList(map.get("anti_patterns")),
                asStringList(map.get("quality_gates"))
        );
    }

    @SuppressWarnings("unchecked")
    private StylePlaybook.ColorPalette convertColorPalette(Map<String, Object> map) {
        return new StylePlaybook.ColorPalette(
                asStringList(map.get("primary")),
                asStringList(map.get("accent")),
                asString(map.get("background")),
                asString(map.get("text")),
                asString(map.get("muted"))
        );
    }

    private String asString(Object value) {
        if (value == null) {
            return null;
        }
        String s = String.valueOf(value).trim();
        return s.isEmpty() ? null : s;
    }

    private Integer asInteger(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Integer i) {
            return i;
        }
        if (value instanceof Number n) {
            return n.intValue();
        }
        String s = String.valueOf(value).trim();
        if (s.isEmpty()) {
            return null;
        }
        try {
            return Integer.valueOf(s);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private List<String> asStringList(Object value) {
        if (value == null) {
            return List.of();
        }
        if (value instanceof List<?> raw) {
            List<String> list = new ArrayList<>();
            for (Object item : raw) {
                if (item != null) {
                    String s = String.valueOf(item).trim();
                    if (!s.isEmpty()) {
                        list.add(s);
                    }
                }
            }
            return list;
        }
        String s = String.valueOf(value).trim();
        return s.isEmpty() ? List.of() : List.of(s);
    }
}
