package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;

class ProviderDescriptorRegistryReloadTest {

    private static final String ID = "prov-test";

    private ObjectMapper newMapper() {
        return new ObjectMapper();
    }

    private DescriptorSecretResolver newResolver() {
        return new DescriptorSecretResolver(null) {
            @Override
            public String resolve(String keyRef) {
                return "secret-value";
            }
        };
    }

    private String descriptorJson(int maxPromptChars) {
        return "{"
                + "\"id\":\"" + ID + "\","
                + "\"label\":\"test\","
                + "\"models\":[{\"id\":\"m1\",\"label\":\"m1\",\"type\":\"video\","
                + "\"constraints\":{\"maxPromptChars\":" + maxPromptChars + "}}],"
                + "\"submit\":{\"method\":\"POST\",\"url\":\"http://localhost:9999/v\","
                + "\"taskIdPath\":\"id\"},"
                + "\"poll\":{\"method\":\"GET\",\"url\":\"http://localhost:9999/s\","
                + "\"statusPath\":\"s\",\"statusMap\":{\"ok\":\"COMPLETED\"}}"
                + "}";
    }

    private void write(Path dir, String content) throws Exception {
        Files.writeString(dir.resolve(ID + ".json"), content);
    }

    private ProviderDescriptorRegistry newRegistry(Path dir) {
        return new ProviderDescriptorRegistry(newMapper(), newResolver(), dir.toString());
    }

    @Test
    void loadsDescriptorFromTempDir(@TempDir Path dir) throws Exception {
        write(dir, descriptorJson(100));
        ProviderDescriptorRegistry registry = newRegistry(dir);
        assertThat(registry.byId(ID)).isPresent();
    }

    @Test
    void loadedDescriptorHasMaxPromptChars100(@TempDir Path dir) throws Exception {
        write(dir, descriptorJson(100));
        ProviderDescriptorRegistry registry = newRegistry(dir);
        assertThat(registry.byId(ID).get().getModels().get(0).getConstraints().getMaxPromptChars()).isEqualTo(100);
    }

    @Test
    void reloadIfChangedPicksUpNewMaxPromptChars(@TempDir Path dir) throws Exception {
        write(dir, descriptorJson(100));
        ProviderDescriptorRegistry registry = newRegistry(dir);
        registry.byId(ID);
        Thread.sleep(20);
        write(dir, descriptorJson(200));
        registry.reloadIfChanged();
        assertThat(registry.byId(ID).get().getModels().get(0).getConstraints().getMaxPromptChars()).isEqualTo(200);
    }

    @Test
    void invalidJsonKeepsOldMaxPromptChars(@TempDir Path dir) throws Exception {
        write(dir, descriptorJson(100));
        ProviderDescriptorRegistry registry = newRegistry(dir);
        registry.byId(ID);
        Thread.sleep(20);
        write(dir, "{ this is not json ");
        registry.reloadIfChanged();
        assertThat(registry.byId(ID).get().getModels().get(0).getConstraints().getMaxPromptChars()).isEqualTo(100);
    }

    @Test
    void invalidJsonDoesNotThrowOnReload(@TempDir Path dir) throws Exception {
        write(dir, descriptorJson(100));
        ProviderDescriptorRegistry registry = newRegistry(dir);
        registry.byId(ID);
        Thread.sleep(20);
        write(dir, "{ this is not json ");
        registry.reloadIfChanged();
        assertThat(true).isTrue();
    }

    @Test
    void missingDirYieldsEmptyResult(@TempDir Path dir) {
        ProviderDescriptorRegistry registry = newRegistry(dir.resolve("nope"));
        Optional<ProviderDescriptor> found = registry.byId(ID);
        assertThat(found).isEmpty();
    }
}
