package com.dramafactory;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.DramaProjectRepository;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.dramafactory.service.CredentialResolver;
import com.dramafactory.service.SkillService;
import com.dramafactory.service.ScriptSplitterService;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import java.net.http.HttpResponse;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "spring.datasource.url=jdbc:h2:mem:scriptsplitterdeep;DB_CLOSE_DELAY=-1;DB_CLOSE_ON_EXIT=FALSE",
        "spring.datasource.driver-class-name=org.h2.Driver",
        "spring.datasource.username=sa",
        "spring.datasource.password=",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.jpa.properties.hibernate.dialect=org.hibernate.dialect.H2Dialect"
})
class ScriptSplitterServiceDeepTest {

    @Autowired
    private EpisodeRepository episodeRepository;

    @Autowired
    private DramaProjectRepository projectRepository;

    @Autowired
    private ShotRepository shotRepository;

    @Autowired
    private VideoTaskRepository videoTaskRepository;

    @Autowired
    private ObjectMapper objectMapper;

    private static final String VALID_JSON = "["
            + "{\"shotNo\":1,\"shotSize\":\"特写\",\"cameraMove\":\"推镜头\","
            + "\"description\":\"女主推开大门\",\"durationSeconds\":4,"
            + "\"dialogue\":\"我回来了\",\"videoPrompt\":\"cinematic close-up 16:9\"},"
            + "{\"shotNo\":2,\"shotSize\":\"全景\",\"cameraMove\":\"固定机位\","
            + "\"description\":\"客厅全貌\",\"durationSeconds\":6,"
            + "\"dialogue\":\"\",\"videoPrompt\":\"cinematic wide 16:9\"}"
            + "]";

    private static HttpResponse<String> fakeResponse(int status, String body) {
        return new HttpResponse<>() {
            @Override
            public int statusCode() {
                return status;
            }

            @Override
            public java.net.http.HttpRequest request() {
                return null;
            }

            @Override
            public java.util.Optional<HttpResponse<String>> previousResponse() {
                return java.util.Optional.empty();
            }

            @Override
            public java.net.http.HttpHeaders headers() {
                return java.net.http.HttpHeaders.of(java.util.Map.of(), (a, b) -> true);
            }

            @Override
            public String body() {
                return body;
            }

            @Override
            public java.net.URI uri() {
                return java.net.URI.create("https://chatapi.weixin.qq.com/openai/v1/chat/completions");
            }

            @Override
            public java.net.http.HttpClient.Version version() {
                return java.net.http.HttpClient.Version.HTTP_1_1;
            }

            @Override
            public java.util.Optional<javax.net.ssl.SSLSession> sslSession() {
                return java.util.Optional.empty();
            }
        };
    }

    private static HttpResponse<String> envelope(int httpStatus, String modelContent) {
        String payload = "{\"choices\":[{\"message\":{\"role\":\"assistant\",\"content\":"
                + quote(modelContent) + "}}]}";
        return fakeResponse(httpStatus, payload);
    }

    private static String quote(String raw) {
        StringBuilder sb = new StringBuilder("\"");
        for (int i = 0; i < raw.length(); i++) {
            char c = raw.charAt(i);
            switch (c) {
                case '"':
                    sb.append("\\\"");
                    break;
                case '\\':
                    sb.append("\\\\");
                    break;
                case '\n':
                    sb.append("\\n");
                    break;
                case '\r':
                    sb.append("\\r");
                    break;
                case '\t':
                    sb.append("\\t");
                    break;
                default:
                    sb.append(c);
            }
        }
        sb.append("\"");
        return sb.toString();
    }

    @BeforeEach
    void setUp() {
        shotRepository.deleteAll();
        videoTaskRepository.deleteAll();
        episodeRepository.deleteAll();
    }

    /**
     * 通过反射构造使用包可见构造器，注入 HttpExchange stub。
     * 由于 HttpExchange 是包可见接口，测试位于 com.dramafactory 包，
     * 使用反射访问其构造器以避免跨包可见性问题。
     */
    private ScriptSplitterService buildService(
            java.util.function.Function<java.net.http.HttpRequest, java.net.http.HttpResponse<String>> handler) {
        try {
            Class<?> exchangeType = Class.forName(
                    "com.dramafactory.service.ScriptSplitterService$HttpExchange");
            Object exchange = java.lang.reflect.Proxy.newProxyInstance(
                    getClass().getClassLoader(),
                    new Class<?>[] { exchangeType },
                    (proxy, method, args) -> handler.apply((java.net.http.HttpRequest) args[0]));
            java.lang.reflect.Constructor<?> ctor = ScriptSplitterService.class.getDeclaredConstructor(
                    EpisodeRepository.class,
                    ShotRepository.class,
                    VideoTaskRepository.class,
                    Class.forName("com.dramafactory.service.CredentialResolver"),
                    Class.forName("com.dramafactory.service.SkillService"),
                    ObjectMapper.class,
                    String.class,
                    int.class,
                    exchangeType);
            ctor.setAccessible(true);
            return (ScriptSplitterService) ctor.newInstance(
                    episodeRepository,
                    shotRepository,
                    videoTaskRepository,
                    mock(CredentialResolver.class),
                    mock(SkillService.class),
                    objectMapper,
                    "Deepseek-v4-flash",
                    3000,
                    exchange);
        } catch (ReflectiveOperationException e) {
            throw new IllegalStateException("构造 ScriptSplitterService 失败", e);
        }
    }

    private Episode persistEpisode(String title) {
        DramaProject p = new DramaProject();
        p.setTitle("测试项目");
        DramaProject savedProject = projectRepository.save(p);

        Episode episode = new Episode();
        episode.setTitle(title);
        episode.setStatus(EpisodeStatus.DRAFT);
        episode.setProject(savedProject);
        episode.setEpisodeNo(1);
        return episodeRepository.save(episode);
    }

    private ScriptSplitterService successService() {
        return buildService((java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                request -> envelope(200, VALID_JSON));
    }

    @Test
    void splitFromScriptSuccessPersistsShotsAndUpdatesStatus() {
        Episode episode = persistEpisode("晚风的第一集");
        ScriptSplitterService svc = successService();

        List<Records.ShotResponse> responses = svc.splitFromScript(episode.getId(), "女主回到老宅。");

        assertEquals(2, responses.size(), "返回分镜数量应为 2");
        List<Shot> stored = shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId());
        assertEquals(2, stored.size(), "库中分镜数量应为 2");
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus(), "剧集状态应更新为 SCRIPTED");
        assertEquals(ShotSize.TE_XIE, stored.get(0).getShotSize(), "第一条分镜景别应为特写");
        assertEquals(CameraMove.TUI, stored.get(0).getCameraMove(), "第一条分镜运镜应为推镜头");
    }

    @Test
    void splitFromScriptReplacesOldShotsOnRepeatCall() {
        Episode episode = persistEpisode("重复拆分");
        ScriptSplitterService svc = successService();
        svc.splitFromScript(episode.getId(), "第一版剧本。");
        int firstBatch = shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size();

        List<Records.ShotResponse> second = svc.splitFromScript(episode.getId(), "第二版剧本。");

        assertEquals(2, firstBatch, "首轮应落 2 条分镜");
        assertEquals(2, second.size(), "次轮返回仍为 2 条");
        assertEquals(2, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "旧分镜应被替换，库中仍为 2 条");
    }

    @Test
    void splitFromScriptSameInputTwiceProducesSameContent() {
        Episode episode = persistEpisode("幂等拆分");
        ScriptSplitterService svc = successService();

        List<Records.ShotResponse> first = svc.splitFromScript(episode.getId(), "同一份剧本。");
        List<Records.ShotResponse> second = svc.splitFromScript(episode.getId(), "同一份剧本。");

        assertEquals(first.size(), second.size(), "两次调用返回条数应一致");
        assertEquals(first.get(0).shotNo(), second.get(0).shotNo(), "第一条分镜编号应一致");
        assertEquals(first.get(0).shotSize(), second.get(0).shotSize(), "第一条景别应一致");
        assertEquals(first.get(1).cameraMove(), second.get(1).cameraMove(), "第二条运镜应一致");
        assertEquals(2, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "重复调用后库中分镜数仍应为 2");
    }

    @Test
    void splitFromScriptRejectsBlankScriptText() {
        Episode episode = persistEpisode("空剧本");
        ScriptSplitterService svc = successService();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.splitFromScript(episode.getId(), "   "));
        assertEquals("剧本原文不能为空", ex.getMessage(), "错误信息应明确");
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "校验失败不应落库任何分镜");
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.DRAFT, reloaded.getStatus(), "校验失败不应改动剧集状态");
    }

    @Test
    void splitFromScriptRejectsNullScriptText() {
        Episode episode = persistEpisode("null 剧本");
        ScriptSplitterService svc = successService();

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> svc.splitFromScript(episode.getId(), (String) null));
        assertEquals("剧本原文不能为空", ex.getMessage(), "错误信息应明确");
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "null 剧本不应落库");
    }

    @Test
    void splitFromScriptThrowsWhenEpisodeMissing() {
        ScriptSplitterService svc = successService();
        Long missingId = 999999L;

        assertThrows(ResourceNotFoundException.class,
                () -> svc.splitFromScript(missingId, "任意剧本。"));
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(missingId).size(),
                "剧集不存在时不应写入分镜");
        assertEquals(0, episodeRepository.count(), "不应凭空创建剧集");
    }

    @Test
    void splitFromScriptRollsBackWhenModelCallFails() {
        Episode episode = persistEpisode("失败注入");
        successService().splitFromScript(episode.getId(), "旧剧本。");
        int oldCount = shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size();

        ScriptSplitterService failing = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> {
                            throw new RuntimeException(new java.io.IOException("网络断了"));
                        });

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> failing.splitFromScript(episode.getId(), "新剧本。"));
        assertNotNull(ex, "应抛出异常");
        assertEquals(oldCount, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "模型调用失败时旧分镜不应被删除");
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus(), "失败不应回退剧集状态");
    }

    @Test
    void splitFromScriptRollsBackWhenShotSizeInvalid() {
        Episode episode = persistEpisode("非法景别");
        String badJson = "[{\"shotNo\":1,\"shotSize\":\"超近景\",\"cameraMove\":\"推镜头\","
                + "\"description\":\"x\",\"durationSeconds\":4,\"dialogue\":\"\",\"videoPrompt\":\"y\"}]";
        ScriptSplitterService svc = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> envelope(200, badJson));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.splitFromScript(episode.getId(), "剧本。"));
        assertTrue(ex.getMessage().contains("shotSize"), "异常信息应包含 shotSize");
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "非法景别不应落库");
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.DRAFT, reloaded.getStatus(), "失败不应改动状态");
    }

    @Test
    void splitFromScriptRollsBackWhenContentNotJsonArray() {
        Episode episode = persistEpisode("非数组");
        ScriptSplitterService svc = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> envelope(200, "抱歉我不会拆。"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.splitFromScript(episode.getId(), "剧本。"));
        assertNotNull(ex.getMessage(), "异常信息不应为空");
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "非 JSON 不应落库");
    }

    @Test
    void splitFromScriptRollsBackWhenArrayEmpty() {
        Episode episode = persistEpisode("空数组");
        ScriptSplitterService svc = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> envelope(200, "[]"));

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> svc.splitFromScript(episode.getId(), "剧本。"));
        assertNotNull(ex.getMessage(), "空数组应抛异常");
        assertEquals(0, shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId()).size(),
                "空数组不应落库");
    }

    @Test
    void splitFromScriptParsesWhenModelWrapsJsonInCodeFence() {
        Episode episode = persistEpisode("围栏包裹");
        String fenced = "```json\n" + VALID_JSON + "\n```";
        ScriptSplitterService svc = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> envelope(200, fenced));

        List<Records.ShotResponse> responses = svc.splitFromScript(episode.getId(), "剧本。");

        assertEquals(2, responses.size(), "围栏包裹时应正常解析出 2 条");
        Episode reloaded = episodeRepository.findById(episode.getId()).orElseThrow();
        assertEquals(EpisodeStatus.SCRIPTED, reloaded.getStatus(), "状态应更新为 SCRIPTED");
    }

    @Test
    void splitFromScriptHandlesVeryLargePayload() {
        Episode episode = persistEpisode("超大 payload");
        StringBuilder sb = new StringBuilder("[");
        for (int i = 1; i <= 8; i++) {
            if (i > 1) {
                sb.append(",");
            }
            sb.append("{\"shotNo\":").append(i)
                    .append(",\"shotSize\":\"中景\",\"cameraMove\":\"摇镜头\",")
                    .append("\"description\":\"画面").append(i).append("\",")
                    .append("\"durationSeconds\":5,\"dialogue\":\"台词").append(i).append("\",")
                    .append("\"videoPrompt\":\"cinematic shot ").append(i).append(" 16:9\"}");
        }
        sb.append("]");
        String bigJson = sb.toString();
        ScriptSplitterService svc = buildService(
                (java.util.function.Function<java.net.http.HttpRequest, HttpResponse<String>>)
                        request -> envelope(200, bigJson));

        List<Records.ShotResponse> responses = svc.splitFromScript(episode.getId(), "剧本。");

        assertEquals(8, responses.size(), "8 条分镜应全部返回");
        List<Shot> stored = shotRepository.findByEpisodeIdOrderByShotNoAsc(episode.getId());
        assertEquals(8, stored.size(), "库中应有 8 条分镜");
        assertEquals(1, stored.get(0).getShotNo(), "首条分镜编号应为 1");
        assertEquals(8, stored.get(7).getShotNo(), "末条分镜编号应为 8");
        assertEquals(ShotSize.ZHONG_JING, stored.get(0).getShotSize(), "景别应为中景");
        assertEquals(CameraMove.YAO, stored.get(0).getCameraMove(), "运镜应为摇镜头");
    }
}