package com.scaffold.framework.audit;

public record OperationLogEntry(
        String module,
        String action,
        String requestMethod,
        String requestUrl,
        String requestParams,
        String operator,
        String ip,
        long cost,
        int result,
        String errorMessage
) {
}
