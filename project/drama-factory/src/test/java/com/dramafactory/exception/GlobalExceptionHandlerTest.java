package com.dramafactory.exception;

import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.lenient;
import static org.mockito.Mockito.when;

/**
 * GlobalExceptionHandler 内容协商测试：浏览器页面请求走友好错误页 forward，
 * API/JSON 请求走 JSON 错误体。
 */
@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerTest {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Mock
    private HttpServletRequest request;

    private NoResourceFoundException noResource() {
        return new NoResourceFoundException(HttpMethod.GET, "/missing-page");
    }

    @Test
    void noResourceHtmlRequestForwardsTo404Page() {
        when(request.getRequestURI()).thenReturn("/missing-page");
        when(request.getHeader("Accept")).thenReturn("text/html,application/xhtml+xml");

        Object result = handler.handleNoResource(noResource(), request);

        assertThat(result).isEqualTo("forward:/error/404.html");
    }

    @Test
    void noResourceJsonRequestReturns404Json() {
        when(request.getRequestURI()).thenReturn("/missing-page");
        when(request.getHeader("Accept")).thenReturn("application/json");

        Object result = handler.handleNoResource(noResource(), request);

        assertThat(result).isInstanceOf(ResponseEntity.class);
        ResponseEntity<?> entity = (ResponseEntity<?>) result;
        assertThat(entity.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void noResourceApiPathWithHtmlAcceptStillReturnsJson() {
        when(request.getRequestURI()).thenReturn("/api/missing");
        lenient().when(request.getHeader("Accept")).thenReturn("text/html");

        Object result = handler.handleNoResource(noResource(), request);

        assertThat(result).isInstanceOf(ResponseEntity.class);
        assertThat(((ResponseEntity<?>) result).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
    }

    @Test
    void genericHtmlRequestForwardsTo500Page() {
        when(request.getRequestURI()).thenReturn("/some-page");
        when(request.getHeader("Accept")).thenReturn("text/html");

        Object result = handler.handleGeneric(new RuntimeException("boom"), request);

        assertThat(result).isEqualTo("forward:/error/500.html");
    }

    @Test
    void genericJsonRequestReturns500Json() {
        when(request.getRequestURI()).thenReturn("/api/boom");
        lenient().when(request.getHeader("Accept")).thenReturn("application/json");

        Object result = handler.handleGeneric(new RuntimeException("boom"), request);

        assertThat(result).isInstanceOf(ResponseEntity.class);
        assertThat(((ResponseEntity<?>) result).getStatusCode()).isEqualTo(HttpStatus.INTERNAL_SERVER_ERROR);
    }
}
