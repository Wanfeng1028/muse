package com.dramafactory.service;

import com.dramafactory.service.ChapterEvent;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ChapterEventServiceTest {

    static class QueueExchange implements ChapterEventService.HttpExchange {
        private final Deque<String> queue = new ArrayDeque<>();

        QueueExchange(List<String> bodies) {
            queue.addAll(bodies);
        }

        @Override
        public HttpResponse<String> send(HttpRequest request) throws Exception {
            String content = queue.isEmpty() ? "[]" : queue.poll();
            String wrapped = "{\"choices\":[{\"message\":{\"content\":" +
                    new ObjectMapper().writeValueAsString(content) + "}}]}";
            @SuppressWarnings("unchecked")
            HttpResponse<String> response = mock(HttpResponse.class);
            when(response.statusCode()).thenReturn(200);
            when(response.body()).thenReturn(wrapped);
            return response;
        }
    }

    private static final String CANNED = "[{\"sourceChapter\":\"第1章\",\"chapterTitle\":\"楔子\",\"characters\":[\"张三\"]," +
            "\"coreEvent\":\"张三离家出发去京城赶考\",\"mainlineRelation\":\"强：主线开端\",\"infoDensity\":\"高\"," +
            "\"estimatedSeconds\":50,\"emotions\":\"期待+紧张\"}]";

    private PromptFileService writePromptFile(Path tmp) throws Exception {
        Files.writeString(tmp.resolve("chapter-events.md"),
                "---\nname: chapter-events\nversion: 1.0.0\ndescription: 提取章节事件\n---\n\n请提取章节事件。\n");
        return new PromptFileService(tmp.toString());
    }

    @Test
    void extract两章返回两个事件(@TempDir Path tmp) throws Exception {
        PromptFileService promptFileService = writePromptFile(tmp);
        QueueExchange exchange = new QueueExchange(List.of(CANNED, CANNED));
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer test-key-1234"));

        ChapterEventService service = new ChapterEventService(credentialResolver, new ObjectMapper(),
                promptFileService, "Deepseek-v4-flash", 4000, exchange);

        List<ChapterEvent> events = service.extract("第1章 楔子\n正文A\n第2章 转折\n正文B");

        assertThat(events).hasSize(2);
        assertThat(events.get(0).chapterIndex()).isEqualTo(1);
        assertThat(events.get(1).chapterIndex()).isEqualTo(2);
        assertThat(events.get(0).coreEvent()).isEqualTo("张三离家出发去京城赶考");
    }

    @Test
    void splitChapters按标题切分() {
        List<ChapterEventService.ChapterTitle> chapters =
                ChapterEventService.splitChapters("第1章 楔子\n正文A\n第2章 转折\n正文B");
        assertThat(chapters).hasSize(2);
    }

    @Test
    void splitChapters无标题回退全文() {
        List<ChapterEventService.ChapterTitle> chapters =
                ChapterEventService.splitChapters("没有标题的正文");
        assertThat(chapters).hasSize(1);
        assertThat(chapters.get(0).title()).isEqualTo("全文");
    }

    @Test
    void extract空白输入抛异常(@TempDir Path tmp) throws Exception {
        PromptFileService promptFileService = writePromptFile(tmp);
        QueueExchange exchange = new QueueExchange(List.of(CANNED));
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer test-key-1234"));

        ChapterEventService service = new ChapterEventService(credentialResolver, new ObjectMapper(),
                promptFileService, "Deepseek-v4-flash", 4000, exchange);

        assertThatThrownBy(() -> service.extract("  "))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void extract空数组抛RuntimeException(@TempDir Path tmp) throws Exception {
        PromptFileService promptFileService = writePromptFile(tmp);
        QueueExchange exchange = new QueueExchange(List.of("[]"));
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer test-key-1234"));

        ChapterEventService service = new ChapterEventService(credentialResolver, new ObjectMapper(),
                promptFileService, "Deepseek-v4-flash", 4000, exchange);

        assertThatThrownBy(() -> service.extract("第1章 楔子\n正文A"))
                .isInstanceOf(RuntimeException.class);
    }

    @Test
    void extract非数组抛RuntimeException(@TempDir Path tmp) throws Exception {
        PromptFileService promptFileService = writePromptFile(tmp);
        QueueExchange exchange = new QueueExchange(List.of("{\"a\":1}"));
        CredentialResolver credentialResolver = mock(CredentialResolver.class);
        when(credentialResolver.chatAuth()).thenReturn(Map.entry("Authorization", "Bearer test-key-1234"));

        ChapterEventService service = new ChapterEventService(credentialResolver, new ObjectMapper(),
                promptFileService, "Deepseek-v4-flash", 4000, exchange);

        assertThatThrownBy(() -> service.extract("第1章 楔子\n正文A"))
                .isInstanceOf(RuntimeException.class);
    }
}

