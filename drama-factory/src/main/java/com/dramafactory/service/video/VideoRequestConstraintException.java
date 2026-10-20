package com.dramafactory.service.video;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class VideoRequestConstraintException extends IllegalArgumentException {

    private final List<String> violations;

    public VideoRequestConstraintException(String message, List<String> violations) {
        super(message == null ? "违反视频通道硬约束。" : message);
        this.violations = violations == null
                ? Collections.emptyList()
                : Collections.unmodifiableList(new ArrayList<>(violations));
    }

    public List<String> getViolations() {
        return new ArrayList<>(violations);
    }
}