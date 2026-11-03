package com.scaffold.common.domain;

import org.junit.jupiter.api.Test;

import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;

class PageResultTest {

    @Test
    void createsFrontendPaginationShape() {
        PageResult<String> result = PageResult.of(List.of("admin"), 56, 1, 10);

        assertThat(result.rows()).containsExactly("admin");
        assertThat(result.total()).isEqualTo(56);
        assertThat(result.pageNum()).isEqualTo(1);
        assertThat(result.pageSize()).isEqualTo(10);
    }
}
