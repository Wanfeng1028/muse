package com.dramafactory.service.byok;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MediaProvider;

import com.dramafactory.repository.MediaProviderRepository;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;


import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.security.SecureRandom;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

@Service
public class ByokGenerateService {

    public record GenerateRequest(String module, Long providerId, String modelId, String prompt, Map<String, String> options) {}
    public record GenerateResponse(String status, String url, String error) {}

    private static final DateTimeFormatter FILE_TS = DateTimeFormatter.ofPattern("yyyyMMddHHmmss");
    private static final String RANDOM_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";
    private static final SecureRandom RANDOM = new SecureRandom();


    /**
     * HTTP 下载发送器接缝：生产环境走 JDK HttpClient，测试注入桩。
     * 包可见，仅供测试使用。
     */
    @FunctionalInterface
    interface DownloadSender {
        HttpResponse<InputStream> send(HttpRequest request) throws IOException, InterruptedException;
    }

    private final MediaProviderRepository providerRepository;
    private final Map<String, ImageProvider> imageProvidersByName;
    private final Map<String, MusicProvider> musicProvidersByName;
    private final Map<String, AvatarProvider> avatarProvidersByName;
    private final String storageDir;
    private final HttpClient downloadClient;
    private final DownloadSender downloadSender;

    private com.dramafactory.service.AssetService assetService;

    @org.springframework.beans.factory.annotation.Autowired(required = false)
    public void setAssetService(com.dramafactory.service.AssetService assetService) {
        this.assetService = assetService;
    }

    @Autowired
    public ByokGenerateService(MediaProviderRepository providerRepository,
                               Map<String, ImageProvider> imageProviders,
                               Map<String, MusicProvider> musicProviders,
                               Map<String, AvatarProvider> avatarProviders,
                               @Value("${drama.storage:./data/media}") String storageDir) {
        this(providerRepository, imageProviders, musicProviders, avatarProviders, storageDir, null);
    }

    ByokGenerateService(MediaProviderRepository providerRepository,
                        Map<String, ImageProvider> imageProviders,
                        Map<String, MusicProvider> musicProviders,
                        Map<String, AvatarProvider> avatarProviders,
                        String storageDir,
                        DownloadSender downloadSender) {
        this.providerRepository = providerRepository;
        this.imageProvidersByName = toNameMap(imageProviders);
        this.musicProvidersByName = toNameMap(musicProviders);
        this.avatarProvidersByName = toNameMap(avatarProviders);
        this.storageDir = storageDir;
        this.downloadClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
        this.downloadSender = downloadSender != null ? downloadSender : this::sendViaClient;
    }

    private HttpResponse<InputStream> sendViaClient(HttpRequest request) throws IOException, InterruptedException {
        return downloadClient.send(request, HttpResponse.BodyHandlers.ofInputStream());
    }


    private static <T> Map<String, T> toNameMap(Map<String, T> source) {
        if (source == null || source.isEmpty()) {
            return Map.of();
        }
        Map<String, T> result = new HashMap<>();
        source.forEach((key, value) -> {
            if (key != null) {
                result.put(key.toLowerCase(Locale.ROOT), value);
            }
        });
        return Map.copyOf(result);
    }

    public GenerateResponse generate(GenerateRequest req) {
        if (req == null) {
            throw new IllegalArgumentException("请求不能为空");
        }
        String module = req.module();
        if (module == null) {
            throw new IllegalArgumentException("不支持的模块：" + module);
        }
        String upperModule = module.toUpperCase(Locale.ROOT);
        if (!upperModule.equals("IMAGE") && !upperModule.equals("MUSIC") && !upperModule.equals("AVATAR")) {
            throw new IllegalArgumentException("不支持的模块：" + module);
        }
        Long providerId = req.providerId();
        if (providerId == null) {
            throw new IllegalArgumentException("请选择供应商");
        }
        String modelId = req.modelId();
        if (modelId == null || modelId.isBlank()) {
            throw new IllegalArgumentException("请选择模型");
        }
        String prompt = req.prompt();
        if (prompt == null || prompt.isBlank()) {
            throw new IllegalArgumentException("请填写提示词");
        }

        MediaProvider provider = providerRepository.findById(providerId)
                .orElseThrow(() -> new ResourceNotFoundException("provider", providerId));

        Map<String, String> options = req.options() == null ? Map.of() : req.options();
        String providerName = provider.getName() == null ? "" : provider.getName();
        String lowerName = providerName.toLowerCase(Locale.ROOT);

        return switch (upperModule) {
            case "IMAGE" -> generateImage(provider, providerName, lowerName, modelId, prompt, options);
            case "MUSIC" -> generateMusic(provider, providerName, lowerName, modelId, prompt, options);
            case "AVATAR" -> generateAvatar(provider, providerName, lowerName, modelId, prompt, options);
            default -> throw new IllegalArgumentException("不支持的模块：" + module);
        };
    }

    private GenerateResponse generateImage(MediaProvider provider, String providerName, String lowerName,
                                           String modelId, String prompt, Map<String, String> options) {
        String beanName = matchImage(lowerName);
        ImageProvider imageProvider = beanName == null ? null : imageProvidersByName.get(beanName);
        if (imageProvider == null) {
            throw new IllegalStateException("该供应商暂未接入生成实现：" + providerName);
        }

        String size = options.get("size");
        if (size == null || size.isBlank()) {
            size = "1024*1024";
        }

        String apiKey = provider.getApiKey();
        String apiBase = provider.getApiAddress();

        ImageProvider.SubmitResult submitResult = imageProvider.submit(apiKey, apiBase, modelId, prompt, size);
        String taskId = submitResult.taskId();

        long deadline = System.currentTimeMillis() + 150_000L;
        String imageUrl = null;
        while (true) {
            ImageProvider.PollResult pollResult = imageProvider.poll(apiKey, apiBase, taskId);
            ImageProvider.RemoteStatus status = pollResult.status();
            if (status == ImageProvider.RemoteStatus.SUCCEEDED) {
                imageUrl = pollResult.imageUrl();
                break;
            }
            if (status == ImageProvider.RemoteStatus.FAILED) {
                throw new RuntimeException("图片生成失败：" + pollResult.errorMessage());
            }
            if (System.currentTimeMillis() >= deadline) {
                throw new RuntimeException("生成超时，请稍后重试");
            }
            sleep(4000L);
        }

        if (imageUrl == null || imageUrl.isBlank()) {
            throw new RuntimeException("图片生成失败：未返回产物地址");
        }

        String path = download(imageUrl, "image", "png");
        registerAsset(path, com.dramafactory.model.AssetType.IMAGE, extractRunId(options), providerName, prompt);
        return new GenerateResponse("SUCCEEDED", path, null);
    }

    private GenerateResponse generateMusic(MediaProvider provider, String providerName, String lowerName,
                                           String modelId, String prompt, Map<String, String> options) {
        String beanName = matchMusic(lowerName);
        MusicProvider musicProvider = beanName == null ? null : musicProvidersByName.get(beanName);
        if (musicProvider == null) {
            throw new IllegalStateException("该供应商暂未接入生成实现：" + providerName);
        }

        String lyrics = options.get("lyrics");
        boolean instrumental = "true".equals(options.get("instrumental"));

        String apiKey = provider.getApiKey();
        String apiBase = provider.getApiAddress();

        MusicProvider.GenerateResult result = musicProvider.generate(apiKey, apiBase, modelId, prompt, lyrics, instrumental);
        String audioUrl = result.audioUrl();
        if (audioUrl == null || audioUrl.isBlank()) {
            throw new RuntimeException("音乐生成失败：未返回产物地址");
        }

        String path = download(audioUrl, "music", "mp3");
        registerAsset(path, com.dramafactory.model.AssetType.AUDIO, extractRunId(options), providerName, prompt);
        return new GenerateResponse("SUCCEEDED", path, null);
    }

    private GenerateResponse generateAvatar(MediaProvider provider, String providerName, String lowerName,
                                            String modelId, String prompt, Map<String, String> options) {
        String beanName = matchAvatar(lowerName);
        AvatarProvider avatarProvider = beanName == null ? null : avatarProvidersByName.get(beanName);
        if (avatarProvider == null) {
            throw new IllegalStateException("该供应商暂未接入生成实现：" + providerName);
        }

        String imageUrl = options.get("imageUrl");
        if (imageUrl == null || imageUrl.isBlank()) {
            throw new IllegalArgumentException("请提供人物图 URL");
        }
        String audioUrl = options.get("audioUrl");
        String script = prompt;

        String apiKey = provider.getApiKey();
        String apiBase = provider.getApiAddress();

        AvatarProvider.SubmitResult submitResult = avatarProvider.submit(apiKey, imageUrl, audioUrl, script);
        String talkId = submitResult.talkId();

        long deadline = System.currentTimeMillis() + 240_000L;
        String videoUrl = null;
        while (true) {
            AvatarProvider.PollResult pollResult = avatarProvider.poll(apiKey, talkId);
            AvatarProvider.RemoteStatus status = pollResult.status();
            if (status == AvatarProvider.RemoteStatus.SUCCEEDED) {
                videoUrl = pollResult.videoUrl();
                break;
            }
            if (status == AvatarProvider.RemoteStatus.FAILED) {
                throw new RuntimeException("数字人生成失败：" + pollResult.errorMessage());
            }
            if (System.currentTimeMillis() >= deadline) {
                throw new RuntimeException("生成超时，请稍后重试");
            }
            sleep(5000L);
        }

        if (videoUrl == null || videoUrl.isBlank()) {
            throw new RuntimeException("数字人生成失败：未返回产物地址");
        }

        String path = download(videoUrl, "avatar", "mp4");
        registerAsset(path, com.dramafactory.model.AssetType.VIDEO, extractRunId(options), providerName, prompt);
        return new GenerateResponse("SUCCEEDED", path, null);
    }

    // 注意：返回值必须是 musicProvidersByName 等 Map 的 key，即 bean 名转小写
    //（toNameMap 做的），写错一个字符就会导致"暂未接入"。改 bean 名时同步改这里。
    static String matchImage(String lowerName) {
        if (lowerName.contains("dashscope") || lowerName.contains("qwen")
                || lowerName.contains("万相") || lowerName.contains("通义")
                || lowerName.contains("image")) {
            return "dashscopeimageprovider";
        }
        return null;
    }


    // 注意：返回值必须是 musicProvidersByName 的 key，即 bean 名转小写
    //（toNameMap 做的），写错一个字符就会导致"暂未接入"。改 bean 名时同步改这里。
    static String matchMusic(String lowerName) {
        if (lowerName.contains("minimax")) {
            return "minimaxmusicprovider";
        }
        if (lowerName.contains("ace-step") || lowerName.contains("acestep")) {
            return "acestepmusicprovider";
        }
        return null;
    }


    // 注意：返回值必须是 avatarProvidersByName 的 key，即 bean 名转小写
    //（toNameMap 做的），写错一个字符就会导致"暂未接入"。改 bean 名时同步改这里。
    static String matchAvatar(String lowerName) {
        if (lowerName.contains("d-id") || lowerName.contains("did") || lowerName.contains("数字人")) {
            return "didavatarprovider";
        }
        return null;
    }


    private static void sleep(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("生成被中断");
        }
    }

    private String download(String url, String subdir, String extHint) {
        HttpResponse<InputStream> response;
        try {
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .timeout(Duration.ofSeconds(30))
                    .GET()
                    .build();

            response = downloadSender.send(request);

        } catch (IOException e) {
            throw new RuntimeException("产物下载失败：" + e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new RuntimeException("生成被中断");
        }

        int statusCode = response.statusCode();
        if (statusCode < 200 || statusCode >= 300) {
            try (InputStream ignored = response.body()) {
                // drain and ignore
            } catch (IOException ignored) {
                // ignore
            }
            throw new RuntimeException("产物下载失败，HTTP " + statusCode);
        }

        String ext = resolveExtension(url, extHint);
        String filename = buildFilename(subdir, ext);

        Path dir = Paths.get(storageDir, "byok", subdir);
        try {
            Files.createDirectories(dir);
        } catch (IOException e) {
            throw new RuntimeException("产物下载失败：" + e.getMessage());
        }

        Path target = dir.resolve(filename);
        try (InputStream body = response.body()) {
            Files.copy(body, target, StandardCopyOption.REPLACE_EXISTING);
        } catch (IOException e) {
            throw new RuntimeException("产物下载失败：" + e.getMessage());
        }

        return "/api/byok/file/" + subdir + "/" + filename;
    }

    private static String resolveExtension(String url, String extHint) {
        String candidate = null;
        if (url != null) {
            String path = url;
            int queryIdx = path.indexOf('?');
            if (queryIdx >= 0) {
                path = path.substring(0, queryIdx);
            }
            int hashIdx = path.indexOf('#');
            if (hashIdx >= 0) {
                path = path.substring(0, hashIdx);
            }
            int slashIdx = path.lastIndexOf('/');
            String lastSegment = slashIdx >= 0 ? path.substring(slashIdx + 1) : path;
            int dotIdx = lastSegment.lastIndexOf('.');
            if (dotIdx >= 0 && dotIdx < lastSegment.length() - 1) {
                candidate = lastSegment.substring(dotIdx + 1).toLowerCase(Locale.ROOT);
            }
        }
        if (candidate != null && isAllowedExt(candidate)) {
            return candidate;
        }
        if (extHint != null) {
            String hint = extHint.toLowerCase(Locale.ROOT);
            if (isAllowedExt(hint)) {
                return hint;
            }
        }
        throw new IllegalStateException("无法确定文件扩展名：url 与 extHint 均无合法扩展名：url=" + url + "，extHint=" + extHint);
    }

    private static boolean isAllowedExt(String ext) {
        return ext.equals("png") || ext.equals("jpg") || ext.equals("jpeg")
                || ext.equals("mp3") || ext.equals("mp4");
    }

    private static String buildFilename(String subdir, String ext) {
        String ts = LocalDateTime.now().format(FILE_TS);
        StringBuilder sb = new StringBuilder(8);
        for (int i = 0; i < 8; i++) {
            sb.append(RANDOM_ALPHABET.charAt(RANDOM.nextInt(RANDOM_ALPHABET.length())));
        }
        return "byok-" + subdir + "-" + ts + "-" + sb + "." + ext;
    }

    private Long extractRunId(java.util.Map<String, String> options) {
        if (options == null) {
            return null;
        }
        String raw = options.get("runId");
        if (raw == null || raw.isBlank()) {
            return null;
        }
        try {
            return Long.parseLong(raw.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private void registerAsset(String path, com.dramafactory.model.AssetType type,
                               Long runId, String provider, String prompt) {
        if (assetService == null || path == null) {
            return;
        }
        try {
            java.nio.file.Path p = java.nio.file.Paths.get(storageDir, path.replaceFirst("^/api/byok/file/", "byok/"));
            String mime = type == com.dramafactory.model.AssetType.IMAGE ? "image/png"
                    : type == com.dramafactory.model.AssetType.AUDIO ? "audio/mpeg" : "video/mp4";
            long size = java.nio.file.Files.exists(p) ? java.nio.file.Files.size(p) : 0L;
            assetService.registerGenerated(path, type, mime, size, provider, prompt, runId);
        } catch (Exception e) {
            // 资产登记失败不阻断主流程
        }
    }
}
