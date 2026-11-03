package com.scaffold.common.domain;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PageQueryTest {

    @Test
    void normalizesMissingAndInvalidPaginationValues() {
        PageQuery query = new PageQuery(0, 500, "createTime", "descending");

        assertThat(query.normalizedPageNum()).isEqualTo(1);
        assertThat(query.normalizedPageSize()).isEqualTo(100);
        assertThat(query.normalizedSortOrder()).isEqualTo("desc");
    }

    @Test
    void keepsValidPaginationValues() {
        PageQuery query = new PageQuery(2, 20, "username", "asc");

        assertThat(query.normalizedPageNum()).isEqualTo(2);
        assertThat(query.normalizedPageSize()).isEqualTo(20);
        assertThat(query.sortField()).isEqualTo("username");
        assertThat(query.normalizedSortOrder()).isEqualTo("asc");
    }
}
