package com.scaffold.framework.security;

import org.junit.jupiter.api.Test;

import java.security.SecureRandom;
import java.util.HexFormat;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class JwtServiceTest {

    @Test
    void rejectsMissingBlankAndShortSecretsAtConstruction() {
        for (String secret : new String[]{null, "", " ".repeat(32), randomSecret().substring(1)}) {
            assertThatThrownBy(() -> new JwtService(secret, 7200))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("JWT_SECRET");
        }
    }

    @Test
    void signsAndVerifiesTokensWithAMinimumLengthSecret() {
        JwtService service = new JwtService(randomSecret(), 7200);

        String token = service.generateToken(1L, "admin");

        assertThat(service.parseUsername(token)).isEqualTo("admin");
        assertThat(service.parseUsername("invalid-token")).isNull();
    }

    @Test
    void measuresSecretLengthInUtf8Bytes() {
        assertThatThrownBy(() -> new JwtService("密".repeat(10), 7200))
                .isInstanceOf(IllegalArgumentException.class);
        JwtService service = new JwtService("密".repeat(11), 7200);

        assertThat(service.parseUsername(service.generateToken(1L, "admin"))).isEqualTo("admin");
    }

    @Test
    void rejectsTokensSignedWithAnotherSecret() {
        JwtService signer = new JwtService(randomSecret(), 7200);
        JwtService verifier = new JwtService(randomSecret(), 7200);

        assertThat(verifier.parseUsername(signer.generateToken(1L, "admin"))).isNull();
    }

    private static String randomSecret() {
        byte[] bytes = new byte[16];
        new SecureRandom().nextBytes(bytes);
        return HexFormat.of().formatHex(bytes);
    }
}
