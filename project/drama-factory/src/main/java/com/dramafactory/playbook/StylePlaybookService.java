package com.dramafactory.playbook;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.core.io.Resource;
import org.springframework.core.io.support.PathMatchingResourcePatternResolver;
import org.springframework.core.io.support.ResourcePatternResolver;
import org.springframework.stereotype.Service;

/**
 * 风格手册服务，负责加载 classpath:style-playbooks 下的所有 YAML 手册并提供查询。
 */
@Service
public class StylePlaybookService {

    private final StylePlaybookLoader loader;
    private final Map<String, StylePlaybook> cache = new LinkedHashMap<>();

    public StylePlaybookService(StylePlaybookLoader loader) {
        this.loader = loader;
        loadAll();
    }

    private void loadAll() {
        try {
            ResourcePatternResolver resolver = new PathMatchingResourcePatternResolver();
            Resource[] resources = resolver.getResources("classpath:style-playbooks/*.yaml");
            for (Resource resource : resources) {
                String filename = resource.getFilename();
                if (filename == null || !filename.endsWith(".yaml")) {
                    continue;
                }
                String name = filename.substring(0, filename.length() - ".yaml".length());
                try (InputStream in = resource.getInputStream()) {
                    StylePlaybook playbook = loader.load(in, name);
                    cache.put(name, playbook);
                } catch (IOException e) {
                    throw new IllegalStateException("读取风格手册文件失败: " + filename, e);
                } catch (RuntimeException e) {
                    throw new IllegalStateException("解析风格手册文件失败: " + filename, e);
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("扫描风格手册目录失败", e);
        }
    }

    /**
     * 列出所有风格手册，按 name 排序。
     *
     * @return 风格手册列表
     */
    public List<StylePlaybook> listPlaybooks() {
        List<StylePlaybook> list = new ArrayList<>(cache.values());
        list.sort(Comparator.comparing(StylePlaybook::getName));
        return list;
    }

    /**
     * 按名称查询风格手册。
     *
     * @param name 手册名（文件名去后缀）
     * @return 查询结果
     */
    public Optional<StylePlaybook> getPlaybook(String name) {
        return Optional.ofNullable(cache.get(name));
    }

    /**
     * 返回已加载的手册数量。
     *
     * @return 数量
     */
    public int count() {
        return cache.size();
    }
}
