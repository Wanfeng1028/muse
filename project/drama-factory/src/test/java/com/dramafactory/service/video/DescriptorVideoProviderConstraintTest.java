package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DescriptorVideoProviderConstraintTest {

    private static final String JSON_WITH_CONSTRAINTS = """
            {
              "id": "demo-video",
              "label": "Demo Video",
              "submit": {
                "url": "http://example.com/submit",
                "method": "POST",
                "body": "{\\"prompt\\":\\"{{prompt}}\\",\\"seconds\\":{{seconds}},\\"model\\":\\"{{model}}\\"}",
                "taskIdPath": "data.taskId"
              },
              "poll": {
                "url": "http://example.com/poll?taskId={{taskId}}",
                "method": "GET",
                "statusPath": "data.status",
                "statusMap": {"DONE": "COMPLETED", "FAIL": "FAILED", "RUN": "PROCESSING"}
              },
              "models": [
                {
                  "id": "video-model-a",
                  "type": "video",
                  "constraints": {
                    "maxPromptChars": 10,
                    "minDurationSeconds": 4,
                    "maxDurationSeconds": 15
                  }
                }
              ]
            }
            """;

    private static final String JSON_WITHOUT_CONSTRAINTS = """
            {
              "id": "demo-video-2",
              "label": "Demo Video 2",
              "submit": {
                "url": "http://example.com/submit",
                "method": "POST",
                "body": "{\\"prompt\\":\\"{{prompt}}\\",\\"seconds\\":{{seconds}}}",
                "taskIdPath": "data.taskId"
              },
              "poll": {
                "url": "http://example.com/poll?taskId={{taskId}}",
                "method": "GET",
                "statusPath": "data.status",
                "statusMap": {"DONE": "COMPLETED"}
              },
              "models": [
                {
                  "id": "video-model-b",
                  "type": "video"
                }
              ]
            }
            """;

    private ObjectMapper objectMapper;
    private AtomicInteger counter;
    private VideoHttpGateway countingGateway;

    @BeforeEach
    void setUp() {
        objectMapper = new ObjectMapper();
        counter = new AtomicInteger(0);
        countingGateway = request -> {
            counter.incrementAndGet();
            throw new AssertionError("gateway.exchange 不应被调用");
        };
    }

    private DescriptorVideoProvider buildProvider(String json) throws Exception {
        ProviderDescriptor descriptor = objectMapper.readValue(json, ProviderDescriptor.class);
        return new DescriptorVideoProvider(descriptor, objectMapper, countingGateway, () -> "test-key");
    }

    private Shot shotWithPrompt(String prompt) {
        Shot shot = new Shot();
        shot.setVideoPrompt(prompt);
        shot.setDescription("desc");
        return shot;
    }

    @Test
    void promptTooLongThrowsConstraintException() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        assertThatThrownBy(() -> provider.submit(shotWithPrompt("0123456789A"), 5))
                .isInstanceOf(VideoRequestConstraintException.class);
    }

    @Test
    void promptTooLongDoesNotCallGateway() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        try {
            provider.submit(shotWithPrompt("0123456789A"), 5);
        } catch (VideoRequestConstraintException ignored) {
        }
        assertThat(counter.get()).isZero();
    }

    @Test
    void duration16SecondsThrowsConstraintExceptionAndSkipsGateway() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        try {
            provider.submit(shotWithPrompt("short"), 16);
        } catch (VideoRequestConstraintException ignored) {
        }
        assertThat(counter.get()).isZero();
    }

    @Test
    void duration16SecondsThrowsConstraintException() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        assertThatThrownBy(() -> provider.submit(shotWithPrompt("short"), 16))
                .isInstanceOf(VideoRequestConstraintException.class);
    }

    @Test
    void duration3SecondsThrowsConstraintException() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        assertThatThrownBy(() -> provider.submit(shotWithPrompt("short"), 3))
                .isInstanceOf(VideoRequestConstraintException.class);
    }

    @Test
    void duration3SecondsDoesNotCallGateway() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        try {
            provider.submit(shotWithPrompt("short"), 3);
        } catch (VideoRequestConstraintException ignored) {
        }
        assertThat(counter.get()).isZero();
    }

    @Test
    void constraintExceptionHasNonEmptyViolations() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        VideoRequestConstraintException ex = null;
        try {
            provider.submit(shotWithPrompt("0123456789A"), 5);
        } catch (VideoRequestConstraintException e) {
            ex = e;
        }
        assertThat(ex).isNotNull();
        assertThat(ex.getViolations()).isNotEmpty();
    }

    @Test
    void validRequestReachesGatewayNotConstraintException() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITH_CONSTRAINTS);
        assertThatThrownBy(() -> provider.submit(shotWithPrompt("hello"), 5))
                .isNotInstanceOf(VideoRequestConstraintException.class);
    }

    @Test
    void modelWithoutConstraintsDoesNotTriggerConstraintCheck() throws Exception {
        DescriptorVideoProvider provider = buildProvider(JSON_WITHOUT_CONSTRAINTS);
        assertThatThrownBy(() -> provider.submit(shotWithPrompt("this prompt is definitely longer than ten chars"), 99))
                .isNotInstanceOf(VideoRequestConstraintException.class);
    }
}