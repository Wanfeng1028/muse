package com.dramafactory.service.video;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;

import com.dramafactory.service.video.ProviderDescriptor.DescriptorModel;

class VideoRequestValidatorTest {

    private final VideoRequestValidator validator = new VideoRequestValidator();

    private DescriptorModel model(String id, String type, String constraintsJson) throws Exception {
        DescriptorModel model = new DescriptorModel();
        model.setId(id);
        model.setType(type);
        if (constraintsJson != null) {
            DescriptorModel.DescriptorConstraints c = new com.fasterxml.jackson.databind.ObjectMapper()
                    .readValue(constraintsJson, DescriptorModel.DescriptorConstraints.class);
            model.setConstraints(c);
        }
        return model;
    }

    @Test
    void returnsEmptyWhenModelIsNull() throws Exception {
        List<String> result = validator.validate(null, "hello", 5);
        assertThat(result).isEmpty();
    }

    @Test
    void returnsEmptyWhenConstraintsIsNull() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", null);
        List<String> result = validator.validate(model, "hello", 5);
        assertThat(result).isEmpty();
    }

    @Test
    void returnsEmptyForValidRequest() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 5);
        assertThat(result).isEmpty();
    }

    @Test
    void returnsMessageWithPromptTooLongWhenPromptExceedsLimit() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 501; i++) {
            sb.append('a');
        }
        List<String> result = validator.validate(model, sb.toString(), 5);
        assertThat(result).anyMatch(msg -> msg.contains("提示词过长"));
    }

    @Test
    void returnsNonEmptyWhenSecondsExceedLimit() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 16);
        assertThat(result).isNotEmpty();
    }

    @Test
    void seedance20PassesAt500PromptLength() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 500; i++) {
            sb.append('a');
        }
        List<String> result = validator.validate(model, sb.toString(), 5);
        assertThat(result).isEmpty();
    }

    @Test
    void seedance20BlocksAt501PromptLength() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 501; i++) {
            sb.append('a');
        }
        List<String> result = validator.validate(model, sb.toString(), 5);
        assertThat(result).isNotEmpty();
    }

    @Test
    void seedance20PassesAt15Seconds() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 15);
        assertThat(result).isEmpty();
    }

    @Test
    void seedance20BlocksAt16Seconds() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 16);
        assertThat(result).isNotEmpty();
    }

    @Test
    void minimaxH3PassesAt7000PromptLength() throws Exception {
        DescriptorModel model = model("MiniMax-H3", "video", "{\"maxPromptChars\":7000,\"maxDurationSeconds\":30,\"minDurationSeconds\":1}");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 7000; i++) {
            sb.append('a');
        }
        List<String> result = validator.validate(model, sb.toString(), 5);
        assertThat(result).isEmpty();
    }

    @Test
    void minimaxH3BlocksAt7001PromptLength() throws Exception {
        DescriptorModel model = model("MiniMax-H3", "video", "{\"maxPromptChars\":7000,\"maxDurationSeconds\":30,\"minDurationSeconds\":1}");
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < 7001; i++) {
            sb.append('a');
        }
        List<String> result = validator.validate(model, sb.toString(), 5);
        assertThat(result).isNotEmpty();
    }

    @Test
    void wan30PassesAt30Seconds() throws Exception {
        DescriptorModel model = model("wan-3.0", "video", "{\"maxPromptChars\":1000,\"maxDurationSeconds\":30,\"minDurationSeconds\":2}");
        List<String> result = validator.validate(model, "hello", 30);
        assertThat(result).isEmpty();
    }

    @Test
    void wan30BlocksAt31Seconds() throws Exception {
        DescriptorModel model = model("wan-3.0", "video", "{\"maxPromptChars\":1000,\"maxDurationSeconds\":30,\"minDurationSeconds\":2}");
        List<String> result = validator.validate(model, "hello", 31);
        assertThat(result).isNotEmpty();
    }

    @Test
    void wan30PassesAt2Seconds() throws Exception {
        DescriptorModel model = model("wan-3.0", "video", "{\"maxPromptChars\":1000,\"maxDurationSeconds\":30,\"minDurationSeconds\":2}");
        List<String> result = validator.validate(model, "hello", 2);
        assertThat(result).isEmpty();
    }

    @Test
    void wan30BlocksAt1Second() throws Exception {
        DescriptorModel model = model("wan-3.0", "video", "{\"maxPromptChars\":1000,\"maxDurationSeconds\":30,\"minDurationSeconds\":2}");
        List<String> result = validator.validate(model, "hello", 1);
        assertThat(result).isNotEmpty();
    }

    @Test
    void seedance25PassesAt30Seconds() throws Exception {
        DescriptorModel model = model("seedance-2.5", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":30,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 30);
        assertThat(result).isEmpty();
    }

    @Test
    void doesNotThrowWhenPromptIsNull() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, null, 5);
        assertThat(result).isNotNull();
    }

    @Test
    void returnsNonNullList() throws Exception {
        DescriptorModel model = model("seedance-2.0", "video", "{\"maxPromptChars\":500,\"maxDurationSeconds\":15,\"minDurationSeconds\":1}");
        List<String> result = validator.validate(model, "hello", 5);
        assertThat(result).isNotNull();
    }
}