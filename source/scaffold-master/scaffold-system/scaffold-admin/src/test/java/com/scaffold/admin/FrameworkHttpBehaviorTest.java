package com.scaffold.admin;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = { ScaffoldAdminApplication.class, TestSecurityConfig.class },
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class FrameworkHttpBehaviorTest {

    private static final ParameterizedTypeReference<Map<String, Object>> MAP_TYPE = new ParameterizedTypeReference<>() {
    };

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void responseContainsTraceIdInHeaderAndBody() {
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/health",
                HttpMethod.GET,
                null,
                MAP_TYPE
        );

        String headerTraceId = response.getHeaders().getFirst("X-Trace-Id");

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(headerTraceId).isNotBlank();
        assertThat(response.getBody()).containsEntry("traceId", headerTraceId);
    }

    @Test
    void businessExceptionReturnsUnifiedErrorResponse() {
        ResponseEntity<Map<String, Object>> response = restTemplate.exchange(
                "/api/test/business-error",
                HttpMethod.GET,
                null,
                MAP_TYPE
        );

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.BAD_REQUEST);
        assertThat(response.getBody()).containsEntry("code", 400);
        assertThat(response.getBody()).containsEntry("message", "业务规则不允许该操作");
        assertThat(response.getBody().get("traceId")).isNotNull();
    }
}
