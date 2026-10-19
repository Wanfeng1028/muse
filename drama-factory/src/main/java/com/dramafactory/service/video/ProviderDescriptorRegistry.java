package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.attribute.FileTime;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;
import java.util.stream.Stream;

/**
 * 描述符注册表：扫描 data/providers/ 目录，按 mtime 热加载 JSON 描述符。
 * 每次对外调用前做一次轻量检查，用户丢入新文件即生效，无需重启服务。
 */
@Component
public class ProviderDescriptorRegistry {

    private static final Logger log = LoggerFactory.getLogger(ProviderDescriptorRegistry.class);

    private static final Pattern FILE_NAME_PATTERN =
            Pattern.compile("^[a-zA-Z0-9][a-zA-Z0-9._-]*\\.json$");

    private final ObjectMapper objectMapper;
    private final DescriptorSecretResolver secretResolver;
    private final String dir;

    private final Map<String, CachedEntry> cache = new HashMap<>();

    /**
     * id -&gt; 主描述符（按文件名排序取首个）。多个文件声明同一 id 时，
     * 生效对象必须确定，不能依赖 HashMap 迭代顺序碰运气；冲突会在日志里告警。
     */
    private final Map<String, CachedEntry> primaryById = new HashMap<>();

    /**
     * 全 registry 共享的 HTTP 客户端（连接复用）。测试走注入的 VideoHttpGateway，不受影响。
     */
    private static final HttpClient SHARED_CLIENT = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(15))
            .build();


    public ProviderDescriptorRegistry(ObjectMapper objectMapper, DescriptorSecretResolver secretResolver,
                                      @Value("${drama.providers.dir:data/providers}") String dir) {
        this.objectMapper = objectMapper;
        this.secretResolver = secretResolver;
        this.dir = dir;
    }

    private static record CachedEntry(Path file, long mtime, ProviderDescriptor descriptor) {
    }

    /**
     * 按 mtime 增量重载描述符；目录不存在或非法直接返回。
     */
    public synchronized void reloadIfChanged() {
        Path root = Path.of(dir);
        if (!Files.exists(root) || !Files.isDirectory(root)) {
            return;
        }
        List<Path> files = new ArrayList<>();
        try (Stream<Path> stream = Files.list(root)) {
            stream.filter(Files::isRegularFile)
                    .filter(p -> !p.getFileName().toString().startsWith("."))
                    .forEach(p -> {
                        String fileName = p.getFileName().toString();
                        if (!FILE_NAME_PATTERN.matcher(fileName).matches()) {
                            log.warn("描述符文件名非法，跳过: {}", fileName);
                            return;
                        }
                        files.add(p);
                    });
        } catch (IOException e) {
            log.warn("读取描述符目录失败: {}", e.getMessage());
            return;
        }

        for (Path file : files) {
            long mtime;
            try {
                FileTime lastModified = Files.getLastModifiedTime(file);
                mtime = lastModified.toMillis();
            } catch (IOException e) {
                log.warn("描述符文件 {} 跳过: {}", file.getFileName(), e.getMessage());
                continue;
            }
            CachedEntry existing = cache.get(file.toAbsolutePath().toString());
            if (existing != null && existing.mtime() == mtime) {
                continue;
            }
            try {
                ProviderDescriptor descriptor = objectMapper.readValue(file.toFile(), ProviderDescriptor.class);
                descriptor.validate();
                cache.put(file.toAbsolutePath().toString(),
                        new CachedEntry(file.toAbsolutePath(), mtime, descriptor));
            } catch (Exception e) {
                log.warn("描述符文件 {} 跳过: {}", file.getFileName(), e.getMessage());
            }
        }

        cache.entrySet().removeIf(entry -> !Files.exists(entry.getValue().file()));

        rebuildPrimaryIndex();
    }

    /**
     * 重建 id 主索引：按文件绝对路径排序，同一 id 只保留首个，其余记 warn。
     * 必须在持有对象锁时调用（reloadIfChanged 已是 synchronized）。
     */
    private void rebuildPrimaryIndex() {
        primaryById.clear();
        List<CachedEntry> sorted = new ArrayList<>(cache.values());
        sorted.sort(Comparator.comparing(e -> e.file().toString()));
        for (CachedEntry entry : sorted) {
            String id = entry.descriptor().getId();
            CachedEntry existing = primaryById.get(id);
            if (existing == null) {
                primaryById.put(id, entry);
            } else {
                log.warn("描述符 id 重复: {}（{} 与 {}），按文件名排序仅 {} 生效",
                        id, existing.file().getFileName(), entry.file().getFileName(),
                        existing.file().getFileName());
            }
        }
    }

    /**
     * 返回按 id 排序的描述符副本。
     *
     * @return 描述符列表
     */
    public synchronized List<ProviderDescriptor> all() {
        reloadIfChanged();
        List<ProviderDescriptor> list = new ArrayList<>();
        for (CachedEntry entry : cache.values()) {
            list.add(entry.descriptor());
        }
        list.sort(Comparator.comparing(ProviderDescriptor::getId));
        return list;
    }

    /**
     * 按 id 查找描述符。
     *
     * @param id 描述符 id
     * @return 命中的描述符
     */
    public synchronized Optional<ProviderDescriptor> byId(String id) {
        reloadIfChanged();
        CachedEntry entry = primaryById.get(id);
        return entry == null ? Optional.empty() : Optional.of(entry.descriptor());
    }

    /**
     * 构造描述符驱动的 Provider 实例。
     *
     * @param id 描述符 id
     * @return Provider 实例
     */
    public synchronized DescriptorVideoProvider buildProvider(String id) {
        ProviderDescriptor descriptor = byId(id)
                .orElseThrow(() -> new IllegalArgumentException("未知描述符 provider: " + id));
        VideoHttpGateway gateway = request -> {
            HttpResponse<String> response = SHARED_CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
            return new VideoHttpGateway.GatewayResponse(response.statusCode(), response.body());
        };        return new DescriptorVideoProvider(descriptor, objectMapper, gateway,
                () -> secretResolver.resolve(descriptor.getAuth().getKeyRef()));
    }
}

