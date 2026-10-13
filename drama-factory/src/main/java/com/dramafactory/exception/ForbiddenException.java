package com.dramafactory.exception;

/**
 * 访问了不属于自己的资源时抛这个，全局 handler 会转成 403。
 */
public class ForbiddenException extends RuntimeException {

    public ForbiddenException(String resource, Object id) {
        super("Forbidden: " + resource + " " + id);
    }
}
