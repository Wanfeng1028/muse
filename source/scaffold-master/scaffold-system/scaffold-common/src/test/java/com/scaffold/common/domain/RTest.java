package com.scaffold.common.domain;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class RTest {

    @Test
    void successBuildsUnifiedResponseShape() {
        R<String> response = R.success("ok");

        assertThat(response.code()).isEqualTo(200);
        assertThat(response.message()).isEqualTo("操作成功");
        assertThat(response.data()).isEqualTo("ok");
    }
}
