package com.dramafactory.service.video;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.databind.JsonNode;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * 声明式 Provider 描述符。
 * 用户往 data/providers/ 目录丢一个 JSON 描述文件即可新增视频生成通道，
 * 无需改动 Java 代码、无需重启服务。
 */
@JsonIgnoreProperties(ignoreUnknown = true)
public class ProviderDescriptor {

    private static final Pattern ID_PATTERN = Pattern.compile("^[a-z][a-z0-9-]{2,63}$");
    private static final List<String> ALLOWED_STATUS =
            List.of("QUEUED", "PROCESSING", "COMPLETED", "FAILED");

    private String id;
    private String label;
    private String version;
    private List<DescriptorModel> models;
    private DescriptorAuth auth;
    private DescriptorEndpoint submit;
    private DescriptorPollEndpoint poll;

    public String getId() {
        return id;
    }

    public void setId(String id) {
        this.id = id;
    }

    public String getLabel() {
        return label;
    }

    public void setLabel(String label) {
        this.label = label;
    }

    public String getVersion() {
        return version;
    }

    public void setVersion(String version) {
        this.version = version;
    }

    public List<DescriptorModel> getModels() {
        return models;
    }

    public void setModels(List<DescriptorModel> models) {
        this.models = models;
    }

    public DescriptorAuth getAuth() {
        return auth;
    }

    public void setAuth(DescriptorAuth auth) {
        this.auth = auth;
    }

    public DescriptorEndpoint getSubmit() {
        return submit;
    }

    public void setSubmit(DescriptorEndpoint submit) {
        this.submit = submit;
    }

    public DescriptorPollEndpoint getPoll() {
        return poll;
    }

    public void setPoll(DescriptorPollEndpoint poll) {
        this.poll = poll;
    }

    /**
     * 校验描述符完整性。任一项不满足抛 {@link IllegalArgumentException}，信息写明字段名。
     */
    public void validate() {
        if (id == null || !ID_PATTERN.matcher(id).matches()) {
            throw new IllegalArgumentException("字段 id 非法，必须匹配 ^[a-z][a-z0-9-]{2,63}$：" + id);
        }
        if (label == null || label.isBlank()) {
            throw new IllegalArgumentException("字段 label 不能为空");
        }
        if (submit == null) {
            throw new IllegalArgumentException("字段 submit 不能为空");
        }
        if (submit.getUrl() == null || !submit.getUrl().startsWith("http")) {
            throw new IllegalArgumentException("字段 submit.url 必须以 http 开头：" + submit.getUrl());
        }
        if (poll == null) {
            throw new IllegalArgumentException("字段 poll 不能为空");
        }
        if (poll.getUrl() == null || !poll.getUrl().startsWith("http")) {
            throw new IllegalArgumentException("字段 poll.url 必须以 http 开头：" + poll.getUrl());
        }
        if (submit.getTaskIdPath() == null || submit.getTaskIdPath().isBlank()) {
            throw new IllegalArgumentException("字段 submit.taskIdPath 不能为空");
        }
        if (poll.getStatusPath() == null || poll.getStatusPath().isBlank()) {
            throw new IllegalArgumentException("字段 poll.statusPath 不能为空");
        }
        if (poll.getStatusMap() == null || poll.getStatusMap().isEmpty()) {
            throw new IllegalArgumentException("字段 poll.statusMap 不能为空");
        }
        for (Map.Entry<String, String> entry : poll.getStatusMap().entrySet()) {
            String value = entry.getValue();
            if (value == null || !ALLOWED_STATUS.contains(value)) {
                throw new IllegalArgumentException(
                        "字段 poll.statusMap 的值只能是 QUEUED/PROCESSING/COMPLETED/FAILED："
                                + entry.getKey() + " -> " + value);
            }
        }
        if (auth != null) {
            String type = auth.getType();
            if (type != null && ("bearer".equals(type) || "header".equals(type))) {
                String keyRef = auth.getKeyRef();
                if (keyRef == null
                        || !(keyRef.startsWith("env:") || keyRef.startsWith("settings:"))) {
                    throw new IllegalArgumentException(
                            "字段 auth.keyRef 在 type=" + type + " 时必须以 env: 或 settings: 开头：" + keyRef);
                }
            }
        }
        if (models != null) {
            for (DescriptorModel model : models) {
                model.validateConstraints();
            }
        }
    }

    /**
     * 按 "." 逐层解析 JSON 路径。path 为空或中间层为 null 返回 null。
     *
     * @param root 根节点
     * @param path 点分路径
     * @return 命中的节点，未命中为 null
     */
    public static JsonNode resolvePath(JsonNode root, String path) {
        if (root == null || path == null || path.isBlank()) {
            return null;
        }
        JsonNode current = root;
        for (String segment : path.split("\\.")) {
            if (current == null) {
                return null;
            }
            if (current.isArray()) {
                int index;
                try {
                    index = Integer.parseInt(segment);
                } catch (NumberFormatException e) {
                    return null;
                }
                current = (index < 0) ? null : current.get(index);
            } else {
                current = current.get(segment);
            }
        }
        return current;
    }

    /**
     * 模型条目。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DescriptorModel {

        private String id;
        private String label;
        private String type;
        private DescriptorConstraints constraints;

        public String getId() {
            return id;
        }

        public void setId(String id) {
            this.id = id;
        }

        public String getLabel() {
            return label;
        }

        public void setLabel(String label) {
            this.label = label;
        }

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }

        public DescriptorConstraints getConstraints() {
            return constraints;
        }

        public void setConstraints(DescriptorConstraints constraints) {
            this.constraints = constraints;
        }

        public void validateConstraints() {
            if (constraints == null) {
                return;
            }
            Integer min = constraints.getMinDurationSeconds();
            Integer max = constraints.getMaxDurationSeconds();
            if (min != null && max != null && min > max) {
                throw new IllegalArgumentException(
                        "字段 constraints.minDurationSeconds 不能大于 constraints.maxDurationSeconds："
                                + min + " > " + max);
            }
            Integer maxPromptChars = constraints.getMaxPromptChars();
            if (maxPromptChars != null && maxPromptChars <= 0) {
                throw new IllegalArgumentException(
                        "字段 constraints.maxPromptChars 必须大于 0：" + maxPromptChars);
            }
            Integer maxReferenceImages = constraints.getMaxReferenceImages();
            if (maxReferenceImages != null && maxReferenceImages < 0) {
                throw new IllegalArgumentException(
                        "字段 constraints.maxReferenceImages 不能小于 0：" + maxReferenceImages);
            }
        }

        /**
         * 视频模型硬约束声明。字段全部允许 null，表示没声明这条约束。
         */
        @JsonIgnoreProperties(ignoreUnknown = true)
        public static class DescriptorConstraints {

            private Integer maxPromptChars;
            private Integer minDurationSeconds;
            private Integer maxDurationSeconds;
            private List<String> resolutions;
            private List<String> aspectRatios;
            private Integer maxReferenceImages;
            private String source;

            public Integer getMaxPromptChars() {
                return maxPromptChars;
            }

            public void setMaxPromptChars(Integer maxPromptChars) {
                this.maxPromptChars = maxPromptChars;
            }

            public Integer getMinDurationSeconds() {
                return minDurationSeconds;
            }

            public void setMinDurationSeconds(Integer minDurationSeconds) {
                this.minDurationSeconds = minDurationSeconds;
            }

            public Integer getMaxDurationSeconds() {
                return maxDurationSeconds;
            }

            public void setMaxDurationSeconds(Integer maxDurationSeconds) {
                this.maxDurationSeconds = maxDurationSeconds;
            }

            public List<String> getResolutions() {
                return resolutions;
            }

            public void setResolutions(List<String> resolutions) {
                this.resolutions = resolutions;
            }

            public List<String> getAspectRatios() {
                return aspectRatios;
            }

            public void setAspectRatios(List<String> aspectRatios) {
                this.aspectRatios = aspectRatios;
            }

            public Integer getMaxReferenceImages() {
                return maxReferenceImages;
            }

            public void setMaxReferenceImages(Integer maxReferenceImages) {
                this.maxReferenceImages = maxReferenceImages;
            }

            public String getSource() {
                return source;
            }

            public void setSource(String source) {
                this.source = source;
            }

            public List<String> violations(String prompt, int seconds) {
                List<String> result = new ArrayList<>();
                if (prompt != null && maxPromptChars != null && prompt.length() > maxPromptChars) {
                    result.add("提示词过长：" + prompt.length() + " 字，通道上限 " + maxPromptChars + " 字");
                }
                if (minDurationSeconds != null && seconds < minDurationSeconds) {
                    result.add("时长过短：" + seconds + " 秒，通道要求至少 " + minDurationSeconds + " 秒");
                }
                if (maxDurationSeconds != null && seconds > maxDurationSeconds) {
                    result.add("时长过长：" + seconds + " 秒，通道上限 " + maxDurationSeconds + " 秒");
                }
                return result;
            }
        }
    }

    /**
     * 鉴权声明。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DescriptorAuth {

        private String type;
        private String keyRef;
        private String headerName;

        public String getType() {
            return type;
        }

        public void setType(String type) {
            this.type = type;
        }

        public String getKeyRef() {
            return keyRef;
        }

        public void setKeyRef(String keyRef) {
            this.keyRef = keyRef;
        }

        public String getHeaderName() {
            return headerName;
        }

        public void setHeaderName(String headerName) {
            this.headerName = headerName;
        }
    }

    /**
     * 提交端点声明。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DescriptorEndpoint {

        private String method;
        private String url;
        private Map<String, String> headers;
        private String body;
        private String taskIdPath;

        public String getMethod() {
            return method;
        }

        public void setMethod(String method) {
            this.method = method;
        }

        public String getUrl() {
            return url;
        }

        public void setUrl(String url) {
            this.url = url;
        }

        public Map<String, String> getHeaders() {
            return headers;
        }

        public void setHeaders(Map<String, String> headers) {
            this.headers = headers;
        }

        public String getBody() {
            return body;
        }

        public void setBody(String body) {
            this.body = body;
        }

        public String getTaskIdPath() {
            return taskIdPath;
        }

        public void setTaskIdPath(String taskIdPath) {
            this.taskIdPath = taskIdPath;
        }
    }

    /**
     * 轮询端点声明。
     */
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DescriptorPollEndpoint {

        private String method;
        private String url;
        private String statusPath;
        private Map<String, String> statusMap;
        private String videoUrlPath;
        private String errorPath;
        private String progressPath;
        private String body;

        public String getMethod() {
            return method;
        }

        public void setMethod(String method) {
            this.method = method;
        }

        public String getUrl() {
            return url;
        }

        public void setUrl(String url) {
            this.url = url;
        }

        public String getStatusPath() {
            return statusPath;
        }

        public void setStatusPath(String statusPath) {
            this.statusPath = statusPath;
        }

        public Map<String, String> getStatusMap() {
            return statusMap;
        }

        public void setStatusMap(Map<String, String> statusMap) {
            this.statusMap = statusMap;
        }

        public String getVideoUrlPath() {
            return videoUrlPath;
        }

        public void setVideoUrlPath(String videoUrlPath) {
            this.videoUrlPath = videoUrlPath;
        }

        public String getErrorPath() {
            return errorPath;
        }

        public void setErrorPath(String errorPath) {
            this.errorPath = errorPath;
        }

        public String getProgressPath() {
            return progressPath;
        }

        public void setProgressPath(String progressPath) {
            this.progressPath = progressPath;
        }

        public String getBody() {
            return body;
        }

        public void setBody(String body) {
            this.body = body;
        }
    }
}

