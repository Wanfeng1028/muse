package com.dramafactory.service.video;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Paths;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatCode;

class ToonflowDescriptorValidationTest {

    @Test
    void toonflowDescriptorsPassValidation() throws Exception {
        String[] names = {
                "toonflow-compshare.json",
                "toonflow-apimart.json",
                "toonflow-metaso.json",
                "toonflow-tfrouter.json"
        };
        ObjectMapper mapper = new ObjectMapper();
        for (String name : names) {
            ProviderDescriptor d = mapper.readValue(
                    Paths.get("docs/samples/providers", name).toFile(),
                    ProviderDescriptor.class);
            assertThatCode(d::validate).doesNotThrowAnyException();
            assertThat(d.getId()).startsWith("toonflow-");
            assertThat(d.getModels()).anySatisfy(m ->
                    assertThat(m.getType()).isEqualTo("video"));
        }
    }
}
