package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class ProviderDescriptorRegistryTest {

    private static final String DEMO_JSON_TEMPLATE = "{\n" +
            "  \"id\": \"demo\",\n" +
            "  \"label\": \"%s\",\n" +
            "  \"auth\": {\"type\": \"bearer\", \"keyRef\": \"env:DEMO_KEY\"},\n" +
            "  \"submit\": {\"method\": \"POST\", \"url\": \"https://example.com/v1/videos\", \"taskIdPath\": \"data.task_id\"},\n" +
            "  \"poll\": {\"method\": \"GET\", \"url\": \"https://example.com/v1/videos/{{taskId}}\", \"statusPath\": \"data.status\", \"statusMap\": {\"queued\": \"QUEUED\", \"processing\": \"PROCESSING\", \"succeeded\": \"COMPLETED\", \"failed\": \"FAILED\"}, \"videoUrlPath\": \"data.video_url\"},\n" +
            "  \"models\": [{\"id\": \"seedance-2-0\", \"type\": \"video\"}]\n" +
            "}";

    @Test
    void all与byId读取合法文件(@TempDir Path tmp) throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        DescriptorSecretResolver secretResolver = mock(DescriptorSecretResolver.class);
        Files.writeString(tmp.resolve("demo.json"), String.format(DEMO_JSON_TEMPLATE, "演示"));

        ProviderDescriptorRegistry registry = new ProviderDescriptorRegistry(objectMapper, secretResolver, tmp.toString());

        assertThat(registry.all()).hasSize(1);
        assertThat(registry.byId("demo")).isPresent();
        assertThat(registry.byId("demo").get().getLabel()).isEqualTo("演示");
        assertThat(registry.byId("nope")).isEmpty();
    }

    @Test
    void reloadIfChanged检测到修改(@TempDir Path tmp) throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        DescriptorSecretResolver secretResolver = mock(DescriptorSecretResolver.class);
        Path file = tmp.resolve("demo.json");
        Files.writeString(file, String.format(DEMO_JSON_TEMPLATE, "旧标签"));

        ProviderDescriptorRegistry registry = new ProviderDescriptorRegistry(objectMapper, secretResolver, tmp.toString());
        assertThat(registry.all()).hasSize(1);
        assertThat(registry.byId("demo").get().getLabel()).isEqualTo("旧标签");

        Files.writeString(file, String.format(DEMO_JSON_TEMPLATE, "新标签"));
        Files.setLastModifiedTime(file, java.nio.file.attribute.FileTime.fromMillis(System.currentTimeMillis() + 2000));

        assertThat(registry.all()).hasSize(1);
        assertThat(registry.byId("demo").get().getLabel()).isEqualTo("新标签");
    }

    @Test
    void 非法JSON文件被跳过(@TempDir Path tmp) throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        DescriptorSecretResolver secretResolver = mock(DescriptorSecretResolver.class);
        Files.writeString(tmp.resolve("demo.json"), String.format(DEMO_JSON_TEMPLATE, "演示"));
        Files.writeString(tmp.resolve("bad.json"), "{not valid json");

        ProviderDescriptorRegistry registry = new ProviderDescriptorRegistry(objectMapper, secretResolver, tmp.toString());

        assertThat(registry.all()).hasSize(1);
    }

    @Test
    void buildProvider未知id抛异常(@TempDir Path tmp) throws Exception {
        ObjectMapper objectMapper = new ObjectMapper();
        DescriptorSecretResolver secretResolver = mock(DescriptorSecretResolver.class);
        Files.writeString(tmp.resolve("demo.json"), String.format(DEMO_JSON_TEMPLATE, "演示"));

        ProviderDescriptorRegistry registry = new ProviderDescriptorRegistry(objectMapper, secretResolver, tmp.toString());

        assertThatThrownBy(() -> registry.buildProvider("unknown"))
                .isInstanceOf(IllegalArgumentException.class);
    }
}

