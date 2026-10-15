package com.dramafactory.service;

import com.dramafactory.dto.Records;
import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.CameraMove;
import com.dramafactory.model.Episode;
import com.dramafactory.model.EpisodeStatus;
import com.dramafactory.model.Shot;
import com.dramafactory.model.ShotSize;
import com.dramafactory.repository.EpisodeRepository;
import com.dramafactory.repository.ShotRepository;
import com.dramafactory.repository.VideoTaskRepository;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import java.lang.reflect.Method;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

/**
 * 补覆盖测试：对照 jacoco missed-branch 清单逐行命中缺失臂。
 *
 * 诚实跳过清单：
 * - 无。清单上每一行均在下方 @Test 中命中其缺失臂。
 */
@ExtendWith(MockitoExtension.class)
class ScriptSplitterServiceV223CTest {

    private static final String VALID_SHOT_JSON =
            "[{\"shotNo\":1,\"shotSize\":\"中景\",\"cameraMove\":\"固定机位\",\"description\":\"雨夜街头\",\"durationSeconds\":5,\"dialogue\":\"\",\"videoPrompt\":\"cinematic street night 16:9\"}]";

    @Mock
    EpisodeRepository episodeRepository;
    @Mock
    ShotRepository shotRepository;
    @Mock
    VideoTaskRepository videoTaskRepository;
    @Mock
    CredentialResolver credentialResolver;
    @Mock
    SkillService skillService;

    private final ObjectMapper objectMapper = new ObjectMapper();

    /** 队列式 fake：send 时 poll 队首响应。 */
    static final class CapturingExchange implements ScriptSplitterService.HttpExchange {
        private final Deque<HttpResponse<String>> queue = new ArrayDeque<>();
        private volatile HttpRequest lastRequest;

        void enqueueResponse(HttpResponse<String> response) {
            queue.add(response);
        }

        HttpRequest lastRequest() {
            return lastRequest;
        }

        @Override
        public HttpResponse<String> send(HttpRequest request) {
            this.lastRequest = request;
            return queue.poll();
        }
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse<String> okResponse(String content) {
        String escaped = content.replace("\\", "\\\\").replace("\"", "\\\"");
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(200);
        when(response.body()).thenReturn("{\"choices\":[{\"message\":{\"content\":\"" + escaped + "\"}}]}");
        return response;
    }

    @SuppressWarnings("unchecked")
    private static HttpResponse<String> rawResponse(int status, String body) {
        HttpResponse<String> response = mock(HttpResponse.class);
        when(response.statusCode()).thenReturn(status);
        when(response.body()).thenReturn(body);
        return response;
    }

    /** 从 HttpRequest 的 bodyPublisher 同步读出请求体字符串（照抄 ScriptSplitterCallModelTest.bodyOf）。 */
    private static String bodyOf(HttpRequest request) {
        final StringBuilder sb = new StringBuilder();
        request.bodyPublisher().ifPresent(publisher -> publisher.subscribe(new java.util.concurrent.Flow.Subscriber<>() {
            public void onSubscribe(java.util.concurrent.Flow.Subscription s) { s.request(Long.MAX_VALUE); }
            public void onNext(java.nio.ByteBuffer b) { byte[] bts = new byte[b.remaining()]; b.get(bts); sb.append(new String(bts, java.nio.charset.StandardCharsets.UTF_8)); }
            public void onError(Throwable t) { }
            public void onComplete() { }
        }));
        return sb.toString();
    }

    private ScriptSplitterService newService(CapturingExchange exchange) {
        return new ScriptSplitterService(
                episodeRepository, shotRepository, videoTaskRepository,
                credentialResolver, skillService, objectMapper,
                "Deepseek-v4-flash", 3000, exchange);
    }

    private Episode episodeWithTitle(String title) {
        Episode episode = new Episode();
        episode.setId(1L);
        if (title != null) {
            episode.setTitle(title);
        }
        return episode;
    }

    private void stubHappyRepos(Episode episode) {
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of());
        when(shotRepository.save(any(Shot.class))).thenAnswer(inv -> inv.getArgument(0));
    }

    // L132 mb=1 cb=1：skillId 非 null 臂
    @Test
    void splitFromScript_withNonNullSkillId_callsResolveForUse() {
        Episode episode = episodeWithTitle("测试剧");
        stubHappyRepos(episode);
        when(skillService.resolveForUse(eq(7L), any()))
                .thenReturn(new SkillService.ResolvedSkill(7L, "悬疑钩子", "1.0", "增强prompt"));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        List<Records.ShotResponse> responses = service.splitFromScript(1L, "剧本", 7L);

        assertNotNull(responses);
        assertEquals(1, responses.size());
        verify(skillService).resolveForUse(eq(7L), any());
    }

    // L137 mb=2 cb=0：title 非 null 臂
    @Test
    void splitFromScript_withSkillId_titleNonNull_putsTitleIntoVars() {
        Episode episode = episodeWithTitle("测试剧");
        stubHappyRepos(episode);
        when(skillService.resolveForUse(eq(7L), any()))
                .thenReturn(new SkillService.ResolvedSkill(7L, "悬疑钩子", "1.0", "增强prompt"));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        service.splitFromScript(1L, "剧本", 7L);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(skillService).resolveForUse(eq(7L), captor.capture());
        assertEquals("测试剧", captor.getValue().get("剧集标题"));
    }

    // L137 mb=2 cb=0：title 为 null 臂
    @Test
    void splitFromScript_withSkillId_titleNull_putsEmptyStringIntoVars() {
        Episode episode = episodeWithTitle(null);
        stubHappyRepos(episode);
        when(skillService.resolveForUse(eq(7L), any()))
                .thenReturn(new SkillService.ResolvedSkill(7L, "悬疑钩子", "1.0", "增强prompt"));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        service.splitFromScript(1L, "剧本", 7L);

        @SuppressWarnings("unchecked")
        ArgumentCaptor<Map<String, String>> captor = ArgumentCaptor.forClass(Map.class);
        verify(skillService).resolveForUse(eq(7L), captor.capture());
        assertEquals("", captor.getValue().get("剧集标题"));
    }

    // L156 mb=1 cb=3：scriptText == null 臂
    @Test
    void splitFromScript_scriptTextNull_throwsIllegalArgument() {
        Episode episode = episodeWithTitle("测试剧");
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));

        CapturingExchange exchange = new CapturingExchange();
        ScriptSplitterService service = newService(exchange);

        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> service.splitFromScript(1L, null, (String) null));
        assertEquals("剧本原文不能为空", ex.getMessage());
    }

    // L168 mb=1 cb=1：oldShots 非空臂
    @Test
    void splitFromScript_oldShotsNonEmpty_deletesOldShotsAndTasks() {
        Episode episode = episodeWithTitle("测试剧");
        Shot oldShot = new Shot();
        oldShot.setId(9L);

        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));
        when(shotRepository.findByEpisodeIdOrderByShotNoAsc(1L)).thenReturn(List.of(oldShot));
        when(videoTaskRepository.findByShotIdOrderByIdDesc(9L)).thenReturn(List.of());
        when(shotRepository.save(any(Shot.class))).thenAnswer(inv -> inv.getArgument(0));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        List<Records.ShotResponse> responses = service.splitFromScript(1L, "剧本", (String) null);

        assertNotNull(responses);
        assertEquals(1, responses.size());
        verify(shotRepository).delete(oldShot);
        verify(videoTaskRepository).findByShotIdOrderByIdDesc(9L);
    }

    // L289 mb=3 cb=1：skillPrompt 非 null 且 blank（空串）臂
    @Test
    void splitFromScript_emptySkillPrompt_doesNotInjectSkillBlock() {
        Episode episode = episodeWithTitle("测试剧");
        stubHappyRepos(episode);

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        List<Records.ShotResponse> responses = service.splitFromScript(1L, "剧本", "");

        assertNotNull(responses);
        assertEquals(1, responses.size());
        String body = bodyOf(exchange.lastRequest());
        assertTrue(!body.contains("Skill 增强"));
    }

    // L289 mb=3 cb=1：skillPrompt 非 null 且非 blank 臂
    @Test
    void splitFromScript_nonBlankSkillPrompt_injectsSkillBlock() {
        Episode episode = episodeWithTitle("测试剧");
        stubHappyRepos(episode);

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        List<Records.ShotResponse> responses = service.splitFromScript(1L, "剧本", "注入的skill");

        assertNotNull(responses);
        assertEquals(1, responses.size());
        String body = bodyOf(exchange.lastRequest());
        assertTrue(body.contains("Skill 增强"));
        assertTrue(body.contains("注入的skill"));
    }

    // L327 mb=1 cb=3：status < 200 臂
    @Test
    void splitFromScript_status199_throwsCallModelFailure() {
        Episode episode = episodeWithTitle("测试剧");
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(rawResponse(199, "early"));
        ScriptSplitterService service = newService(exchange);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.splitFromScript(1L, "剧本", (String) null));
        assertTrue(ex.getMessage().contains("调用大模型失败"));
    }

    // L347 mb=1 cb=3：contentNode.isNull() == true 臂
    @Test
    void splitFromScript_contentNullNode_throwsEmptyContent() {
        Episode episode = episodeWithTitle("测试剧");
        when(episodeRepository.findById(1L)).thenReturn(Optional.of(episode));

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(rawResponse(200, "{\"choices\":[{\"message\":{\"content\":null}}]}"));
        ScriptSplitterService service = newService(exchange);

        RuntimeException ex = assertThrows(RuntimeException.class,
                () -> service.splitFromScript(1L, "剧本", (String) null));
        assertEquals("大模型返回内容为空", ex.getMessage());
    }

    // L472 + L475 + L477：episode/shotSize/cameraMove 全为 null 臂
    @Test
    void toResponse_nullEpisodeAndNullEnums_yieldsNullComponents() throws Exception {
        ScriptSplitterService service = newService(new CapturingExchange());

        Shot shot = new Shot();
        shot.setId(1L);

        Method m = ScriptSplitterService.class.getDeclaredMethod("toResponse", Shot.class);
        m.setAccessible(true);
        Records.ShotResponse resp = (Records.ShotResponse) m.invoke(service, shot);

        assertNotNull(resp);
        assertNull(resp.episodeId());
        assertNull(resp.shotSizeLabel());
        assertNull(resp.cameraMoveLabel());
    }

    // 附：确保 ResourceNotFoundException 场景在测试集内可用（保留 import 语义一致性）
    @Test
    void splitFromScript_episodeMissing_throwsResourceNotFound() {
        when(episodeRepository.findById(1L)).thenReturn(Optional.empty());

        ScriptSplitterService service = newService(new CapturingExchange());

        assertThrows(ResourceNotFoundException.class,
                () -> service.splitFromScript(1L, "剧本", (String) null));
    }

    // 附：确认 setStatus 落在 EpisodeStatus.SCRIPTED（无副作用防御）
    @Test
    void splitFromScript_setsEpisodeStatusScripted() {
        Episode episode = episodeWithTitle("测试剧");
        stubHappyRepos(episode);

        CapturingExchange exchange = new CapturingExchange();
        exchange.enqueueResponse(okResponse(VALID_SHOT_JSON));
        ScriptSplitterService service = newService(exchange);

        service.splitFromScript(1L, "剧本", (String) null);

        assertEquals(EpisodeStatus.SCRIPTED, episode.getStatus());
        verify(episodeRepository).save(episode);
    }

    // 附：确认 ShotSize / CameraMove 枚举解析链路无异常
    @Test
    void parseShotsJson_validLabels_parsesEnums() {
        Episode episode = episodeWithTitle("测试剧");
        ScriptSplitterService service = newService(new CapturingExchange());

        List<Shot> shots = service.parseShotsJson(episode, VALID_SHOT_JSON);

        assertEquals(1, shots.size());
        assertEquals(ShotSize.ZHONG_JING, shots.get(0).getShotSize());
        assertEquals(CameraMove.GU_DING, shots.get(0).getCameraMove());
    }
}
