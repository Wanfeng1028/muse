// 文件：src/test/java/com/dramafactory/config/SettingsEnvPostProcessorV229Test.java

package com.dramafactory.config;

import com.dramafactory.service.SettingsService;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.mock.env.MockEnvironment;

import java.nio.file.Files;
import java.nio.file.Paths;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;
import static org.junit.jupiter.api.Assumptions.assumeFalse;

/**
 * 分支覆盖说明：
 * SettingsService.SETTINGS_PATH 是 static final 常量，写死生产路径 data/settings.json。
 * Java 17 无法可靠地用反射改写 static final，测试内也不允许触碰生产文件。
 * 因此本测试只能覆盖「文件不存在 → 静默 return」这一分支；
 * 「文件存在 → 读取 JSON → addAfter/addLast」分支需要真实存在 data/settings.json 的集成环境，
 * 此处用 assumeFalse 守护，若该文件恰好存在则跳过相关断言，保证任何环境都绿。
 * 异常路径（IOException / root 非 object）同样依赖文件存在，无法在纯单元测试中构造，故不硬凑。
 */
class SettingsEnvPostProcessorV229Test {

    private static final String SETTINGS_PATH = SettingsService.SETTINGS_PATH;

    @Test
    @DisplayName("settings.json 不存在时静默返回：不抛异常且不新增任何 propertySource")
    void postProcessEnvironment_silentlyReturnsWhenFileMissing() {
        assumeFalse(Files.isRegularFile(Paths.get(SETTINGS_PATH)),
                "生产路径 " + SETTINGS_PATH + " 存在，无法在纯单元测试中断言文件缺失分支");

        SettingsEnvironmentPostProcessor processor = new SettingsEnvironmentPostProcessor();
        ConfigurableEnvironment environment = new MockEnvironment();
        int before = environment.getPropertySources().size();

        assertThatCode(() -> processor.postProcessEnvironment(environment, new SpringApplication()))
                .doesNotThrowAnyException();

        assertThat(environment.getPropertySources()).hasSize(before);
        assertThat(environment.getPropertySources().contains("settingsJson")).isFalse();
    }

    @Test
    @DisplayName("settings.json 不存在时不会写入 settingsJson 属性源，且返回后环境仍可查询")
    void postProcessEnvironment_doesNotRegisterSettingsJsonSource() {
        assumeFalse(Files.isRegularFile(Paths.get(SETTINGS_PATH)),
                "生产路径 " + SETTINGS_PATH + " 存在，无法在纯单元测试中断言文件缺失分支");

        SettingsEnvironmentPostProcessor processor = new SettingsEnvironmentPostProcessor();
        MockEnvironment environment = new MockEnvironment();

        processor.postProcessEnvironment(environment, new SpringApplication());

        assertThat(environment.getPropertySources().contains("settingsJson")).isFalse();
        assertThat(environment.getProperty("settingsJson", "fallback")).isEqualTo("fallback");
    }
}

