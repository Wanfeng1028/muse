package com.scaffold.common.domain;

/**
 * Unified pagination request model.
 *
 * @param pageNum 当前页码
 * @param pageSize 每页数量
 * @param sortField 排序字段
 * @param sortOrder 排序方向
 */
public record PageQuery(Integer pageNum, Integer pageSize, String sortField, String sortOrder) {

    public static final int DEFAULT_PAGE_NUM = 1;
    public static final int DEFAULT_PAGE_SIZE = 10;
    public static final int MAX_PAGE_SIZE = 100;

    public int normalizedPageNum() {
        return pageNum == null || pageNum < 1 ? DEFAULT_PAGE_NUM : pageNum;
    }

    public int normalizedPageSize() {
        if (pageSize == null || pageSize < 1) {
            return DEFAULT_PAGE_SIZE;
        }
        return Math.min(pageSize, MAX_PAGE_SIZE);
    }

    public String normalizedSortOrder() {
        if ("asc".equalsIgnoreCase(sortOrder)) {
            return "asc";
        }
        return "desc";
    }
}
