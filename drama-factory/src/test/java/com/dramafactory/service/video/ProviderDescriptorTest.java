package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class ProviderDescriptorTest {

    private ProviderDescriptor validDescriptor() {
        ProviderDescriptor d = new ProviderDescriptor();
        d.setId("demo");
        d.setLabel("演示");

        ProviderDescriptor.DescriptorAuth auth = new ProviderDescriptor.DescriptorAuth();
        auth.setType("bearer");
        auth.setKeyRef("env:DEMO_KEY");
        d.setAuth(auth);

        ProviderDescriptor.DescriptorEndpoint submit = new ProviderDescriptor.DescriptorEndpoint();
        submit.setMethod("POST");
        submit.setUrl("https://example.com/v1/videos");
        submit.setTaskIdPath("data.task_id");
        d.setSubmit(submit);

        ProviderDescriptor.DescriptorPollEndpoint poll = new ProviderDescriptor.DescriptorPollEndpoint();
        poll.setMethod("GET");
        poll.setUrl("https://example.com/v1/videos/{{taskId}}");
        poll.setStatusPath("data.status");
        poll.setStatusMap(java.util.Map.of(
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
    void validate_通过合法描述符不抛异常() {
        ProviderDescriptor d = validDescriptor();
        d.validate();
    }

    @Test
    void validate_id非法抛异常() {
        ProviderDescriptor d = validDescriptor();
        d.setId("Bad_ID");
        assertThatThrownBy(d::validate)
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("id");
    }

    @Test
    void validate_submitUrl非http抛异常() {
        ProviderDescriptor d = validDescriptor();
        d.getSubmit().setUrl("ftp://x");
        assertThatThrownBy(d::validate)
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void validate_statusMap值不在枚举内抛异常() {
        ProviderDescriptor d = validDescriptor();
        d.getPoll().setStatusMap(java.util.Map.of(
                "queued", "QUEUED",
                "processing", "PROCESSING",
                "succeeded", "COMPLETED",
                "failed", "DONE"));
        assertThatThrownBy(d::validate)
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void validate_bearer类型但keyRef非引用抛异常() {
        ProviderDescriptor d = validDescriptor();
        d.getAuth().setType("bearer");
        d.getAuth().setKeyRef("plain");
        assertThatThrownBy(d::validate)
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void resolvePath_正常取值() throws Exception {
        ObjectMapper om = new ObjectMapper();
        JsonNode root = om.readTree("{\"data\":{\"task_id\":\"t1\"}}");
        JsonNode node = ProviderDescriptor.resolvePath(root, "data.task_id");
        assertThat(node).isNotNull();
        assertThat(node.asText()).isEqualTo("t1");
    }

    @Test
    void resolvePath_缺失返回null() throws Exception {
        ObjectMapper om = new ObjectMapper();
        JsonNode root = om.readTree("{\"data\":{\"task_id\":\"t1\"}}");
        assertThat(ProviderDescriptor.resolvePath(root, "data.missing")).isNull();
    }

    @Test
    void resolvePath_空路径返回null() throws Exception {
        ObjectMapper om = new ObjectMapper();
        JsonNode root = om.readTree("{\"data\":{\"task_id\":\"t1\"}}");
        assertThat(ProviderDescriptor.resolvePath(root, "")).isNull();
    }
}

