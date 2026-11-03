package com.dramafactory.service.video;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;

import org.junit.jupiter.api.Test;

import com.dramafactory.service.video.ProviderDescriptor.DescriptorModel.DescriptorConstraints;

class DescriptorConstraintsTest {

    private DescriptorConstraints newConstraints() {
        return new DescriptorConstraints();
    }

    private ProviderDescriptor.DescriptorModel newModel() {
        return new ProviderDescriptor.DescriptorModel();
    }

    private ProviderDescriptor.DescriptorModel newModelWith(DescriptorConstraints constraints) {
        ProviderDescriptor.DescriptorModel model = newModel();
        model.setConstraints(constraints);
        return model;
    }

    @Test
    void violationsIsEmptyWhenNoConstraints() {
        DescriptorConstraints constraints = newConstraints();
        assertThat(constraints.violations("hello world", 10)).isEmpty();
    }

    @Test
    void promptOverLimitGivesOneViolationWithNumber() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(5);
        List<String> result = constraints.violations("abcdefgh", 10);
        assertThat(result).hasSize(1);
        assertThat(result.get(0)).contains("5");
    }

    @Test
    void promptExactlyAtLimitPasses() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(5);
        assertThat(constraints.violations("abcde", 10)).isEmpty();
    }

    @Test
    void emptyPromptDoesNotTriggerLengthViolation() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(5);
        assertThat(constraints.violations("", 10)).isEmpty();
    }

    @Test
    void durationBelowMinGivesOneViolation() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMinDurationSeconds(5);
        assertThat(constraints.violations("ok", 2)).hasSize(1);
    }

    @Test
    void durationAboveMaxGivesOneViolation() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxDurationSeconds(5);
        assertThat(constraints.violations("ok", 20)).hasSize(1);
    }

    @Test
    void durationExactlyAtBoundaryPasses() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMinDurationSeconds(5);
        constraints.setMaxDurationSeconds(10);
        assertThat(constraints.violations("ok", 5)).isEmpty();
        assertThat(constraints.violations("ok", 10)).isEmpty();
    }

    @Test
    void promptAndDurationViolationsTogetherGiveTwo() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(3);
        constraints.setMinDurationSeconds(10);
        assertThat(constraints.violations("abcdef", 1)).hasSize(2);
    }

    @Test
    void minGreaterThanMaxThrowsOnValidate() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMinDurationSeconds(10);
        constraints.setMaxDurationSeconds(5);
        assertThatThrownBy(newModelWith(constraints)::validateConstraints).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void zeroMaxPromptCharsThrowsOnValidate() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(0);
        assertThatThrownBy(newModelWith(constraints)::validateConstraints).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void negativeMaxReferenceImagesThrowsOnValidate() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxReferenceImages(-1);
        assertThatThrownBy(newModelWith(constraints)::validateConstraints).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void validConstraintsDoesNotThrow() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(100);
        constraints.setMinDurationSeconds(1);
        constraints.setMaxDurationSeconds(60);
        constraints.setMaxReferenceImages(3);
        newModelWith(constraints).validateConstraints();
    }

    @Test
    void modelValidateConstraintsThrowsWhenMinGreaterThanMax() {
        ProviderDescriptor.DescriptorModel model = newModel();
        DescriptorConstraints constraints = newConstraints();
        constraints.setMinDurationSeconds(10);
        constraints.setMaxDurationSeconds(5);
        model.setConstraints(constraints);
        assertThatThrownBy(model::validateConstraints).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void providerValidateDoesNotThrowWhenModelsEmpty() {
        ProviderDescriptor descriptor = new ProviderDescriptor();
        descriptor.setId("prov-test");
        descriptor.setLabel("test");
        ProviderDescriptor.DescriptorEndpoint submit = new ProviderDescriptor.DescriptorEndpoint();
        submit.setUrl("http://localhost:9999/v");
        submit.setTaskIdPath("id");
        descriptor.setSubmit(submit);
        ProviderDescriptor.DescriptorPollEndpoint poll = new ProviderDescriptor.DescriptorPollEndpoint();
        poll.setUrl("http://localhost:9999/s");
        poll.setStatusPath("s");
        poll.setStatusMap(java.util.Map.of("ok", "COMPLETED"));
        descriptor.setPoll(poll);
        descriptor.setModels(java.util.List.of());
        descriptor.validate();
    }

    @Test
    void resolutionsRoundTrip() {
        DescriptorConstraints constraints = newConstraints();
        List<String> resolutions = List.of("720p", "1080p");
        constraints.setResolutions(resolutions);
        assertThat(constraints.getResolutions()).isEqualTo(resolutions);
    }

    @Test
    void aspectRatiosRoundTrip() {
        DescriptorConstraints constraints = newConstraints();
        List<String> ratios = List.of("16:9", "9:16");
        constraints.setAspectRatios(ratios);
        assertThat(constraints.getAspectRatios()).isEqualTo(ratios);
    }

    @Test
    void sourceRoundTrip() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setSource("official");
        assertThat(constraints.getSource()).isEqualTo("official");
    }

    @Test
    void returnedViolationsListIsMutableAndDoesNotAffectInternal() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(1);
        List<String> first = constraints.violations("abcdef", 10);
        first.add("extra");
        List<String> second = constraints.violations("abcdef", 10);
        assertThat(second).hasSize(1);
    }

    @Test
    void chineseViolationMessageIsNotEmptyAndContainsChinese() {
        DescriptorConstraints constraints = newConstraints();
        constraints.setMaxPromptChars(1);
        String message = constraints.violations("abcdef", 10).get(0);
        assertThat(message).isNotEmpty();
        assertThat(message).matches(".*[\\u4e00-\\u9fa5].*");
    }
}
