package com.dramaauth.db;

import com.dramaauth.repository.UserRepository;
import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.MigrationInfo;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * 验证 auth-service 的 Flyway 版本化迁移在 H2 内存库上正确落地。
 *
 * <p>目标：
 * <ul>
 *   <li>V1__baseline.sql 作为基线迁移被成功应用，flyway_schema_history 中存在 version=1 且已应用的记录；</li>
 *   <li>在 ddl-auto=validate 下 Spring 上下文能够正常启动，说明实体映射与迁移产生的表结构一致。</li>
 * </ul>
 */
@SpringBootTest
@TestPropertySource(properties = {
        "AUTH_JWT_SECRET=dummy-flyway-test-secret-0123456789abcdef",
        "spring.jpa.hibernate.ddl-auto=validate",
        "spring.datasource.url=jdbc:h2:mem:authflywaytest;DB_CLOSE_DELAY=-1"
})
class AuthFlywayMigrationTest {

    @Autowired
    private Flyway flyway;

    @Autowired
    private UserRepository userRepository;

    /**
     * V1 基线迁移应被成功应用，且历史记录中存在 version=1 的已应用条目。
     */
    @Test
    void v1BaselineIsAppliedSuccessfully() {
        MigrationInfo[] applied = flyway.info().applied();
        assertThat(applied).isNotEmpty();
        assertThat(applied)
                .anySatisfy(info -> {
                    assertThat(info.getVersion()).isNotNull();
                    assertThat(info.getVersion().getVersion()).isEqualTo("1");
                    assertThat(info.getState().isApplied()).isTrue();
                });
    }

    /**
     * 在 ddl-auto=validate 下能访问 UserRepository，说明实体映射与迁移表结构一致。
     * 若结构不一致，Spring 上下文会在启动阶段直接失败。
     */
    @Test
    void schemaMatchesEntitiesUnderValidate() {
        assertThat(userRepository.count()).isGreaterThanOrEqualTo(0L);
    }
}
