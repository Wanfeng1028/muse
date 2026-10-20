package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

import static org.assertj.core.api.Assertions.assertThat;

class ToonflowCanonicalTest {

    private static final Path PROVIDER_DIRECTORY = Paths.get("data", "providers");

    private final ObjectMapper objectMapper = new ObjectMapper();

    private List<ProviderDescriptor> providers;

    @BeforeEach
    void loadProviders() throws IOException {
        try (Stream<Path> files = Files.list(PROVIDER_DIRECTORY)) {
            providers = files
                    .filter(Files::isRegularFile)
                    .filter(path -> path.getFileName().toString().endsWith(".json"))
                    .sorted(Comparator.comparing(path -> path.getFileName().toString()))
                    .map(this::readProvider)
                    .collect(Collectors.toList());
        }

        assertThat(providers).hasSize(4);
    }

    private ProviderDescriptor readProvider(Path path) {
        try {
            return objectMapper.readValue(path.toFile(), ProviderDescriptor.class);
        } catch (IOException exception) {
            throw new UncheckedIOException(exception);
        }
    }

    @Test
    void everyModelHasCanonical() {
        assertThat(providers).isNotEmpty();

        providers.forEach(provider -> provider.getModels().forEach(model ->
                assertThat(model.getCanonical()).isNotNull().isNotEmpty()
        ));
    }

    @Test
    void everyCanonicalUsesKebabCasePattern() {
        providers.forEach(provider -> provider.getModels().forEach(model ->
                assertThat(model.getCanonical()).matches("^[a-z0-9]+(-[a-z0-9.]+)*$")
        ));
    }

    @Test
    void apimartAndTfrouterShareSeedanceCanonicals() {
        Set<String> apimartCanonicals = canonicalSetFor("toonflow-apimart");
        Set<String> tfrouterCanonicals = canonicalSetFor("toonflow-tfrouter");

        Set<String> intersection = new HashSet<>(apimartCanonicals);
        intersection.retainAll(tfrouterCanonicals);

        assertThat(intersection).contains("seedance-2.5", "seedance-2.0");
    }

    @Test
    void tfrouterSeedanceCanonicalKeepsOriginalModelId() {
        List<String> ids = providerById("toonflow-tfrouter").getModels().stream()
                .filter(model -> "seedance-2.5".equals(model.getCanonical()))
                .map(model -> model.getId())
                .collect(Collectors.toList());

        assertThat(ids).containsExactly("Seedance 2.5");
    }

    private ProviderDescriptor providerById(String id) {
        return providers.stream()
                .filter(provider -> id.equals(provider.getId()))
                .findFirst()
                .orElseThrow(() -> new AssertionError("Provider not found: " + id));
    }

    private Set<String> canonicalSetFor(String providerId) {
        return providerById(providerId).getModels().stream()
                .map(model -> model.getCanonical())
                .collect(Collectors.toSet());
    }
}
