package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.net.URI;
import java.net.http.HttpRequest;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DescriptorVideoProviderTest {

    private static final String TEST_KEY = "test-key-abcdefgh1234";

    private ProviderDescriptor newDescriptor() {
        ProviderDescriptor d = new ProviderDescriptor();
        d.setId("seedance-demo");
        d.setLabel("Seedance Demo");

        ProviderDescriptor.DescriptorAuth auth = new ProviderDescriptor.DescriptorAuth();
        auth.setType("bearer");
        auth.setKeyRef("env:DEMO_KEY");
        d.setAuth(auth);

        ProviderDescriptor.DescriptorEndpoint submit = new ProviderDescriptor.DescriptorEndpoint();
        submit.setMethod("POST");
        submit.setUrl("https://example.com/v1/videos");
        submit.setHeaders(Map.of("Content-Type", "application/json"));
        submit.setBody("{\"model\":\"{{model}}\",\"prompt\":\"{{prompt}}\",\"seconds\":{{seconds}}}");
        submit.setTaskIdPath("data.task_id");
        d.setSubmit(submit);

        ProviderDescriptor.DescriptorPollEndpoint poll = new ProviderDescriptor.DescriptorPollEndpoint();
        poll.setMethod("GET");
        poll.setUrl("https://example.com/v1/videos/{{taskId}}");
        poll.setStatusPath("data.status");
        poll.setStatusMap(Map.of(
                "queued", "QUEUED",
                "processing", "PROCESSING",
                "succeeded", "COMPLETED",
                "failed", "FAILED"));
        poll.setVideoUrlPath("data.video_url");
        poll.setErrorPath("data.error_message");
        poll.setProgressPath("data.progress");
        d.setPoll(poll);

        ProviderDescriptor.DescriptorModel model = new ProviderDescriptor.DescriptorModel();
        model.setId("seedance-2-0");
        model.setLabel("Seedance 2.0");
        model.setType("video");
        d.setModels(List.of(model));

        return d;
    }

    static class RecordingGateway implements VideoHttpGateway {
        final List<HttpRequest> requests = new ArrayList<>();
        volatile String nextBody = "{}";
        volatile int nextStatus = 200;

        @Override
        public GatewayResponse exchange(HttpRequest r) {
            requests.add(r);
            return new GatewayResponse(nextStatus, nextBody);
        }
    }

    private DescriptorVideoProvider provider(RecordingGateway gateway, Supplier<String> keySupplier) {
        return new DescriptorVideoProvider(newDescriptor(), new ObjectMapper(), gateway, keySupplier);
    }

    @Test
    void name_返回descriptor前缀() {
        RecordingGateway gateway = new RecordingGateway();
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);
        assertThat(p.name()).isEqualTo("descriptor:seedance-demo");
    }

    @Test
    void submit_返回任务ID并携带鉴权头() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextBody = "{\"data\":{\"task_id\":\"t-123\"}}";
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);

        Shot shot = new Shot();
        shot.setVideoPrompt("a cat video");

        String taskId = p.submit(shot, 5);

        assertThat(taskId).isEqualTo("t-123");
        assertThat(gateway.requests).hasSize(1);
        HttpRequest req = gateway.requests.get(0);
        assertThat(req.headers().firstValue("Authorization")).contains("Bearer " + TEST_KEY);
        assertThat(req.uri()).isEqualTo(URI.create("https://example.com/v1/videos"));
    }

    @Test
    void poll_成功返回COMPLETED与视频地址() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextBody = "{\"data\":{\"status\":\"succeeded\",\"video_url\":\"https://cdn.example/v.mp4\",\"progress\":100}}";
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);

        VideoProvider.ProbeResult result = p.poll("t-123");

        assertThat(result.status()).isEqualTo(VideoProvider.RemoteStatus.COMPLETED);
        assertThat(result.videoUrl()).isEqualTo("https://cdn.example/v.mp4");
    }

    @Test
    void poll_失败返回FAILED与错误信息() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextBody = "{\"data\":{\"status\":\"failed\",\"error_message\":\"boom\"}}";
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);

        VideoProvider.ProbeResult result = p.poll("t-123");

        assertThat(result.status()).isEqualTo(VideoProvider.RemoteStatus.FAILED);
        assertThat(result.errorMessage()).contains("boom");
    }

    @Test
    void poll_未知状态回退为PROCESSING() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextBody = "{\"data\":{\"status\":\"dreaming\"}}";
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);

        VideoProvider.ProbeResult result = p.poll("t-123");

        assertThat(result.status()).isEqualTo(VideoProvider.RemoteStatus.PROCESSING);
    }

    @Test
    void submit_错误体泄露密钥时被脱敏() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextStatus = 500;
        gateway.nextBody = "{\"error\":\"bad key " + TEST_KEY + "\"}";
        DescriptorVideoProvider p = provider(gateway, () -> TEST_KEY);

        Shot shot = new Shot();
        shot.setVideoPrompt("a cat video");

        assertThatThrownBy(() -> p.submit(shot, 5))
                .isInstanceOf(RuntimeException.class)
                .satisfies(ex -> {
                    assertThat(ex.getMessage()).doesNotContain(TEST_KEY);
                    assertThat(ex.getMessage()).contains("****");
                });
    }

    @Test
    void submit_密钥为null抛IllegalStateException() {
        RecordingGateway gateway = new RecordingGateway();
        DescriptorVideoProvider p = provider(gateway, () -> null);

        Shot shot = new Shot();
        shot.setVideoPrompt("a cat video");

        assertThatThrownBy(() -> p.submit(shot, 5))
                .isInstanceOf(IllegalStateException.class);
    }

    private static ProviderDescriptor newPostBodyDescriptor() {
        ProviderDescriptor d = new ProviderDescriptor();
        d.setId("seedance-post-demo");
        d.setLabel("Seedance Post Demo");

        ProviderDescriptor.DescriptorAuth auth = new ProviderDescriptor.DescriptorAuth();
        auth.setType("bearer");
        auth.setKeyRef("env:DEMO_KEY");
        d.setAuth(auth);

        ProviderDescriptor.DescriptorEndpoint submit = new ProviderDescriptor.DescriptorEndpoint();
        submit.setMethod("POST");
        submit.setUrl("https://example.com/v1/videos");
        submit.setHeaders(Map.of("Content-Type", "application/json"));
        submit.setBody("{\"model\":\"{{model}}\",\"prompt\":\"{{prompt}}\",\"seconds\":{{seconds}}}");
        submit.setTaskIdPath("data.task_id");
        d.setSubmit(submit);

        ProviderDescriptor.DescriptorPollEndpoint poll = new ProviderDescriptor.DescriptorPollEndpoint();
        poll.setMethod("POST");
        poll.setUrl("https://example.com/v1/videos/status");
        poll.setBody("{\"taskIdCode\":\"{{taskId}}\"}");
        poll.setStatusPath("data.status");
        poll.setStatusMap(Map.of(
                "queued", "QUEUED",
                "processing", "PROCESSING",
                "succeeded", "COMPLETED",
                "failed", "FAILED"));
        poll.setVideoUrlPath("data.video_url");
        d.setPoll(poll);

        ProviderDescriptor.DescriptorModel model = new ProviderDescriptor.DescriptorModel();
        model.setId("seedance-2-0");
        model.setLabel("Seedance 2.0");
        model.setType("video");
        d.setModels(List.of(model));

        return d;
    }

    @Test
    void poll_POST带body时以application_json发送() {
        RecordingGateway gateway = new RecordingGateway();
        gateway.nextBody = "{\"data\":{\"status\":\"succeeded\",\"video_url\":\"https://cdn.example/v.mp4\"}}";
        DescriptorVideoProvider p = new DescriptorVideoProvider(
                newPostBodyDescriptor(), new ObjectMapper(), gateway, () -> TEST_KEY);

        p.poll("t-123");

        assertThat(gateway.requests).hasSize(1);
        HttpRequest req = gateway.requests.get(0);
        assertThat(req.method()).isEqualTo("POST");
        assertThat(req.headers().firstValue("Content-Type"))
                .hasValueSatisfying(v -> assertThat(v).contains("application/json"));
        assertThat(req.bodyPublisher()).isPresent();
    }
}

