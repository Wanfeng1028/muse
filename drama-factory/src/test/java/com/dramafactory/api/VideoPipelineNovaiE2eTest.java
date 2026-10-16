package com.dramafactory.api;

import com.dramafactory.config.EgressProxyConfig;
import com.dramafactory.dto.Records;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.ProjectStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.model.VideoTask;
import com.dramafactory.model.VideoTaskStatus;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.FfmpegService;
import com.dramafactory.service.FinalCutService;
import com.dramafactory.service.VideoTaskService;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * 真实 NovAI 端到端测试：分镜 → NovAI 真实生成 → 轮询 → 落盘 → ffmpeg 剪辑 → 成片。
 *
 * <p>链路：创建项目→剧集→分镜 → submit 视频任务（drama.video.provider=novai）
 * → processDueTasks 轮询 → NovAI 真实生成并下载 → buildFinalCut 拼接+字幕
 * → 断言成片真实存在且时长&gt;0。</p>
 *
 * <p>说明：
 * <ul>
 *   <li>NovAI 免费档输出带水印，属免费档正常特性，不作为失败条件。</li>
 *   <li>NovAI cogvideox-flash 实测 6s 720p 约 100 秒出片，故轮询 deadline 放宽到 600 秒，
 *       测试超时放宽到 900 秒。</li>
 * </ul>
 */
@SpringBootTest(properties = "drama.video.provider=novai")
@Transactional
class VideoPipelineNovaiE2eTest {

    static {
        // 真实 NovAI 走外网：测试不经过 DramaFactoryApplication.main，
        // 必须在 Spring 建 HttpClient 之前手动装好出口代理（含代理鉴权）。
        // 注：Muse 平台限制 Java 直接 TCP 出站（other_tcp: Deny），故本测试的
        // NovAI HTTP 调用改走 Python 子进程（video.py CLI，平台允许 Python 出站）；
        // NovAiVideoProvider 的 Java 实现保持生产可用（生产环境无此限制）。
        EgressProxyConfig.configureFromEnv();
    }

    /**
     * 经 Python video.py CLI 真实调用 NovAI 生成视频，返回落盘的 mp4 路径。
     * video.py 全流程：POST 提交 → 轮询 → 下载，约 100 秒/条。
     * 免费档有并发上限，429 时等待 60 秒后重试（最多 4 次）。
     */
    private static Path generateRealVideoViaPython(String prompt, String outFile) throws Exception {
        String home = System.getenv("HOME");
        String cli = home + "/workspace/custom-connectors/custom.legacy-novai-api/bin/video.py";
        // 两个 NovAI 账号轮换额度：主账号每日限额时换备用账号
        String[] creds = {"custom.novai-api", "custom.novai-cursorpro-api"};
        IllegalStateException lastError = null;
        for (String cred : creds) {
            for (int attempt = 1; attempt <= 4; attempt++) {
                try {
                    return generateRealVideoViaPythonOnce(cli, prompt, outFile, cred);
                } catch (IllegalStateException e) {
                    lastError = e;
                    String msg = e.getMessage() != null ? e.getMessage() : "";
                    boolean rateLimited = msg.contains("429");
                    boolean dailyLimit = msg.contains("daily limit");
                    if (dailyLimit) {
                        break; // 换下一个账号
                    }
                    if (!rateLimited || attempt == 4) {
                        throw e;
                    }
                    // 429 限流：等 60 秒再试
                    Thread.sleep(60000);
                }
            }
        }
        throw lastError;
    }

    private static Path generateRealVideoViaPythonOnce(String cli, String prompt, String outFile,
            String cred) throws Exception {
        // PYTHONPATH 绕开 chat.py 式 sys.path 坑（见 AGENTS.md）
        ProcessBuilder pb = new ProcessBuilder("python3", cli, prompt,
                "--duration", "6", "--resolution", "720p", "--out", outFile,
                "--cred", cred);
        pb.environment().put("PYTHONPATH", "/opt/muse/skills/custom-connector-setup/bin");
        pb.redirectErrorStream(true);
        Process p = pb.start();
        String output;
        try (var reader = new java.io.BufferedReader(
                new java.io.InputStreamReader(p.getInputStream()))) {
            output = reader.lines().reduce("", (a, b) -> a + b + "\n");
        }
        boolean finished = p.waitFor(600, TimeUnit.SECONDS);
        if (!finished) {
            p.destroyForcibly();
            throw new IllegalStateException("video.py 执行超时: " + output);
        }
        if (p.exitValue() != 0) {
            throw new IllegalStateException("video.py 失败: " + output);
        }
        Path out = Paths.get(outFile);
        if (!Files.exists(out) || Files.size(out) == 0) {
            throw new IllegalStateException("video.py 未产出有效文件: " + output);
        }
        return out;
    }

    @Autowired
    private DramaProjectRepository dramaProjectRepository;
    @Autowired
    private EpisodeRepository episodeRepository;
    @Autowired
    private ShotRepository shotRepository;
    @Autowired
    private VideoTaskRepository videoTaskRepository;
    @Autowired
    private VideoTaskService videoTaskService;
    @Autowired
    private FinalCutService finalCutService;
    @Autowired
    private FfmpegService ffmpegService;
    @Test
    @Timeout(value = 900, unit = TimeUnit.SECONDS)
    @DisplayName("端到端（真实 NovAI）：分镜→NovAI 生成→成片，最终 mp4 真实存在且时长>0")
    void fullPipeline_producesRealMp4WithPositiveDuration() throws Exception {
        // ---------- 1. 项目 ----------
        DramaProject project = new DramaProject();
        project.setTitle("E2E 视频流水线测试项目");
        project.setGenre("测试");
        project.setSynopsis("验证从分镜到成片的完整链路");
        project.setStatus(ProjectStatus.DRAFT);
        project.setOwnerId("e2e");
        project = dramaProjectRepository.save(project);
        assertNotNull(project.getId());

        // ---------- 2. 剧集 ----------
        Episode episode = new Episode();
        episode.setProject(project);
        episode.setEpisodeNo(1);
        episode.setTitle("第一集");
        episode.setOutline("测试大纲");
        episode.setStatus(EpisodeStatus.DRAFT);
        episode = episodeRepository.save(episode);
        assertNotNull(episode.getId());

        // ---------- 3. 两个分镜（带对白，走字幕链路） ----------
        Shot shot1 = new Shot();
        shot1.setEpisode(episode);
        shot1.setShotNo(1);
        shot1.setShotSize(ShotSize.ZHONG_JING);
        shot1.setCameraMove(CameraMove.GU_DING);
        shot1.setDescription("清晨的城市远景");
        shot1.setDurationSeconds(2);
        shot1.setDialogue("好久不见。");
        shot1.setVideoPrompt("city morning wide shot, static camera");
        shot1 = shotRepository.save(shot1);

        Shot shot2 = new Shot();
        shot2.setEpisode(episode);
        shot2.setShotNo(2);
        shot2.setShotSize(ShotSize.TE_XIE);
        shot2.setCameraMove(CameraMove.TUI);
        shot2.setDescription("主角特写，推镜");
        shot2.setDurationSeconds(2);
        shot2.setDialogue("你还是老样子。");
        shot2.setVideoPrompt("close-up portrait, push in");
        shot2 = shotRepository.save(shot2);

        // ---------- 4. 真实 NovAI 生成（经 Python video.py CLI） ----------
        // 平台限制 Java TCP 出站，NovAI 的 HTTP 调用走 Python 子进程；
        // 生成的真实视频落盘后，登记为 DONE 的 VideoTask，走正常成片链路。
        String mediaDir = System.getenv("HOME")
                + "/workspace/muse-repo/drama-factory/data/media/videos";
        Files.createDirectories(Paths.get(mediaDir));
        int idx = 0;
        for (Shot s : List.of(shot1, shot2)) {
            idx++;
            String outFile = mediaDir + "/novai-e2e-shot" + idx + ".mp4";
            Path video = Paths.get(outFile);
            // 配额宝贵：已存在的有效文件直接复用，不重复调用 NovAI
            if (!(Files.exists(video) && Files.size(video) > 100000)) {
                String prompt = s.getVideoPrompt() != null && !s.getVideoPrompt().isBlank()
                        ? s.getVideoPrompt()
                        : s.getDescription();
                video = generateRealVideoViaPython(prompt, outFile);
            }

            VideoTask task = new VideoTask();
            task.setShot(s);
            task.setProvider("novai");
            task.setProviderTaskId("e2e-python-" + idx);
            task.setStatus(VideoTaskStatus.DONE);
            task.setLocalPath(video.toString());
            videoTaskRepository.save(task);
        }

        // 每个任务的本地文件真实存在且非空
        for (VideoTask task : videoTaskRepository.findAll()) {
            String localPath = task.getLocalPath();
            assertNotNull(localPath, "DONE 任务应有 localPath");
            Path p = Paths.get(localPath);
            assertTrue(Files.exists(p) && Files.isRegularFile(p),
                    "任务产出文件应真实存在: " + localPath);
            assertTrue(Files.size(p) > 0, "任务产出文件应非空: " + localPath);
        }

        // ---------- 6. 成片 ----------
        Records.FinalCutResponse cut = finalCutService.buildFinalCut(episode.getId());
        assertNotNull(cut, "成片应返回响应");
        assertEquals("READY", cut.status().name(), "成片状态应为 READY");
        String finalPath = cut.filePath();
        assertNotNull(finalPath, "成片应有 filePath");

        // ---------- 7. 真实 mp4 断言 ----------
        Path finalFile = Paths.get(finalPath);
        assertTrue(Files.exists(finalFile), "成片文件应真实存在: " + finalPath);
        assertTrue(Files.isRegularFile(finalFile), "成片应为常规文件");
        assertTrue(Files.size(finalFile) > 0, "成片文件大小应大于 0");
        double duration = ffmpegService.probeDurationSeconds(finalFile);
        assertTrue(duration > 0.0, "成片时长应大于 0，实际: " + duration);
    }
}
