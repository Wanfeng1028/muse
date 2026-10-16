package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

@Component("doubaoEmailVideoProvider")
public class DoubaoEmailVideoProvider implements VideoProvider {

    private static final Logger log = LoggerFactory.getLogger(DoubaoEmailVideoProvider.class);

    private static final String TASK_PREFIX = "doubao:";
    private static final long REPLY_TIMEOUT_MS = 6L * 60L * 60L * 1000L; // 6 小时
    private static final long SCRIPT_TIMEOUT_SECONDS = 120L;

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Value("${drama.video.doubao.script-path:scripts/doubao_email.py}")
    private String scriptPath;

    @Autowired
    public DoubaoEmailVideoProvider() {
    }

    @Override
    public String name() {
        return "doubao";
    }

    @Override
    public String submit(Shot shot, int seconds) {
        String prompt = shot.getVideoPrompt();
        if (prompt == null || prompt.isBlank()) {
            StringBuilder sb = new StringBuilder();
            if (shot.getDescription() != null) {
                sb.append(shot.getDescription());
            }
            if (shot.getShotSize() != null) {
                sb.append("，").append(shot.getShotSize());
            }
            if (shot.getCameraMove() != null) {
                sb.append("，").append(shot.getCameraMove());
            }
            prompt = sb.toString();
        }

        String shotId = String.valueOf(shot.getId());

        List<String> cmd = new ArrayList<>();
        cmd.add("python3");
        cmd.add(resolveScriptPath());
        cmd.add("send");
        cmd.add("--shot-id");
        cmd.add(shotId);
        cmd.add("--prompt");
        cmd.add(prompt);
        cmd.add("--seconds");
        cmd.add(String.valueOf(seconds));

        String stdout = runScript(cmd);

        JsonNode root;
        try {
            root = objectMapper.readTree(stdout);
        } catch (Exception e) {
            throw new RuntimeException("豆包邮件派发失败: 响应解析失败");
        }

        boolean ok = root.hasNonNull("ok") && root.get("ok").asBoolean(false);
        if (!ok) {
            String error = root.hasNonNull("error") ? root.get("error").asText() : "未知错误";
            throw new RuntimeException("豆包邮件派发失败: " + error);
        }

        JsonNode threadIdNode = root.get("thread_id");
        if (threadIdNode == null || threadIdNode.isNull() || threadIdNode.asText().isBlank()) {
            throw new RuntimeException("豆包邮件派发失败: 响应缺少 thread_id");
        }

        String threadId = threadIdNode.asText();
        return TASK_PREFIX + threadId + ":" + System.currentTimeMillis();
    }

    @Override
    public ProbeResult poll(String providerTaskId) {
        if (providerTaskId == null || !providerTaskId.startsWith(TASK_PREFIX)) {
            return new ProbeResult(RemoteStatus.FAILED, null, "任务ID格式错误", 0);
        }
        String rest = providerTaskId.substring(TASK_PREFIX.length());
        int sep = rest.lastIndexOf(':');
        if (sep <= 0 || sep == rest.length() - 1) {
            return new ProbeResult(RemoteStatus.FAILED, null, "任务ID格式错误", 0);
        }
        String threadId = rest.substring(0, sep);
        String tsStr = rest.substring(sep + 1);
        long dispatchedAt;
        try {
            dispatchedAt = Long.parseLong(tsStr);
        } catch (NumberFormatException e) {
            return new ProbeResult(RemoteStatus.FAILED, null, "任务ID格式错误", 0);
        }

        if (System.currentTimeMillis() - dispatchedAt > REPLY_TIMEOUT_MS) {
            return new ProbeResult(RemoteStatus.FAILED, null, "豆包6小时未回复，转降级", 0);
        }

        List<String> cmd = new ArrayList<>();
        cmd.add("python3");
        cmd.add(resolveScriptPath());
        cmd.add("poll");
        cmd.add("--thread-id");
        cmd.add(threadId);

        try {
            String stdout = runScript(cmd);
            JsonNode root = objectMapper.readTree(stdout);
            boolean ok = root.path("ok").asBoolean(false);
            if (!ok) {
                String err = root.path("error").asText("未知错误");
                throw new RuntimeException("豆包邮件轮询失败: " + err);
            }
            String status = root.path("status").asText("");
            if ("waiting".equals(status)) {
                return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
            }
            if ("done".equals(status)) {
                String videoUrl = root.path("video_url").asText("");
                if (videoUrl == null || videoUrl.isEmpty()) {
                    return new ProbeResult(RemoteStatus.FAILED, null, "豆包任务失败", 0);
                }
                return new ProbeResult(RemoteStatus.COMPLETED, videoUrl, null, 100);
            }
            if ("failed".equals(status)) {
                return new ProbeResult(RemoteStatus.FAILED, null, "豆包任务失败", 0);
            }
            return new ProbeResult(RemoteStatus.PROCESSING, null, null, 0);
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("豆包邮件轮询失败: " + e.getMessage());
        }
    }

    private String runScript(List<String> cmd) {
        try {
            ProcessBuilder pb = new ProcessBuilder(cmd);
            pb.redirectErrorStream(false);
            Process process = pb.start();

            StringBuilder stdout = new StringBuilder();
            StringBuilder stderr = new StringBuilder();

            Thread errThread = new Thread(() -> {
                try (BufferedReader reader = new BufferedReader(
                        new InputStreamReader(process.getErrorStream(), StandardCharsets.UTF_8))) {
                    String line;
                    while ((line = reader.readLine()) != null) {
                        if (stderr.length() < 2000) {
                            stderr.append(line).append('\n');
                        }
                    }
                } catch (IOException ignored) {
                }
            });
            errThread.setDaemon(true);
            errThread.start();

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(process.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = reader.readLine()) != null) {
                    stdout.append(line).append('\n');
                }
            }

            boolean finished = process.waitFor(SCRIPT_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!finished) {
                process.destroyForcibly();
                throw new RuntimeException("脚本执行超时");
            }

            errThread.join(1000);

            int exitCode = process.exitValue();
            if (exitCode != 0) {
                String errSnippet = stderr.toString().trim();
                if (errSnippet.length() > 200) {
                    errSnippet = errSnippet.substring(0, 200);
                }
                throw new RuntimeException("脚本执行失败, exit=" + exitCode + ", stderr=" + errSnippet);
            }

            return stdout.toString().trim();
        } catch (RuntimeException e) {
            throw e;
        } catch (Exception e) {
            throw new RuntimeException("脚本执行异常: " + e.getMessage());
        }
    }

    private String resolveScriptPath() {
        Path path = Paths.get(scriptPath);
        if (!path.isAbsolute()) {
            path = Paths.get(System.getProperty("user.dir")).resolve(scriptPath);
        }
        return path.toAbsolutePath().normalize().toString();
    }

    @Override
    public ConnectivityResult probeConnectivity() {
        try {
            Path path = Paths.get(resolveScriptPath());
            if (Files.exists(path) && Files.isRegularFile(path)) {
                return new ConnectivityResult(ConnectivityStatus.OK, "邮件助手脚本就绪");
            }
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, "脚本缺失");
        } catch (Exception e) {
            return new ConnectivityResult(ConnectivityStatus.UNREACHABLE, "脚本缺失");
        }
    }
}
