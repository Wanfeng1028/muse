package com.dramafactory.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

/**
 * {@link CinematographyVocabulary} 的深度单元测试。
 *
 * <p>纯单元测试，直接 new 出被测对象，不启动 Spring 上下文、不访问网络、不 mock 任何东西
 * （被测逻辑全部走真实实现，包括 Jackson 解析与文件读取）。</p>
 */
class CinematographyVocabularyDeepTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    private static final String MISSING_PATH = "data/cinematography/does-not-exist.json";

    private CinematographyVocabulary defaultVocab() {
        return new CinematographyVocabulary(MISSING_PATH, objectMapper);
    }

    private CinematographyVocabulary fromJson(String json, Path dir) throws Exception {
        Path file = dir.resolve("vocabulary.json");
        Files.writeString(file, json, StandardCharsets.UTF_8);
        return new CinematographyVocabulary(file.toString(), objectMapper);
    }

    /**
     * 未知景别词条必须回退为 Optional.empty，而不是抛异常或编造英文。
     */
    @Test
    void unknownShotSizeLabelFallsBackToEmptyOptional() {
        CinematographyVocabulary vocab = defaultVocab();
        assertThat(vocab.englishShotSize("完全不存在的景别")).isEmpty();
    }

    /**
     * 未知运镜/光线/构图词条同样回退为 empty。
     */
    @Test
    void unknownLabelsForAllCategoriesFallBackToEmptyOptional() {
        CinematographyVocabulary vocab = defaultVocab();
        assertThat(vocab.englishCameraMove("不存在的运镜")).isEmpty();
        assertThat(vocab.englishLighting("不存在的光线")).isEmpty();
        assertThat(vocab.englishComposition("不存在的构图")).isEmpty();
    }

    /**
     * 中文标签两侧的空白会被 trim 后再匹配；纯空白与 null 视为无匹配。
     */
    @Test
    void lookupTrimsSurroundingWhitespaceAndRejectsBlankOrNull() {
        CinematographyVocabulary vocab = defaultVocab();
        assertThat(vocab.englishShotSize("  特写  ")).contains("close-up");
        assertThat(vocab.englishShotSize("   ")).isEmpty();
        assertThat(vocab.englishShotSize("\t\n")).isEmpty();
        assertThat(vocab.englishShotSize(null)).isEmpty();
        assertThat(vocab.englishCameraMove("   ")).isEmpty();
        assertThat(vocab.englishLighting(null)).isEmpty();
        assertThat(vocab.englishComposition("   ")).isEmpty();
    }

    /**
     * 大小写敏感：匹配为精确字符串比较，大小写不同不应命中英文键以外的中文标签。
     * 中文标签本身无大小写，但构造自定义词表验证 label 精确匹配语义。
     */
    @Test
    void lookupIsExactMatchAndCaseSensitive(@TempDir Path tempDir) throws Exception {
        String json = "{"
                + "\"version\":\"case-test\","
                + "\"shotSize\":[{\"label\":\"Close\",\"en\":\"close-up\"}],"
                + "\"cameraMove\":[],"
                + "\"cameraAngle\":[],"
                + "\"lighting\":[],"
                + "\"composition\":[]"
                + "}";
        CinematographyVocabulary vocab = fromJson(json, tempDir);
        assertThat(vocab.englishShotSize("Close")).contains("close-up");
        assertThat(vocab.englishShotSize("close")).isEmpty();
        assertThat(vocab.englishShotSize("CLOSE")).isEmpty();
    }

    /**
     * 当词表缺少某个数组字段（merge/缺失节点场景）时，对应类别应解析为空列表，
     * 查询一律回退为 empty，且 renderAppendix 仍能正常输出。
     */
    @Test
    void missingArrayNodesDegradeToEmptyListsAndEmptyLookups(@TempDir Path tempDir) throws Exception {
        String json = "{"
                + "\"version\":\"sparse\","
                + "\"shotSize\":[{\"label\":\"特写\",\"en\":\"close-up\"}]"
                + "}";
        CinematographyVocabulary vocab = fromJson(json, tempDir);
        assertThat(vocab.englishShotSize("特写")).contains("close-up");
        assertThat(vocab.englishCameraMove("推镜")).isEmpty();
        assertThat(vocab.englishLighting("柔光")).isEmpty();
        assertThat(vocab.englishComposition("三分法")).isEmpty();
        assertThat(vocab.renderAppendix()).contains("close-up");
    }

    /**
     * 空输入场景：全部入参为 null / 空串 / 空列表时 buildShotPrompt 返回空串。
     */
    @Test
    void buildShotPromptReturnsEmptyStringForAllEmptyInputs() {
        CinematographyVocabulary vocab = defaultVocab();
        assertThat(vocab.buildShotPrompt(null, null, null, null, null, null)).isEmpty();
        assertThat(vocab.buildShotPrompt("", "", "   ", new ArrayList<>(), "", "   ")).isEmpty();
        assertThat(vocab.buildShotPrompt(null, null, null, List.of(), null, null)).isEmpty();
    }

    /**
     * buildShotPrompt 中未知标签层应被跳过，不得编造英文；主体与风格仍拼接。
     */
    @Test
    void buildShotPromptSkipsUnknownLayersWithoutInventingEnglish() {
        CinematographyVocabulary vocab = defaultVocab();
        String prompt = vocab.buildShotPrompt(
                "不存在的景别", "不存在的运镜", "一只猫在窗边", List.of("暖色调"), "不存在的光线", "cinematic");
        assertThat(prompt).isEqualTo("一只猫在窗边, 暖色调. Style: cinematic");
        assertThat(prompt).doesNotContain("不存在的景别");
        assertThat(prompt).doesNotContain("不存在的运镜");
        assertThat(prompt).doesNotContain("不存在的光线");
    }

    /**
     * buildShotPrompt 应按 camera -> movement -> subject -> lighting -> style 顺序用 ". " 连接，
     * 并剔除纹理关键词中的 null 与空白项。
     */
    @Test
    void buildShotPromptOrdersLayersAndFiltersBlankTextureKeywords() {
        CinematographyVocabulary vocab = defaultVocab();
        List<String> textures = new ArrayList<>();
        textures.add("  暖光  ");
        textures.add(null);
        textures.add("   ");
        String prompt = vocab.buildShotPrompt("特写", "推镜", "  主角的脸  ", textures, "柔光", "  noir  ");
        assertThat(prompt).startsWith("close-up. push-in. 主角的脸, 暖光");
        assertThat(prompt).contains("Style: noir");
        assertThat(prompt).doesNotContain("null");
        assertThat(prompt.split("\\. ", -1).length).isGreaterThanOrEqualTo(4);
    }

    /**
     * 自定义词表 merge 冲突：同名 label 出现多条时，按顺序命中第一条（先到先得策略）。
     */
    @Test
    void duplicateLabelsResolveToFirstEntryInDeclarationOrder(@TempDir Path tempDir) throws Exception {
        String json = "{"
                + "\"version\":\"dup\","
                + "\"shotSize\":["
                + "{\"label\":\"特写\",\"en\":\"first-close-up\"},"
                + "{\"label\":\"特写\",\"en\":\"second-close-up\"}"
                + "],"
                + "\"cameraMove\":[]"
                + "}";
        CinematographyVocabulary vocab = fromJson(json, tempDir);
        assertThat(vocab.englishShotSize("特写")).contains("first-close-up");
        assertThat(vocab.renderAppendix()).contains("first-close-up");
    }

    /**
     * 自定义词表中 en 为 null 时，查询应返回 empty 而非 null。
     */
    @Test
    void nullEnglishValueYieldsEmptyOptional(@TempDir Path tempDir) throws Exception {
        String json = "{"
                + "\"version\":\"null-en\","
                + "\"shotSize\":[{\"label\":\"特写\"}],"
                + "\"cameraMove\":[]"
                + "}";
        CinematographyVocabulary vocab = fromJson(json, tempDir);
        Optional<String> result = vocab.englishShotSize("特写");
        assertThat(result).isEmpty();
    }

    /**
     * 非法 JSON 文件必须抛 IllegalStateException（大声失败），不得静默返回空词表。
     */
    @Test
    void malformedJsonFileThrowsIllegalStateException(@TempDir Path tempDir) throws Exception {
        Path file = tempDir.resolve("broken.json");
        Files.writeString(file, "{ this is not valid json ", StandardCharsets.UTF_8);
        assertThatThrownBy(() -> new CinematographyVocabulary(file.toString(), objectMapper))
                .isInstanceOf(IllegalStateException.class)
                .hasMessageContaining("解析镜头语言词汇表文件失败");
    }

    /**
     * 文件路径为空白串时跳过文件分支直接走 classpath；classpath 资源存在则正常加载。
     */
    @Test
    void blankPathFallsBackToClasspathResource() {
        CinematographyVocabulary vocab = new CinematographyVocabulary("   ", objectMapper);
        assertThat(vocab.englishShotSize("特写")).contains("close-up");
        assertThat(vocab.renderAppendix()).contains("push-in");
    }

    /**
     * 并发读取安全：多线程同时查询与渲染附录，结果一致且无异常。
     */
    @Test
    void concurrentReadsAreSafeAndConsistent() throws Exception {
        CinematographyVocabulary vocab = defaultVocab();
        String expectedAppendix = vocab.renderAppendix();
        int threads = 8;
        int iterations = 200;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        List<Future<String>> futures = new ArrayList<>();
        try {
            Callable<String> task = () -> {
                startGate.await(5, TimeUnit.SECONDS);
                String last = null;
                for (int i = 0; i < iterations; i++) {
                    Optional<String> shot = vocab.englishShotSize("特写");
                    if (shot.isEmpty() || !"close-up".equals(shot.get())) {
                        return "SHOT_MISMATCH:" + shot;
                    }
                    String appendix = vocab.renderAppendix();
                    if (!expectedAppendix.equals(appendix)) {
                        return "APPENDIX_MISMATCH";
                    }
                    last = appendix;
                }
                return last;
            };
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(task));
            }
            startGate.countDown();
            for (Future<String> f : futures) {
                String result = f.get(30, TimeUnit.SECONDS);
                assertThat(result).isEqualTo(expectedAppendix);
            }
        } finally {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
    }

    /**
     * 并发构造多个实例（模拟失败注入下的高频加载）不应互相干扰，且每个实例都能独立查询。
     */
    @Test
    void concurrentConstructionProducesIndependentInstances() throws Exception {
        int threads = 6;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch startGate = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();
        List<Future<CinematographyVocabulary>> futures = new ArrayList<>();
        try {
            for (int i = 0; i < threads; i++) {
                futures.add(pool.submit(() -> {
                    startGate.await(5, TimeUnit.SECONDS);
                    try {
                        return new CinematographyVocabulary(MISSING_PATH, objectMapper);
                    } catch (Throwable t) {
                        failure.compareAndSet(null, t);
                        throw t;
                    }
                }));
            }
            startGate.countDown();
            for (Future<CinematographyVocabulary> f : futures) {
                CinematographyVocabulary vocab = f.get(30, TimeUnit.SECONDS);
                assertThat(vocab.englishShotSize("特写")).contains("close-up");
            }
        } finally {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
        assertThat(failure.get()).isNull();
    }

    /**
     * 中断注入：等待中的并发任务被中断时，Future 抛 CancellationException 或 InterruptedException，
     * 但共享的被测对象不受影响，后续查询仍正常。
     */
    @Test
    void interruptedConcurrentReaderDoesNotCorruptVocabulary() throws Exception {
        CinematographyVocabulary vocab = defaultVocab();
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch entered = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            Future<String> blocked = pool.submit(() -> {
                entered.countDown();
                release.await(10, TimeUnit.SECONDS);
                return vocab.englishShotSize("特写").orElse("MISSING");
            });
            assertThat(entered.await(5, TimeUnit.SECONDS)).isTrue();
            assertThat(blocked.cancel(true)).isTrue();
            release.countDown();
            assertThatThrownBy(blocked::get)
                    .isInstanceOf(java.util.concurrent.CancellationException.class);
        } finally {
            pool.shutdownNow();
            assertThat(pool.awaitTermination(10, TimeUnit.SECONDS)).isTrue();
        }
        assertThat(vocab.englishShotSize("特写")).contains("close-up");
        assertThat(vocab.renderAppendix()).contains("push-in");
    }

    /**
     * 版本号：缺失 version 字段时返回空串；存在时按原文返回，不做 trim 处理之外的变化。
     */
    @Test
    void versionDefaultsToEmptyStringWhenAbsent(@TempDir Path tempDir) throws Exception {
        String jsonNoVersion = "{"
                + "\"shotSize\":[{\"label\":\"特写\",\"en\":\"close-up\"}],"
                + "\"cameraMove\":[]"
                + "}";
        CinematographyVocabulary vocab = fromJson(jsonNoVersion, tempDir);
        assertThat(vocab.getVersion()).isEmpty();
        assertThat(vocab.englishShotSize("特写")).contains("close-up");
    }

    /**
     * renderAppendix 输出结构：空词表时仍包含规则段落，但类别行为空，不抛异常。
     */
    @Test
    void renderAppendixHandlesEmptyVocabularyGracefully(@TempDir Path tempDir) throws Exception {
        String json = "{"
                + "\"version\":\"empty\","
                + "\"shotSize\":[],"
                + "\"cameraMove\":[],"
                + "\"cameraAngle\":[],"
                + "\"lighting\":[],"
                + "\"composition\":[]"
                + "}";
        CinematographyVocabulary vocab = fromJson(json, tempDir);
        String appendix = vocab.renderAppendix();
        assertThat(appendix).contains("Shot size");
        assertThat(appendix).contains("Rules:");
        assertThat(appendix).contains("Optional camera angles");
        assertThat(appendix).doesNotContain("null");
    }
}
