package com.dramafactory.db;

import com.dramafactory.repository.DramaProjectRepository;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationInfo;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 验证 Flyway 基线迁移已应用，并且 Hibernate 在 ddl-auto=validate 下能通过
 * —— 即实体映射与 V1__baseline.sql 产生的 schema 完全一致。
 */
@SpringBootTest
@TestPropertySource(properties = {
        "spring.jpa.hibernate.ddl-auto=validate"
})
class FlywayMigrationTest {

    @Autowired
    private Flyway flyway;

    @Autowired
    private DramaProjectRepository dramaProjectRepository;

    @Test
    void v1BaselineIsAppliedSuccessfully() {
        MigrationInfo[] applied = flyway.info().applied();
        assertThat(applied).isNotEmpty();

        boolean v1Applied = false;
        for (MigrationInfo info : applied) {
            if (info.getVersion() != null
                    && "1".equals(info.getVersion().getVersion())
                    && info.getState() != null
                    && info.getState().isApplied()) {
                v1Applied = true;
                break;
            }
        }
        assertThat(v1Applied)
                .as("Flyway V1 基线迁移应处于 SUCCESS 状态")
                .isTrue();
    }

    @Test
    void schemaMatchesEntitiesUnderValidate() {
        // 若 schema 与实体映射不一致，ddl-auto=validate 会在上下文启动时失败；
        // 这里执行一次查询，进一步证明表结构与 Repository 映射可用。
        long count = dramaProjectRepository.count();
        assertThat(count).isGreaterThanOrEqualTo(0L);
    }
}
