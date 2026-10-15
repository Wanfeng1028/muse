package com.dramaauth.metrics;

import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
@TestPropertySource(properties = {
        "AUTH_JWT_SECRET=dummy-metrics-test-secret-0123456789abcdef",
        "spring.datasource.url=jdbc:h2:mem:authmetricstest;DB_CLOSE_DELAY=-1",
        "spring.jpa.hibernate.ddl-auto=create-drop"
})
class AuthMetricsTest {

    @Autowired
    private AuthMetrics metrics;

    @Autowired
    private MeterRegistry registry;

    @Autowired
    private com.dramaauth.repository.UserRepository userRepository;

    @Test
    void registrationCounterIncrements() {
        double before = registry.get("dramaauth_registrations_total").counter().count();
        metrics.recordRegistration();
        assertEquals(before + 1.0, registry.get("dramaauth_registrations_total").counter().count(), 0.0001);
    }

    @Test
    void loginCountersTaggedByResult() {
        metrics.recordLogin(true);
        metrics.recordLogin(false);
        assertEquals(1.0, registry.get("dramaauth_logins_total").tag("result", "success").counter().count(), 0.0001);
        assertEquals(1.0, registry.get("dramaauth_logins_total").tag("result", "failure").counter().count(), 0.0001);
    }

    @Test
    void oauthCallbackCounterTaggedByProviderAndResult() {
        metrics.recordOAuthCallback("github", true);
        assertEquals(1.0, registry.get("dramaauth_oauth_callbacks_total")
                .tag("provider", "github")
                .tag("result", "success")
                .counter()
                .count(), 0.0001);
    }

    @Test
    void refreshUpdatesUserGaugeFromRepository() {
        com.dramaauth.model.User u = new com.dramaauth.model.User();
        u.setEmail("metrics-gauge@example.com");
        u.setPasswordHash("x");
        u.setNickname("gauge");
        u.setRole("USER");
        userRepository.save(u);
        metrics.refresh();
        assertTrue(registry.get("dramaauth_users_total").gauge().value() >= 1.0);
    }
}
