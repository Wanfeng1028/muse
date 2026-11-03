package com.dramafactory;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.service.AssetService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.TestPropertySource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:assetdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "drama.storage=./target/test-media-assetdeep"
})
class AssetServiceDeepTest {

    @Autowired
    private AssetService assetService;

    @Autowired
    private AssetRepository assetRepository;

    private Path storageRoot;

    @BeforeEach
    void setUp() throws IOException {
        assetRepository.deleteAll();
        storageRoot = Paths.get("./target/test-media-assetdeep").toAbsolutePath().normalize();
        deleteRecursively(storageRoot);
        Files.createDirectories(storageRoot);
    }

    @AfterEach
    void tearDown() throws IOException {
        assetRepository.deleteAll();
        deleteRecursively(storageRoot);
    }

    private void deleteRecursively(Path root) throws IOException {
        if (!Files.exists(root)) {
            return;
        }
        try (var walk = Files.walk(root)) {
            walk.sorted((a, b) -> b.getNameCount() - a.getNameCount())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException ignored) {
                        }
                    });
        }
    }

    private MockMultipartFile imageFile(String name, int sizeBytes) {
        byte[] data = new byte[sizeBytes];
        for (int i = 0; i < sizeBytes; i++) {
            data[i] = (byte) ('a' + (i % 26));
        }
        return new MockMultipartFile("file", name, "image/png", data);
    }

    @Test
    void uploadThenTagThenDeleteLifecycle() {
        // given 一个 1KB 的 png 素材
        MockMultipartFile file = imageFile("life.png", 1024);

        // when 上传
        Asset uploaded = assetService.upload(file, "a,b", 100L);

        // then 落库字段正确且磁盘文件存在
        assertNotNull(uploaded.getId());
        assertEquals(AssetType.IMAGE, uploaded.getType());
        assertEquals(AssetSource.UPLOADED, uploaded.getSource());
        assertEquals("life.png", uploaded.getFileName());
        assertEquals(1024L, uploaded.getFileSize());
        assertEquals("a,b", uploaded.getTags());
        assertEquals(100L, uploaded.getRunId());
        Path onDisk = storageRoot.resolve(uploaded.getFilePath()).normalize();
        assertTrue(Files.exists(onDisk), "上传后磁盘文件应存在");

        // when 打标签
        Asset tagged = assetService.tag(uploaded.getId(), "x, y , x");

        // then 标签去重去空
        assertEquals("x,y", tagged.getTags());
        assertEquals(uploaded.getId(), tagged.getId());

        // when 删除
        assetService.delete(uploaded.getId());

        // then 记录与文件都消失
        assertFalse(assetRepository.findById(uploaded.getId()).isPresent());
        assertFalse(Files.exists(onDisk), "删除后磁盘文件应消失");
    }

    @Test
    void uploadRejectsEmptyFile() {
        // given 空文件
        MockMultipartFile empty = new MockMultipartFile("file", "e.png", "image/png", new byte[0]);

        // when / then 抛参数异常
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.upload(empty, null, null));
        assertTrue(ex.getMessage().contains("上传文件不能为空"));

        // then 数据库无新增
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void uploadRejectsOversizedPayload() {
        // given 超过 1KB 上限的文件
        MockMultipartFile big = imageFile("big.png", 4096);

        // when / then 抛大小超限异常
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.upload(big, null, null, 1024L));
        assertTrue(ex.getMessage().contains("上传文件超过大小限制"));

        // then 数据库无新增
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void uploadRejectsUnsupportedMimeType() {
        // given text/plain 文件
        MockMultipartFile txt = new MockMultipartFile("file", "n.txt", "text/plain",
                "hello".getBytes(StandardCharsets.UTF_8));

        // when / then 抛不支持类型异常
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.upload(txt, null, null));
        assertTrue(ex.getMessage().contains("不支持的文件类型"));

        // then 数据库无新增
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void uploadIsIdempotentForSameLogicalAsset() {
        // given 相同内容两次上传
        MockMultipartFile file1 = imageFile("same.png", 512);
        MockMultipartFile file2 = imageFile("same.png", 512);

        // when
        Asset a1 = assetService.upload(file1, "k", 7L);
        Asset a2 = assetService.upload(file2, "k", 7L);

        // then 两次落库均为独立记录，字段一致
        assertEquals(2L, assetRepository.count());
        assertNotNull(a1.getId());
        assertNotNull(a2.getId());
        assertFalse(a1.getId().equals(a2.getId()), "两次上传应生成不同主键");
        assertEquals(a1.getType(), a2.getType());
        assertEquals(a1.getFileName(), a2.getFileName());
        assertEquals(a1.getFileSize(), a2.getFileSize());
        assertEquals(a1.getTags(), a2.getTags());
        assertEquals(a1.getRunId(), a2.getRunId());

        // then 两次落盘的路径不同
        assertFalse(a1.getFilePath().equals(a2.getFilePath()));
    }

    @Test
    void tagIsIdempotentWhenAppliedTwice() {
        // given 一个已上传资产
        Asset uploaded = assetService.upload(imageFile("t.png", 128), "old", null);

        // when 连续两次设置同一标签集合
        Asset first = assetService.tag(uploaded.getId(), "p,q");
        Asset second = assetService.tag(uploaded.getId(), "p,q");

        // then 标签一致，主键不变，库中只一条
        assertEquals("p,q", first.getTags());
        assertEquals("p,q", second.getTags());
        assertEquals(uploaded.getId(), second.getId());
        assertEquals(1L, assetRepository.count());
    }

    @Test
    void tagThrowsWhenAssetMissing() {
        // given 不存在的 id
        long missingId = 987654321L;

        // when / then 抛 ResourceNotFoundException
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> assetService.tag(missingId, "x"));
        assertTrue(ex.getMessage().contains("Asset"));
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)));

        // then 无副作用
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void deleteRejectsIllegalFilePath() {
        // given 手工写入一条非法 filePath 的记录
        Asset asset = new Asset();
        asset.setType(AssetType.IMAGE);
        asset.setSource(AssetSource.UPLOADED);
        asset.setFileName("evil.png");
        asset.setFilePath("../etc/passwd");
        asset.setMimeType("image/png");
        asset.setFileSize(10L);
        Asset saved = assetRepository.save(asset);

        // when / then 拒绝删除
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.delete(saved.getId()));
        assertTrue(ex.getMessage().contains("非法的资产文件路径"));

        // then 记录仍在
        assertTrue(assetRepository.findById(saved.getId()).isPresent());
    }

    @Test
    void deleteThrowsWhenAssetMissing() {
        // given 不存在的 id
        long missingId = 123123123L;

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> assetService.delete(missingId));
        assertTrue(ex.getMessage().contains("Asset"));
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)));

        // then
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void reuseUpdatesEpisodeAndShotAndIsIdempotent() {
        // given 已上传资产
        Asset uploaded = assetService.upload(imageFile("r.png", 256), null, 55L);

        // when 首次复用
        Asset first = assetService.reuse(uploaded.getId(), 11L, 22L);
        // when 重复同一复用调用
        Asset second = assetService.reuse(uploaded.getId(), 11L, 22L);

        // then 幂等且字段正确
        assertEquals(11L, first.getEpisodeId());
        assertEquals(22L, first.getShotId());
        assertEquals(11L, second.getEpisodeId());
        assertEquals(22L, second.getShotId());
        assertEquals(uploaded.getId(), second.getId());
        assertEquals(55L, second.getRunId());
        assertEquals(1L, assetRepository.count());
    }

    @Test
    void reuseThrowsWhenAssetMissing() {
        // given
        long missingId = 424242L;

        // when / then
        ResourceNotFoundException ex = assertThrows(ResourceNotFoundException.class,
                () -> assetService.reuse(missingId, 1L, 2L));
        assertTrue(ex.getMessage().contains("Asset"));
        assertTrue(ex.getMessage().contains(String.valueOf(missingId)));

        // then
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void registerGeneratedNormalizesPrefixAndIsIdempotent() {
        // given 生成资产路径不带 assets/ 前缀
        String rawPath = "byok/abc.png";

        // when 两次登记
        Asset first = assetService.registerGenerated(rawPath, AssetType.IMAGE, "image/png",
                2048L, "providerX", "a prompt", 9L);
        Asset second = assetService.registerGenerated(rawPath, AssetType.IMAGE, "image/png",
                2048L, "providerX", "a prompt", 9L);

        // then 路径统一到 assets/ 下，fileName 为最后一段
        assertTrue(first.getFilePath().startsWith("assets/"));
        assertEquals("assets/byok/abc.png", first.getFilePath());
        assertEquals("abc.png", first.getFileName());
        assertEquals(AssetSource.GENERATED, first.getSource());
        assertEquals("providerX", first.getProvider());
        assertEquals("a prompt", first.getPrompt());
        assertEquals(9L, first.getRunId());

        // then 两次登记产生两条独立记录
        assertEquals(2L, assetRepository.count());
        assertFalse(first.getId().equals(second.getId()));
    }

    @Test
    void registerGeneratedRejectsBlankPath() {
        // given 空路径
        String blank = "   ";

        // when / then
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> assetService.registerGenerated(blank, AssetType.IMAGE, "image/png",
                        10L, "p", "prompt", null));
        assertTrue(ex.getMessage().contains("不能为空"));

        // then
        assertEquals(0L, assetRepository.count());
    }

    @Test
    void listFiltersByTypeSourceAndKeyword() {
        // given 上传一个图片并登记一个生成视频
        assetService.upload(imageFile("kw_pic.png", 128), "kw,alpha", 1L);
        assetService.registerGenerated("byok/kw_movie.mp4", AssetType.VIDEO, "video/mp4",
                4096L, "pv", "prompt", 2L);

        // when 按 IMAGE 类型过滤
        List<Asset> images = assetService.list(AssetType.IMAGE, null, null);
        // when 按 GENERATED 来源过滤
        List<Asset> generated = assetService.list(null, AssetSource.GENERATED, null);
        // when 按关键字过滤
        List<Asset> keyword = assetService.list(null, null, "kw");
        // when 关键字为空串视为不过滤
        List<Asset> noKeyword = assetService.list(null, null, "   ");

        // then
        assertEquals(1L, images.size());
        assertEquals(AssetType.IMAGE, images.get(0).getType());

        assertEquals(1L, generated.size());
        assertEquals(AssetSource.GENERATED, generated.get(0).getSource());

        assertTrue(keyword.size() >= 1);
        assertTrue(keyword.stream().anyMatch(a -> a.getFileName().contains("kw")));

        assertEquals(2L, noKeyword.size());
    }

    @Test
    void concurrentReuseKeepsSingleRecordConsistent() throws Exception {
        // given 一条已上传资产
        Asset uploaded = assetService.upload(imageFile("c.png", 512), null, 3L);
        Long id = uploaded.getId();

        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger failures = new AtomicInteger(0);
        AtomicReference<Long> seenEpisode = new AtomicReference<>();

        // when 两个线程同时推进同一资产的复用
        for (int i = 0; i < threads; i++) {
            final long episodeId = 100L + i;
            pool.submit(() -> {
                try {
                    start.await();
                    Asset r = assetService.reuse(id, episodeId, 200L);
                    seenEpisode.set(r.getEpisodeId());
                } catch (Exception e) {
                    failures.incrementAndGet();
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(15, TimeUnit.SECONDS), "并发任务应在超时前完成");
        pool.shutdownNow();

        // then 无异常、只有一条记录、episodeId 为两个候选之一
        assertEquals(0, failures.get(), "并发复用不应抛异常");
        assertEquals(1L, assetRepository.count());
        Asset reloaded = assetRepository.findById(id).orElseThrow();
        assertTrue(reloaded.getEpisodeId() == 100L || reloaded.getEpisodeId() == 101L);
        assertEquals(200L, reloaded.getShotId());
        assertEquals(3L, reloaded.getRunId());
    }

    @Test
    void concurrentDeleteOnSameAssetDoesNotCorruptState() throws Exception {
        // given
        Asset uploaded = assetService.upload(imageFile("d.png", 256), null, null);
        Long id = uploaded.getId();

        int threads = 2;
        ExecutorService pool = Executors.newFixedThreadPool(threads);
        CountDownLatch start = new CountDownLatch(1);
        CountDownLatch done = new CountDownLatch(threads);
        AtomicInteger success = new AtomicInteger(0);
        AtomicInteger notFound = new AtomicInteger(0);
        AtomicInteger lostRace = new AtomicInteger(0);
        AtomicReference<String> unexpected = new AtomicReference<>();

        // when 两个线程同时删除同一资产
        for (int i = 0; i < threads; i++) {
            pool.submit(() -> {
                try {
                    start.await();
                    assetService.delete(id);
                    success.incrementAndGet();
                } catch (ResourceNotFoundException e) {
                    // (a) 输家 findById 跑在赢家提交之后：看不到该行 -> ResourceNotFoundException
                    notFound.incrementAndGet();
                } catch (org.springframework.orm.ObjectOptimisticLockingFailureException e) {
                    // (b) 输家 findById 跑在赢家提交之前（看到行），但 flush/DELETE 跑在赢家提交之后，
                    //     DELETE 影响 0 行 -> Hibernate StaleStateException -> Spring 转为 ObjectOptimisticLockingFailureException
                    lostRace.incrementAndGet();
                } catch (Exception e) {
                    // 不再吞异常：把竞态语义之外的异常类名+消息记录下来，交由断言暴露
                    unexpected.compareAndSet(null, e.getClass().getName() + ": " + e.getMessage());
                } finally {
                    done.countDown();
                }
            });
        }
        start.countDown();
        assertTrue(done.await(15, TimeUnit.SECONDS), "并发删除应在超时前完成");
        pool.shutdownNow();

        // then 至少一个成功；另一线程的结局必为 (a) notFound 或 (b) lostRace 之一
        assertTrue(success.get() >= 1, "至少一个删除应成功");
        assertEquals(2, success.get() + notFound.get() + lostRace.get(), "两个线程都必须有明确的竞态结局");
        assertNull(unexpected.get(), "不应出现竞态语义之外的异常：" + unexpected.get());
        assertFalse(assetRepository.findById(id).isPresent(), "最终库中无记录");
    }

    @Test
    void uploadWithBlankTagsStoresNull() {
        // given 空白标签
        MockMultipartFile file = imageFile("blank.png", 64);

        // when
        Asset asset = assetService.upload(file, "   ", null);

        // then
        assertNotNull(asset.getId());
        assertNull(asset.getTags());
        assertNull(asset.getRunId());
        assertEquals(1L, assetRepository.count());
    }

    @Test
    void uploadExtractsExtensionFromOriginalName() {
        // given 带扩展名的文件
        MockMultipartFile file = imageFile("photo.JPEG", 100);

        // when
        Asset asset = assetService.upload(file, null, null);

        // then 存储路径保留扩展名且落在 image 子目录
        assertTrue(asset.getFilePath().startsWith("assets/image/"));
        assertTrue(asset.getFilePath().endsWith(".JPEG"));
        assertEquals("photo.JPEG", asset.getFileName());
        assertTrue(Files.exists(storageRoot.resolve(asset.getFilePath()).normalize()));
    }
}