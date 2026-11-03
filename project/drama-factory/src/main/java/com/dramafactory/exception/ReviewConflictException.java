package com.dramafactory.exception;

import com.dramafactory.model.ReviewStatus;

/**
 * 审核并发冲突：请求带过来的 version 和库里的对不上，全局 handler 会转成 409。
 */
public class ReviewConflictException extends RuntimeException {

    public ReviewConflictException(Long reviewItemId, ReviewStatus currentStatus, int currentVersion) {
        super("Review conflict: reviewItemId=" + reviewItemId
                + ", currentStatus=" + currentStatus
                + ", currentVersion=" + currentVersion);
    }
}
