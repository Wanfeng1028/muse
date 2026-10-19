package com.dramafactory.tools.service;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.service.FfmpegService;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.tools.model.ToolOpLog;
import com.dramafactory.tools.repository.ToolOpLogRepository;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.nio.charset.StandardCharsets;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.fail;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:quicktoolsdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE"
})
class QuickToolsServiceDeepTest {

    @Autowired
    private QuickToolsService quickToolsService;

    @Autowired
    private AssetRepository assetRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ToolOpLogRepository toolOpLogRepository;

    @Autowired
    private FfmpegService ffmpegService;

    @BeforeEach
    void setUp() {
        toolOpLogRepository.deleteAll();
        shotRepository.deleteAll();
        assetRepository.deleteAll();
        episodeRepository.deleteAll();
    }

    private Asset persistVideoAsset(String fileName, String tags) {
        Asset a = new Asset();
        a.setType(AssetType.VIDEO);
        a.setFileName(fileName);
        a.setFilePath("assets/upload/" + fileName);
        a.setMimeType("video/mp4");
        a.setFileSize(1024L);
        a.setTags(tags);
        a.setCreatedAt(LocalDateTime.now());
        a.setUpdatedAt(LocalDateTime.now());
        return assetRepository.save(a);
    }

    private Asset persistAudioAsset(String fileName) {
        Asset a = new Asset();
        a.setType(AssetType.AUDIO);
        a.setFileName(fileName);
        a.setFilePath("assets/upload/" + fileName);
        a.setMimeType("audio/mpeg");
        a.setFileSize(512L);
        a.setCreatedAt(LocalDateTime.now());
        a.setUpdatedAt(LocalDateTime.now());
        return assetRepository.save(a);
    }

    private Episode persistEpisode(String title) {
        Episode e = new Episode();
        e.setTitle(title);
        e.setCreatedAt(LocalDateTime.now());
        e.setUpdatedAt(LocalDateTime.now());
        return episodeRepository.save(e);
    }

    private List<ToolOpLog> findAllLogsByTool(String toolName) {
        List<ToolOpLog> all = toolOpLogRepository.findAll();
        List<ToolOpLog> filtered = new ArrayList<>();
        for (ToolOpLog l : all) {
            if (toolName.equals(l.getToolName())) {
                filtered.add(l);
            }
        }
        return filtered;
    }

    private void assumeFfmpegAvailable() {
        boolean available;
        try {
            ffmpegService.executeCapture(java.util.List.of(ffmpegService.getFfmpeg(), "-version"), 10L);
            available = true;
        } catch (Throwable t) {
            available = false;
        }
        Assumptions.assumeTrue(available, "ffmpeg 不可用，跳过依赖真实 ffmpeg 的测试");
    }

    // ---------- 批量打标签 ----------

    @Test
    void batchTagAssets_mergeMode_appendsAndDeduplicatesTags() {
        Asset a1 = persistVideoAsset("a1.mp4", "red,blue");
        Asset a2 = persistVideoAsset("a2.mp4", "blue");
        List<Long> ids = Arrays.asList(a1.getId(), a2.getId());

        int updated = quickToolsService.batchTagAssets(ids, "blue, green ,red", "merge");

        assertEquals(2, updated);
        Asset reloaded1 = assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new);
        Asset reloaded2 = assetRepository.findById(a2.getId()).orElseThrow(IllegalStateException::new);
        assertEquals("red,blue,green", reloaded1.getTags());
        assertEquals("blue,green", reloaded2.getTags());

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(1, logs.size());
        ToolOpLog log = logs.get(0);
        assertEquals("batch-tag", log.getOperation());
        assertTrue(log.isSuccess());
        assertEquals("count=2", log.getResult());
        assertTrue(log.getParams().contains("mode=merge"));
    }

    @Test
    void batchTagAssets_replaceMode_overwritesTags() {
        Asset a1 = persistVideoAsset("r1.mp4", "old1,old2");
        Asset a2 = persistVideoAsset("r2.mp4", "legacy");

        int updated = quickToolsService.batchTagAssets(
                Arrays.asList(a1.getId(), a2.getId()), "new1,new2", "replace");

        assertEquals(2, updated);
        assertEquals("new1,new2",
                assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new).getTags());
        assertEquals("new1,new2",
                assetRepository.findById(a2.getId()).orElseThrow(IllegalStateException::new).getTags());

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(1, logs.size());
        assertTrue(logs.get(0).isSuccess());
        assertTrue(logs.get(0).getParams().contains("mode=replace"));
    }

    @Test
    void batchTagAssets_replaceModeWithEmptyTags_clearsTags() {
        Asset a1 = persistVideoAsset("e1.mp4", "to-be-cleared");

        int updated = quickToolsService.batchTagAssets(
                Collections.singletonList(a1.getId()), "  ", "replace");

        assertEquals(1, updated);
        Asset reloaded = assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new);
        assertEquals(null, reloaded.getTags());

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(1, logs.size());
        assertTrue(logs.get(0).isSuccess());
    }

    @Test
    void batchTagAssets_invalidMode_throwsAndLogsFailure() {
        Asset a1 = persistVideoAsset("im.mp4", "x");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.batchTagAssets(
                        Collections.singletonList(a1.getId()), "y", "append"));
        assertTrue(ex.getMessage().contains("mode"));

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(1, logs.size());
        ToolOpLog log = logs.get(0);
        assertTrue(!log.isSuccess());
        assertEquals("batch-tag", log.getOperation());
        assertTrue(log.getParams().contains("mode=append"));

        Asset reloaded = assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new);
        assertEquals("x", reloaded.getTags());
    }

    @Test
    void batchTagAssets_emptyIds_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.batchTagAssets(Collections.emptyList(), "t", "merge"));
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.batchTagAssets(null, "t", "merge"));

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(0, logs.size());
    }

    @Test
    void batchTagAssets_missingAsset_throwsResourceNotFoundAndLogsFailure() {
        Asset a1 = persistVideoAsset("exists.mp4", "t1");
        long missingId = a1.getId() + 99999L;

        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.batchTagAssets(
                        Arrays.asList(a1.getId(), missingId), "z", "merge"));
        assertNotNull(ex.getMessage());

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());

        Asset reloaded = assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new);
        assertEquals("t1", reloaded.getTags());
    }

    // ---------- 批量重命名 ----------

    @Test
    void batchRenameAssets_updatesFileNamesAndLogsSuccess() {
        Asset a1 = persistVideoAsset("orig1.mp4", null);
        Asset a2 = persistVideoAsset("orig2.mp4", null);

        Map<Long, String> renames = new HashMap<>();
        renames.put(a1.getId(), "  renamed-one.mp4  ");
        renames.put(a2.getId(), "renamed-two.mp4");

        int updated = quickToolsService.batchRenameAssets(renames);

        assertEquals(2, updated);
        assertEquals("renamed-one.mp4",
                assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new).getFileName());
        assertEquals("renamed-two.mp4",
                assetRepository.findById(a2.getId()).orElseThrow(IllegalStateException::new).getFileName());

        List<ToolOpLog> logs = findAllLogsByTool("batchRenameAssets");
        assertEquals(1, logs.size());
        ToolOpLog log = logs.get(0);
        assertTrue(log.isSuccess());
        assertEquals("batch-rename", log.getOperation());
        assertTrue(log.getParams().contains("count=2"));
        assertEquals("count=2", log.getResult());
    }

    @Test
    void batchRenameAssets_blankName_throwsBeforeMutating() {
        Asset a1 = persistVideoAsset("keep.mp4", null);

        Map<Long, String> renames = new HashMap<>();
        renames.put(a1.getId(), "   ");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.batchRenameAssets(renames));
        assertTrue(ex.getMessage().contains("文件名"));

        assertEquals("keep.mp4",
                assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new).getFileName());

        List<ToolOpLog> logs = findAllLogsByTool("batchRenameAssets");
        assertEquals(0, logs.size());
    }

    @Test
    void batchRenameAssets_missingAsset_throwsAndLogsFailure() {
        Asset a1 = persistVideoAsset("present.mp4", null);

        Map<Long, String> renames = new HashMap<>();
        renames.put(a1.getId(), "present-renamed.mp4");
        renames.put(a1.getId() + 12345L, "ghost.mp4");

        assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.batchRenameAssets(renames));

        List<ToolOpLog> logs = findAllLogsByTool("batchRenameAssets");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());

        // 由于整个方法在同一事务中，失败不应提交任何变更
        assertEquals("present.mp4",
                assetRepository.findById(a1.getId()).orElseThrow(IllegalStateException::new).getFileName());
    }

    // ---------- CSV 导出 ----------

    @Test
    void exportShotCsv_producesBomHeaderAndRowsInShotNoOrder() {
        Episode episode = persistEpisode("Ep-1");

        Shot s1 = new Shot();
        s1.setEpisode(episode);
        s1.setShotNo(1);
        s1.setDescription("开场");
        s1.setDialogue("你好, 世界");
        s1.setDurationSeconds(5);
        s1.setCreatedAt(LocalDateTime.of(2024, 1, 2, 3, 4));
        s1.setUpdatedAt(LocalDateTime.now());
        shotRepository.save(s1);

        Shot s2 = new Shot();
        s2.setEpisode(episode);
        s2.setShotNo(2);
        s2.setDescription("带\"引号\"");
        s2.setDurationSeconds(7);
        s2.setCreatedAt(LocalDateTime.of(2024, 1, 2, 3, 5));
        s2.setUpdatedAt(LocalDateTime.now());
        shotRepository.save(s2);

        byte[] csv = quickToolsService.exportShotCsv(episode.getId());
        assertNotNull(csv);

        String text = new String(csv, StandardCharsets.UTF_8);
        assertTrue(text.startsWith("\uFEFF"), "CSV 必须以 BOM 开头");
        String body = text.substring(1);

        assertTrue(body.contains("镜号,景别,运镜,画面描述,台词,时长(秒),创建时间"));
        assertTrue(body.contains("开场"));
        assertTrue(body.contains("\"你好, 世界\""));
        assertTrue(body.contains("\"带\"\"引号\"\"\""));
        assertTrue(body.contains("2024-01-02 03:04"));
        assertTrue(body.contains("2024-01-02 03:05"));

        int idxRow1 = body.indexOf("开场");
        int idxRow2 = body.indexOf("带\"\"引号\"\"");
        assertTrue(idxRow1 > 0 && idxRow2 > idxRow1, "行应按 shotNo 升序");

        List<ToolOpLog> logs = findAllLogsByTool("exportShotCsv");
        assertEquals(1, logs.size());
        ToolOpLog log = logs.get(0);
        assertTrue(log.isSuccess());
        assertEquals("episode-shots-csv", log.getOperation());
        assertEquals("rows=2", log.getResult());
        assertEquals("episodeId=" + episode.getId(), log.getParams());
    }

    @Test
    void exportShotCsv_missingEpisode_throwsAndLogsFailure() {
        long missingId = 987654321L;

        assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.exportShotCsv(missingId));

        List<ToolOpLog> logs = findAllLogsByTool("exportShotCsv");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());
        assertEquals("episodeId=" + missingId, logs.get(0).getParams());
    }

    // ---------- 审计日志 ----------

    @Test
    void auditLogs_areWrittenWithExpectedFieldsAndOrderedByCreatedAt() {
        Asset a1 = persistVideoAsset("audit.mp4", "seed");
        quickToolsService.batchTagAssets(Collections.singletonList(a1.getId()), "x", "merge");
        quickToolsService.batchRenameAssets(Collections.singletonMap(a1.getId(), "audit2.mp4"));

        List<ToolOpLog> top = toolOpLogRepository.findTop50ByOrderByCreatedAtDesc();
        assertEquals(2, top.size());
        // 最近一次应为 batchRenameAssets
        assertEquals("batchRenameAssets", top.get(0).getToolName());
        assertEquals("batch-rename", top.get(0).getOperation());
        assertTrue(top.get(0).isSuccess());
        assertEquals("count=1", top.get(0).getResult());
        assertEquals("batchTagAssets", top.get(1).getToolName());
        assertEquals("batch-tag", top.get(1).getOperation());

        List<ToolOpLog> all = toolOpLogRepository.findAll();
        for (ToolOpLog l : all) {
            assertNotNull(l.getCreatedAt());
            assertNotNull(l.getToolName());
            assertNotNull(l.getOperation());
        }
    }

    // ---------- 并发批量操作 ----------

    @Test
    void concurrentBatchTagAssets_onDistinctAssets_allSucceed() throws InterruptedException {
        int n = 6;
        List<Long> ids = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            ids.add(persistVideoAsset("c" + i + ".mp4", "init").getId());
        }

        ExecutorService pool = Executors.newFixedThreadPool(n);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(n);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failure = new AtomicInteger();

        for (int i = 0; i < n; i++) {
            final Long id = ids.get(i);
            final int idx = i;
            pool.submit(() -> {
                try {
                    start.await();
                    quickToolsService.batchTagAssets(
                            Collections.singletonList(id), "tag" + idx, "merge");
                    success.incrementAndGet();
                } catch (Throwable t) {
                    failure.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }

        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS), "并发任务未在超时内完成");
        pool.shutdownNow();

        assertEquals(n, success.get(), "所有并发打标签都应成功");
        assertEquals(0, failure.get());

        for (int i = 0; i < n; i++) {
            Asset reloaded = assetRepository.findById(ids.get(i)).orElseThrow(IllegalStateException::new);
            assertEquals("init,tag" + i, reloaded.getTags());
        }

        List<ToolOpLog> logs = findAllLogsByTool("batchTagAssets");
        assertEquals(n, logs.size());
        int okCount = 0;
        for (ToolOpLog l : logs) {
            if (l.isSuccess()) {
                okCount++;
            }
        }
        assertEquals(n, okCount);
    }

    @Test
    void concurrentBatchRenameAssets_onSameAsset_neverCorruptsState() throws InterruptedException {
        Asset a1 = persistVideoAsset("shared.mp4", null);
        final Long id = a1.getId();

        int n = 4;
        ExecutorService pool = Executors.newFixedThreadPool(n);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(n);
        AtomicInteger success = new AtomicInteger();
        AtomicInteger failure = new AtomicInteger();

        for (int i = 0; i < n; i++) {
            final String newName = "shared-" + i + ".mp4";
            pool.submit(() -> {
                try {
                    start.await();
                    quickToolsService.batchRenameAssets(Collections.singletonMap(id, newName));
                    success.incrementAndGet();
                } catch (Throwable t) {
                    failure.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }

        start.countDown();
        assertTrue(done.await(30, TimeUnit.SECONDS), "并发重命名未在超时内完成");
        pool.shutdownNow();

        assertEquals(n, success.get() + failure.get());

        Asset reloaded = assetRepository.findById(id).orElseThrow(IllegalStateException::new);
        assertNotNull(reloaded.getFileName());
        assertTrue(reloaded.getFileName().startsWith("shared-"),
                "文件名应被某次成功操作覆盖，实际=" + reloaded.getFileName());

        // 只要成功过，审计日志条数必须等于成功次数
        List<ToolOpLog> logs = findAllLogsByTool("batchRenameAssets");
        assertEquals(success.get(), logs.size());
    }

    // ---------- ffmpeg 相关 ----------

    @Test
    void convertVideo_rejectsNonVideoAsset() {
        Asset audio = persistAudioAsset("audio.mp3");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.convertVideo(audio.getId(), "mp4", 720));
        assertTrue(ex.getMessage().contains("视频"));

        List<ToolOpLog> logs = findAllLogsByTool("convertVideo");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());
    }

    @Test
    void convertVideo_invalidFormat_throwsBeforeLookup() {
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.convertVideo(1L, "avi", 720));
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.convertVideo(1L, "mp4", 10));

        List<ToolOpLog> logs = findAllLogsByTool("convertVideo");
        assertEquals(0, logs.size());
    }

    @Test
    void extractAudio_rejectsNonVideoAsset() {
        Asset audio = persistAudioAsset("audio2.mp3");

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.extractAudio(audio.getId(), "mp3"));
        assertTrue(ex.getMessage().contains("视频"));

        List<ToolOpLog> logs = findAllLogsByTool("extractAudio");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());
    }

    @Test
    void extractAudio_invalidFormat_throwsBeforeLookup() {
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.extractAudio(1L, "ogg"));

        List<ToolOpLog> logs = findAllLogsByTool("extractAudio");
        assertEquals(0, logs.size());
    }

    @Test
    void convertVideo_missingAsset_logsFailure() {
        assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.convertVideo(42424242L, "mp4", 720));

        List<ToolOpLog> logs = findAllLogsByTool("convertVideo");
        assertEquals(1, logs.size());
        assertTrue(!logs.get(0).isSuccess());
        assertTrue(logs.get(0).getParams().contains("assetId=42424242"));
    }

    @Test
    void convertVideo_endToEnd_whenFfmpegAvailable() {
        assumeFfmpegAvailable();

        // 先验证 ffmpeg 可用性判断没有误报；随后由于没有真实可用的源视频文件，
        // 直接调用会因 resolveStoragePath / ffmpeg 处理失败而抛出，这属于合理失败路径。
        Asset asset = persistVideoAsset("e2e.mp4", null);

        try {
            Asset created = quickToolsService.convertVideo(asset.getId(), "mp4", 720);
            assertNotNull(created);
            assertNotNull(created.getId());
            assertNotNull(created.getFilePath());
            List<ToolOpLog> logs = findAllLogsByTool("convertVideo");
            assertEquals(1, logs.size());
            assertTrue(logs.get(0).isSuccess());
        } catch (RuntimeException e) {
            // 源文件不存在 → ffmpeg 或 size 读取失败，审计必须记录失败
            List<ToolOpLog> logs = findAllLogsByTool("convertVideo");
            assertEquals(1, logs.size(), "失败路径必须写审计日志");
            assertTrue(!logs.get(0).isSuccess());
        }
    }

    @Test
    void extractAudio_endToEnd_whenFfmpegAvailable() {
        assumeFfmpegAvailable();

        Asset asset = persistVideoAsset("e2e-audio.mp4", null);

        try {
            Asset created = quickToolsService.extractAudio(asset.getId(), "mp3");
            assertNotNull(created);
            assertNotNull(created.getId());
            assertEquals(AssetType.AUDIO, created.getType());
            List<ToolOpLog> logs = findAllLogsByTool("extractAudio");
            assertEquals(1, logs.size());
            assertTrue(logs.get(0).isSuccess());
        } catch (RuntimeException e) {
            List<ToolOpLog> logs = findAllLogsByTool("extractAudio");
            assertEquals(1, logs.size(), "失败路径必须写审计日志");
            assertTrue(!logs.get(0).isSuccess());
        }
    }
}
