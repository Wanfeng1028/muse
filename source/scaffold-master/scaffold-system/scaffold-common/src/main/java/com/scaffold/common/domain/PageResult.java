package com.scaffold.common.domain;

import java.util.List;

/**
 * Unified pagination response model.
 *
 * @param rows 当前页数据
 * @param total 总记录数
 * @param pageNum 当前页码
 * @param pageSize 每页数量
 */
public record PageResult<T>(List<T> rows, long total, int pageNum, int pageSize) {

    public static <T> PageResult<T> of(List<T> rows, long total, int pageNum, int pageSize) {
        return new PageResult<>(rows, total, pageNum, pageSize);
    }
}
