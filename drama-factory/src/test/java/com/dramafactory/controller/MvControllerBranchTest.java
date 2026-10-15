package com.dramafactory.controller;

import com.dramafactory.exception.ResourceNotFoundException;
import com.dramafactory.model.MvSong;
import com.dramafactory.service.MvService;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MvControllerBranchTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private MvService mvService;

    private MvSong songWith(Long id) {
        MvSong s = new MvSong();
        s.setId(id);
        return s;
    }

    // ---------- create ----------

    // L46: body==null 分支。空 body 无 Content-Type，Spring 可能直接 400。
    @Test
    void create_withEmptyBody_returnsBadRequest() throws Exception {
        // L46: body==null 分支。走 HTTP 时 Spring 要么反序列化出 Map 要么在框架层
        // 直接抛错（实测空 body/"null" 都到不了 controller），body==null 实际不可达；
        // 改为直接调用 controller 方法覆盖该防御分支。
        MvController direct = new MvController(Mockito.mock(MvService.class), "./data/media");
        var resp = direct.create(null);
        org.junit.jupiter.api.Assertions.assertEquals(400, resp.getStatusCode().value());
        org.junit.jupiter.api.Assertions.assertEquals("FAILED", resp.getBody().get("status"));
    }

    // L46/L47: body 非 null 但缺 theme key -> theme==null -> 400
    @Test
    void create_withMissingThemeKey_returnsBadRequest() throws Exception {
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"mood\":\"happy\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // L52/L53: 正常返回，验证 create 分支
    @Test
    void create_withValidTheme_returnsOk() throws Exception {
        when(mvService.create(eq("t"), isNull(), isNull())).thenReturn(42L);
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"t\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.id").value(42));
    }

    // L54/L55: service 抛 IllegalArgumentException -> 400
    @Test
    void create_whenServiceThrowsIllegalArgument_returnsBadRequest() throws Exception {
        when(mvService.create(eq("t"), any(), any()))
                .thenThrow(new IllegalArgumentException("bad theme"));
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"t\"}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"))
                .andExpect(jsonPath("$.error").value("bad theme"));
    }

    // L56/L57: service 抛 ResourceNotFoundException -> 全局处理 404
    @Test
    void create_whenServiceThrowsResourceNotFound_returnsNotFound() throws Exception {
        when(mvService.create(eq("t"), any(), any()))
                .thenThrow(new ResourceNotFoundException("mv", 1L));
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"t\"}"))
                .andExpect(status().isNotFound());
    }

    // L58/L59/L60: service 抛 RuntimeException -> 500
    @Test
    void create_whenServiceThrowsRuntimeException_returnsInternalServerError() throws Exception {
        when(mvService.create(eq("t"), any(), any()))
                .thenThrow(new RuntimeException("boom"));
        mockMvc.perform(post("/api/mv")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"theme\":\"t\"}"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value("FAILED"))
                .andExpect(jsonPath("$.error").value("boom"));
    }

    // ---------- importAudio ----------

    // L76/L77: audioUrl==null, durationMs==null -> 默认 "" 和 0
    @Test
    void importAudio_whenAudioUrlAndDurationNull_usesDefaults() throws Exception {
        MvSong s = songWith(10L);
        s.setAudioUrl(null);
        s.setDurationMs(null);
        when(mvService.importAudio(any(), eq("t"), any(), any(), any())).thenReturn(s);
        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", new byte[]{1, 2, 3});
        mockMvc.perform(multipart("/api/mv/import").file(file).param("title", "t"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.id").value(10))
                .andExpect(jsonPath("$.audioUrl").value(""))
                .andExpect(jsonPath("$.durationMs").value(0));
    }

    // L76/L77: 有值分支
    @Test
    void importAudio_whenAudioUrlAndDurationPresent_returnsValues() throws Exception {
        MvSong s = songWith(11L);
        s.setAudioUrl("/x.mp3");
        s.setDurationMs(1234);
        when(mvService.importAudio(any(), eq("t"), any(), any(), any())).thenReturn(s);
        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", new byte[]{1});
        mockMvc.perform(multipart("/api/mv/import").file(file).param("title", "t"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.audioUrl").value("/x.mp3"))
                .andExpect(jsonPath("$.durationMs").value(1234));
    }

    // L78/L79: IllegalArgumentException -> 400
    @Test
    void importAudio_whenIllegalArgument_returnsBadRequest() throws Exception {
        when(mvService.importAudio(any(), any(), any(), any(), any()))
                .thenThrow(new IllegalArgumentException("bad"));
        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", new byte[]{1});
        mockMvc.perform(multipart("/api/mv/import").file(file).param("title", "t"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // L78/L79: IllegalStateException -> 400
    @Test
    void importAudio_whenIllegalState_returnsBadRequest() throws Exception {
        when(mvService.importAudio(any(), any(), any(), any(), any()))
                .thenThrow(new IllegalStateException("state"));
        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", new byte[]{1});
        mockMvc.perform(multipart("/api/mv/import").file(file).param("title", "t"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // L82/L83/L84: RuntimeException -> 500
    @Test
    void importAudio_whenRuntimeException_returnsInternalServerError() throws Exception {
        when(mvService.importAudio(any(), any(), any(), any(), any()))
                .thenThrow(new RuntimeException("boom"));
        MockMultipartFile file = new MockMultipartFile("file", "a.mp3", "audio/mpeg", new byte[]{1});
        mockMvc.perform(multipart("/api/mv/import").file(file).param("title", "t"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // ---------- lyrics ----------

    // L94: lyricsJson==null -> ""
    @Test
    void lyrics_whenLyricsJsonNull_usesEmptyString() throws Exception {
        MvSong s = songWith(1L);
        s.setLyricsJson(null);
        when(mvService.generateLyrics(1L)).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/lyrics"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.lyricsJson").value(""));
    }

    // L95/L96: IllegalArgumentException -> 400
    @Test
    void lyrics_whenIllegalArgument_returnsBadRequest() throws Exception {
        when(mvService.generateLyrics(1L))
                .thenThrow(new IllegalArgumentException("bad"));
        mockMvc.perform(post("/api/mv/1/lyrics"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // L99/L100/L101: RuntimeException -> 500
    @Test
    void lyrics_whenRuntimeException_returnsInternalServerError() throws Exception {
        when(mvService.generateLyrics(1L))
                .thenThrow(new RuntimeException("boom"));
        mockMvc.perform(post("/api/mv/1/lyrics"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // ---------- compose ----------

    // L113/L114: providerId 为 Number -> longValue
    @Test
    void compose_withNumericProviderId_passesLongValue() throws Exception {
        MvSong s = songWith(1L);
        s.setAudioUrl("/a.mp3");
        s.setDurationMs(100);
        when(mvService.compose(1L, 5L, null)).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"providerId\":5}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"));
        verify(mvService).compose(1L, 5L, null);
    }

    // L115/L116: providerId 为 String -> parseLong
    @Test
    void compose_withStringProviderId_parsesLong() throws Exception {
        MvSong s = songWith(1L);
        s.setAudioUrl("/a.mp3");
        s.setDurationMs(100);
        when(mvService.compose(1L, 7L, null)).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"providerId\":\"7\"}"))
                .andExpect(status().isOk());
        verify(mvService).compose(1L, 7L, null);
    }

    // L115: providerId 空字符串 -> isBlank true -> 保持 null
    @Test
    void compose_withBlankStringProviderId_keepsNull() throws Exception {
        MvSong s = songWith(1L);
        s.setAudioUrl("/a.mp3");
        s.setDurationMs(100);
        when(mvService.compose(1L, null, null)).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"providerId\":\"\"}"))
                .andExpect(status().isOk());
        verify(mvService).compose(1L, null, null);
    }

    // L119/L120: mid!=null -> modelId 赋值
    @Test
    void compose_withModelId_passesModelId() throws Exception {
        MvSong s = songWith(1L);
        s.setAudioUrl("/a.mp3");
        s.setDurationMs(100);
        when(mvService.compose(1L, null, "m1")).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"modelId\":\"m1\"}"))
                .andExpect(status().isOk());
        verify(mvService).compose(1L, null, "m1");
    }

    // L128/L129: IllegalStateException -> 400
    @Test
    void compose_whenIllegalState_returnsBadRequest() throws Exception {
        when(mvService.compose(eq(1L), any(), any()))
                .thenThrow(new IllegalStateException("state"));
        mockMvc.perform(post("/api/mv/1/compose")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // ---------- storyboard ----------

    // L142: 返回空列表
    @Test
    void storyboard_returnsEmptyList() throws Exception {
        when(mvService.storyboard(1L)).thenReturn(List.of());
        mockMvc.perform(post("/api/mv/1/storyboard"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.items").isArray());
    }

    // L143/L144: IllegalArgumentException -> 400
    @Test
    void storyboard_whenIllegalArgument_returnsBadRequest() throws Exception {
        when(mvService.storyboard(1L))
                .thenThrow(new IllegalArgumentException("bad"));
        mockMvc.perform(post("/api/mv/1/storyboard"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // ---------- render ----------

    // L157: dryRun=true 正常路径
    @Test
    void render_withDryRunTrue_returnsOk() throws Exception {
        MvSong s = songWith(1L);
        when(mvService.render(1L, true)).thenReturn(s);
        mockMvc.perform(post("/api/mv/1/render").param("dryRun", "true"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.videoUrl").value("/api/mv/1/video"));
    }

    // L161/L162: IllegalStateException -> 400
    @Test
    void render_whenIllegalState_returnsBadRequest() throws Exception {
        when(mvService.render(eq(1L), Mockito.anyBoolean()))
                .thenThrow(new IllegalStateException("state"));
        mockMvc.perform(post("/api/mv/1/render").param("dryRun", "true"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.status").value("FAILED"));
    }

    // ---------- get ----------

    // L184: timelineJson==null -> ""
    @Test
    void get_whenTimelineJsonNull_usesEmptyString() throws Exception {
        MvSong s = songWith(1L);
        s.setTimelineJson(null);
        when(mvService.getById(1L)).thenReturn(s);
        mockMvc.perform(get("/api/mv/1"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.timelineJson").value(""));
    }

    // ---------- status ----------

    // L205: getStepStatuses 调用
    @Test
    void status_withRunId_returnsSteps() throws Exception {
        MvSong s = songWith(1L);
        s.setRunId(99L);
        s.setStatus("RUNNING");
        when(mvService.getById(1L)).thenReturn(s);
        when(mvService.getStepStatuses(99L)).thenReturn(List.of());
        mockMvc.perform(get("/api/mv/1/status"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value(1))
                .andExpect(jsonPath("$.runId").value(99))
                .andExpect(jsonPath("$.steps").isArray());
    }

    // L207/L208: ResourceNotFoundException -> 404
    @Test
    void status_whenResourceNotFound_returnsNotFound() throws Exception {
        when(mvService.getById(1L))
                .thenThrow(new ResourceNotFoundException("mv", 1L));
        mockMvc.perform(get("/api/mv/1/status"))
                .andExpect(status().isNotFound());
    }

    // ---------- video ----------

    // L218: sid 不匹配正则（这里用合法 id 但文件不存在走 L226）
    // L226/L227: 文件不存在 -> ResourceNotFoundException -> 404
    @Test
    void video_whenFileMissing_returnsNotFound() throws Exception {
        mockMvc.perform(get("/api/mv/999999/video"))
                .andExpect(status().isNotFound());
    }
}
