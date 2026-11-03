package com.dramafactory.exception;

import com.dramafactory.dto.Records;
import jakarta.servlet.http.HttpServletRequest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class GlobalExceptionHandlerDeepTestR4 {

    private final GlobalExceptionHandler handler = new GlobalExceptionHandler();

    @Mock
    private HttpServletRequest request;

    @Test
    void handleNotFound_returns404WithBody() {
        ResourceNotFoundException ex = new ResourceNotFoundException("Shot", 7L);
        ResponseEntity<Records.ErrorResponse> response = handler.handleNotFound(ex);
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(404, body.status());
        assertEquals("Not Found", body.error());
        assertNotNull(body.message());
        org.junit.jupiter.api.Assertions.assertTrue(body.message().contains("Shot"));
    }

    @Test
    void handleNotFound_messageUsesExceptionMessage() {
        ResourceNotFoundException ex = new ResourceNotFoundException("Shot", 7L);
        ResponseEntity<Records.ErrorResponse> response = handler.handleNotFound(ex);
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals("Shot not found: 7", body.message());
    }

    @Test
    void handleForbidden_returns403() {
        ForbiddenException ex = new ForbiddenException("Project", 3L);
        ResponseEntity<Records.ErrorResponse> response = handler.handleForbidden(ex);
        assertEquals(HttpStatus.FORBIDDEN, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(403, body.status());
        assertEquals("Forbidden", body.error());
    }

    @Test
    void handleIllegalArgument_returns400() {
        IllegalArgumentException ex = new IllegalArgumentException("ids 不能为空");
        ResponseEntity<Records.ErrorResponse> response = handler.handleIllegalArgument(ex);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(400, body.status());
        assertEquals("ids 不能为空", body.message());
    }

    @Test
    void handleIllegalState_returns409() {
        IllegalStateException ex = new IllegalStateException("状态不允许");
        ResponseEntity<Records.ErrorResponse> response = handler.handleIllegalState(ex);
        assertEquals(HttpStatus.CONFLICT, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(409, body.status());
        assertEquals("Conflict", body.error());
    }

    @Test
    void handleMissingParam_returns400中文消息() throws Exception {
        MissingServletRequestParameterException ex =
                new MissingServletRequestParameterException("episodeId", "Long");
        ResponseEntity<Records.ErrorResponse> response = handler.handleMissingParam(ex);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(400, body.status());
        assertEquals("缺少必填参数：episodeId", body.message());
    }

    @Test
    void handleDataIntegrityViolation_noRootCause_defaultMessage() {
        DataIntegrityViolationException ex = new DataIntegrityViolationException("dup", null);
        ResponseEntity<Records.ErrorResponse> response = handler.handleDataIntegrityViolation(ex);
        assertEquals(HttpStatus.BAD_REQUEST, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(400, body.status());
        assertEquals("数据完整性校验失败", body.message());
    }

    @Test
    void handleDataIntegrityViolation_longRootCause_truncated200() {
        String longMsg = "x".repeat(300);
        DataIntegrityViolationException ex =
                new DataIntegrityViolationException("outer", new RuntimeException(longMsg));
        ResponseEntity<Records.ErrorResponse> response = handler.handleDataIntegrityViolation(ex);
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals(200, body.message().length());
    }

    @Test
    void handleDataIntegrityViolation_shortRootCause_fullMessage() {
        DataIntegrityViolationException ex =
                new DataIntegrityViolationException("outer", new RuntimeException("唯一键冲突"));
        ResponseEntity<Records.ErrorResponse> response = handler.handleDataIntegrityViolation(ex);
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals("唯一键冲突", body.message());
    }

    @Test
    void handleCanvasConflict_returns409Map() {
        CanvasConflictException ex = new CanvasConflictException(5, "alice");
        ResponseEntity<Map<String, Object>> response = handler.handleCanvasConflict(ex);
        assertEquals(HttpStatus.CONFLICT, response.getStatusCode());
        Map<String, Object> body = response.getBody();
        assertNotNull(body);
        assertEquals(409, body.get("status"));
        assertEquals(5, body.get("current_version"));
        assertEquals("alice", body.get("updated_by"));
        assertEquals("Conflict", body.get("error"));
    }

    @Test
    void handleGeneric_nullMessage_usesClassName() {
        when(request.getRequestURI()).thenReturn("/api/x");
        RuntimeException ex = new RuntimeException((String) null);
        Object result = handler.handleGeneric(ex, request);
        assertInstanceOf(ResponseEntity.class, result);
        @SuppressWarnings("unchecked")
        ResponseEntity<Records.ErrorResponse> response = (ResponseEntity<Records.ErrorResponse>) result;
        assertEquals(HttpStatus.INTERNAL_SERVER_ERROR, response.getStatusCode());
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals("RuntimeException", body.message());
    }

    @Test
    void handleGeneric_blankMessage_usesClassName() {
        when(request.getRequestURI()).thenReturn("/api/x");
        RuntimeException ex = new RuntimeException("  ");
        Object result = handler.handleGeneric(ex, request);
        assertInstanceOf(ResponseEntity.class, result);
        @SuppressWarnings("unchecked")
        ResponseEntity<Records.ErrorResponse> response = (ResponseEntity<Records.ErrorResponse>) result;
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals("RuntimeException", body.message());
    }

    @Test
    void handleGeneric_normalMessage() {
        when(request.getRequestURI()).thenReturn("/api/x");
        RuntimeException ex = new RuntimeException("boom");
        Object result = handler.handleGeneric(ex, request);
        assertInstanceOf(ResponseEntity.class, result);
        @SuppressWarnings("unchecked")
        ResponseEntity<Records.ErrorResponse> response = (ResponseEntity<Records.ErrorResponse>) result;
        Records.ErrorResponse body = response.getBody();
        assertNotNull(body);
        assertEquals("boom", body.message());
        assertEquals("Internal Server Error", body.error());
    }

    @Test
    void handleNoResource_apiPath_returnsJsonNotForward() throws Exception {
        when(request.getRequestURI()).thenReturn("/api/missing");
        NoResourceFoundException ex = new NoResourceFoundException(
                org.springframework.http.HttpMethod.GET, "/api/missing");
        Object result = handler.handleNoResource(ex, request);
        assertInstanceOf(ResponseEntity.class, result);
        @SuppressWarnings("unchecked")
        ResponseEntity<Records.ErrorResponse> response = (ResponseEntity<Records.ErrorResponse>) result;
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }

    @Test
    void handleNoResource_nonApiNoAccept_returnsJson() throws Exception {
        when(request.getRequestURI()).thenReturn("/page");
        when(request.getHeader("Accept")).thenReturn(null);
        NoResourceFoundException ex = new NoResourceFoundException(
                org.springframework.http.HttpMethod.GET, "/page");
        Object result = handler.handleNoResource(ex, request);
        assertInstanceOf(ResponseEntity.class, result);
        @SuppressWarnings("unchecked")
        ResponseEntity<Records.ErrorResponse> response = (ResponseEntity<Records.ErrorResponse>) result;
        assertEquals(HttpStatus.NOT_FOUND, response.getStatusCode());
    }
}