package com.dramafactory.tools;

import com.dramafactory.model.Asset;
import com.dramafactory.model.AssetSource;
import com.dramafactory.model.AssetType;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.tools.repository.ToolOpLogRepository;
import com.dramafactory.tools.service.QuickToolsService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class QuickToolsServiceTest {

    @Autowired
    private QuickToolsService quickToolsService;

    @Autowired
    private AssetRepository assetRepository;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private ToolOpLogRepository toolOpLogRepository;

    private static final Path MEDIA_ROOT = Paths.get("./data/media");
    private static final Path TOOLS_TEST_DIR = MEDIA_ROOT.resolve("tools-test");
    private static final Path ASSETS_TOOLS_DIR = MEDIA_ROOT.resolve("assets/tools-test");

    @AfterEach
    void cleanup() throws IOException {
        deleteRecursively(TOOLS_TEST_DIR);
        deleteRecursively(ASSETS_TOOLS_DIR);
    }

    private void deleteRecursively(Path dir) throws IOException {
        if (!Files.exists(dir)) {
            return;
        }
        try (var stream = Files.walk(dir)) {
            stream.sorted((a, b) -> b.getNameCount() - a.getNameCount())
                    .forEach(p -> {
                        try {
                            Files.deleteIfExists(p);
                        } catch (IOException ignored) {
                        }
                    });
        }
    }

    private Asset createAsset(AssetType type, String fileName, String filePath, String mimeType, long size) {
        Asset asset = new Asset();
        asset.setType(type);
        asset.setSource(AssetSource.UPLOADED);
        asset.setFileName(fileName);
        asset.setFilePath(filePath);
        asset.setMimeType(mimeType);
        asset.setFileSize(size);
        return assetRepository.save(asset);
    }

    private void generateTestVideo(Path out) throws IOException, InterruptedException {
        Files.createDirectories(out.getParent());
        ProcessBuilder pb = new ProcessBuilder(
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "testsrc=duration=2:size=640x480:rate=24",
                "-f", "lavfi",
                "-i", "sine=frequency=440:duration=2",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-shortest",
                out.toAbsolutePath().toString()
        );
        pb.redirectErrorStream(true);
        Process process = pb.start();
        process.getInputStream().readAllBytes();
        int exit = process.waitFor();
        assertEquals(0, exit, "ffmpeg 生成测试视频失败");
    }

    private int ffprobeWidth(Path file) throws IOException, InterruptedException {
        ProcessBuilder pb = new ProcessBuilder(
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width",
                "-of", "csv=p=0",
                file.toAbsolutePath().toString()
        );
        pb.redirectErrorStream(true);
        Process process = pb.start();
        String output = new String(process.getInputStream().readAllBytes(), StandardCharsets.UTF_8).trim();
        int exit = process.waitFor();
        assertEquals(0, exit, "ffprobe 探测失败");
        return Integer.parseInt(output);
    }

    @Test
    void batchTag_merge() {
        Asset a1 = createAsset(AssetType.IMAGE, "a1.png", "assets/tools-test/a1.png", "image/png", 10L);
        Asset a2 = createAsset(AssetType.IMAGE, "a2.png", "assets/tools-test/a2.png", "image/png", 10L);
        a1.setTags("a,b");
        a1 = assetRepository.save(a1);

        List<Long> ids = new ArrayList<>();
        ids.add(a1.getId());
        ids.add(a2.getId());

        int count = quickToolsService.batchTagAssets(ids, "b,c", "merge");
        assertEquals(2, count);

        Asset r1 = assetRepository.findById(a1.getId()).orElseThrow();
        Asset r2 = assetRepository.findById(a2.getId()).orElseThrow();
        assertEquals("a,b,c", r1.getTags());
        assertEquals("b,c", r2.getTags());
    }

    @Test
    void batchTag_replace() {
        Asset a1 = createAsset(AssetType.IMAGE, "r1.png", "assets/tools-test/r1.png", "image/png", 10L);
        a1.setTags("a");
        a1 = assetRepository.save(a1);

        int count = quickToolsService.batchTagAssets(List.of(a1.getId()), "x", "replace");
        assertEquals(1, count);

        Asset r1 = assetRepository.findById(a1.getId()).orElseThrow();
        assertEquals("x", r1.getTags());
    }

    @Test
    void batchTag_emptyIds_throws() {
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.batchTagAssets(new ArrayList<>(), "a", "merge"));
    }

    @Test
    void batchTag_notFound_throws() {
        assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.batchTagAssets(List.of(999999L), "a", "merge"));
    }

    @Test
    void batchRename() {
        Asset a1 = createAsset(AssetType.IMAGE, "old.png", "assets/tools-test/old.png", "image/png", 10L);

        Map<Long, String> renames = new HashMap<>();
        renames.put(a1.getId(), "new.png");
        int count = quickToolsService.batchRenameAssets(renames);
        assertEquals(1, count);

        Asset r1 = assetRepository.findById(a1.getId()).orElseThrow();
        assertEquals("new.png", r1.getFileName());

        Map<Long, String> emptyNames = new HashMap<>();
        emptyNames.put(a1.getId(), "");
        assertThrows(IllegalArgumentException.class, () -> quickToolsService.batchRenameAssets(emptyNames));
    }

    @Test
    void convertVideo_webm() throws Exception {
        Path src = TOOLS_TEST_DIR.resolve("src.mp4");
        generateTestVideo(src);

        Path dest = ASSETS_TOOLS_DIR.resolve("src.mp4");
        Files.createDirectories(dest.getParent());
        Files.copy(src, dest, StandardCopyOption.REPLACE_EXISTING);

        Asset asset = createAsset(AssetType.VIDEO, "src.mp4", "assets/tools-test/src.mp4", "video/mp4", Files.size(dest));

        Asset webm = quickToolsService.convertVideo(asset.getId(), "webm", 320);
        assertNotNull(webm);
        assertEquals(AssetType.VIDEO, webm.getType());
        assertEquals("video/webm", webm.getMimeType());

        Path webmPath = MEDIA_ROOT.resolve(webm.getFilePath());
        assertTrue(Files.exists(webmPath), "webm 输出文件不存在");
        int width = ffprobeWidth(webmPath);
        assertTrue(width <= 320, "webm 宽度应 <=320, 实际 " + width);

        Asset mp4 = quickToolsService.convertVideo(asset.getId(), "mp4", null);
        assertNotNull(mp4);
        assertEquals("video/mp4", mp4.getMimeType());
    }

    @Test
    void extractAudio_mp3() throws Exception {
        Path src = TOOLS_TEST_DIR.resolve("src.mp4");
        generateTestVideo(src);

        Path dest = ASSETS_TOOLS_DIR.resolve("src.mp4");
        Files.createDirectories(dest.getParent());
        Files.copy(src, dest, StandardCopyOption.REPLACE_EXISTING);

        Asset asset = createAsset(AssetType.VIDEO, "src.mp4", "assets/tools-test/src.mp4", "video/mp4", Files.size(dest));

        Asset audio = quickToolsService.extractAudio(asset.getId(), "mp3");
        assertNotNull(audio);
        assertEquals(AssetType.AUDIO, audio.getType());
        assertEquals("audio/mpeg", audio.getMimeType());

        Path audioPath = MEDIA_ROOT.resolve(audio.getFilePath());
        assertTrue(Files.exists(audioPath), "音频输出文件不存在");
        assertTrue(Files.size(audioPath) > 0, "音频文件大小应 >0");
    }

    @Test
    void convertVideo_notVideo_throws() {
        Asset image = createAsset(AssetType.IMAGE, "img.png", "assets/tools-test/img.png", "image/png", 10L);
        assertThrows(IllegalArgumentException.class,
                () -> quickToolsService.convertVideo(image.getId(), "webm", 320));
    }

    @Test
    void exportShotCsv_content() {
        DramaProject project = new DramaProject();
        project.setTitle("测试项目");
        project.setOwnerId("test-owner");
        project = dramaProjectRepository.save(project);

        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode = episodeRepository.save(episode);

        Shot shot1 = new Shot();
        shot1.setEpisode(episode);
        shot1.setShotNo(1);
        shot1.setShotSize(ShotSize.JIN_JING);
        shot1.setCameraMove(CameraMove.GU_DING);
        shot1.setDescription("第一个镜头");
        shot1.setDialogue("你好");
        shot1.setDurationSeconds(3);
        shotRepository.save(shot1);

        Shot shot2 = new Shot();
        shot2.setEpisode(episode);
        shot2.setShotNo(2);
        shot2.setShotSize(ShotSize.YUAN_JING);
        shot2.setCameraMove(CameraMove.GU_DING);
        shot2.setDescription("第二个镜头");
        shot2.setDialogue("他说：\"你好，世界\"\n然后走了");
        shot2.setDurationSeconds(4);
        shotRepository.save(shot2);

        byte[] bytes = quickToolsService.exportShotCsv(episode.getId());
        assertNotNull(bytes);
        assertTrue(bytes.length >= 3);
        assertEquals((byte) 0xEF, bytes[0]);
        assertEquals((byte) 0xBB, bytes[1]);
        assertEquals((byte) 0xBF, bytes[2]);

        String content = new String(bytes, StandardCharsets.UTF_8);
        assertTrue(content.contains("镜号,景别,运镜,画面描述,台词,时长(秒),创建时间"),
                "缺少 CSV 头行");
        assertTrue(content.contains("\"他说：\"\"你好，世界\""),
                "缺少转义后的台词片段");

        String[] lines = content.split("\r\n");
        assertEquals(3, lines.length, "应为头行+2 行数据");
    }

    @Test
    void exportShotCsv_notFound_throws() {
        assertThrows(ResourceNotFoundException.class,
                () -> quickToolsService.exportShotCsv(999999L));
    }

    @Test
    void opLog_recorded() {
        Asset a1 = createAsset(AssetType.IMAGE, "log.png", "assets/tools-test/log.png", "image/png", 10L);

        quickToolsService.batchTagAssets(List.of(a1.getId()), "t1", "merge");

        var logs = toolOpLogRepository.findTop50ByOrderByCreatedAtDesc();
        assertNotNull(logs);
        assertTrue(!logs.isEmpty(), "操作日志不应为空");
        boolean found = logs.stream()
                .anyMatch(log -> "batch-tag".equals(log.getOperation()));
        assertTrue(found, "应包含 operation=batch-tag 的日志");
    }
}
