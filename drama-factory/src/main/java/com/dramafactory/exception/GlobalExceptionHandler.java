package com.dramafactory.exception;

import com.dramafactory.dto.Records;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseBody;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.dao.DataIntegrityViolationException;

import java.time.LocalDateTime;
import java.util.LinkedHashMap;
import java.util.Map;

@ControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleNotFound(ResourceNotFoundException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.NOT_FOUND.value(),
                "Not Found",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(ForbiddenException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleForbidden(ForbiddenException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.FORBIDDEN.value(),
                "Forbidden",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.FORBIDDEN).body(body);
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {
        String message = "Validation failed";
        FieldError fieldError = ex.getBindingResult().getFieldError();
        if (fieldError != null && fieldError.getDefaultMessage() != null) {
            message = fieldError.getDefaultMessage();
        }
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.BAD_REQUEST.value(),
                "Bad Request",
                message,
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleTypeMismatch(MethodArgumentTypeMismatchException ex) {
        String message = "参数类型错误：" + ex.getName() + " 应为 " +
                (ex.getRequiredType() == null ? "合法值" : ex.getRequiredType().getSimpleName()) + " 类型";
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.BAD_REQUEST.value(),
                "Bad Request",
                message,
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    @ExceptionHandler(MissingServletRequestParameterException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleMissingParam(MissingServletRequestParameterException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.BAD_REQUEST.value(),
                "Bad Request",
                "缺少必填参数：" + ex.getParameterName(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleIllegalArgument(IllegalArgumentException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.BAD_REQUEST.value(),
                "Bad Request",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    @ExceptionHandler(IllegalStateException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleIllegalState(IllegalStateException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.CONFLICT.value(),
                "Conflict",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    @ExceptionHandler(ReviewConflictException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleReviewConflict(ReviewConflictException ex) {
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.CONFLICT.value(),
                "Conflict",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    @ResponseBody
    public ResponseEntity<Records.ErrorResponse> handleDataIntegrityViolation(DataIntegrityViolationException ex) {
        String message = "数据完整性校验失败";
        Throwable root = ex.getRootCause();
        if (root != null && root.getMessage() != null) {
            String rm = root.getMessage();
            message = rm.length() > 200 ? rm.substring(0, 200) : rm;
        }
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.BAD_REQUEST.value(),
                "Bad Request",
                message,
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    @ExceptionHandler(CanvasConflictException.class)
    @ResponseBody
    public ResponseEntity<Map<String, Object>> handleCanvasConflict(CanvasConflictException ex) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", HttpStatus.CONFLICT.value());
        body.put("error", "Conflict");
        body.put("message", ex.getMessage());
        body.put("current_version", ex.getCurrentVersion());
        body.put("updated_by", ex.getUpdatedBy());
        body.put("timestamp", LocalDateTime.now());
        body.put("requestId", MDC.get("request_id"));
        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }

    @ExceptionHandler(NoResourceFoundException.class)
    public Object handleNoResource(NoResourceFoundException ex, HttpServletRequest req) {
        if (wantsHtml(req)) {
            return "forward:/error/404.html";
        }
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.NOT_FOUND.value(),
                "Not Found",
                ex.getMessage(),
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(body);
    }

    @ExceptionHandler(Exception.class)
    public Object handleGeneric(Exception ex, HttpServletRequest req) {
        if (wantsHtml(req)) {
            return "forward:/error/500.html";
        }
        String message = ex.getMessage();
        if (message == null || message.isBlank()) {
            message = ex.getClass().getSimpleName();
        }
        Records.ErrorResponse body = new Records.ErrorResponse(
                HttpStatus.INTERNAL_SERVER_ERROR.value(),
                "Internal Server Error",
                message,
                LocalDateTime.now(),
                MDC.get("request_id")
        );
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR).body(body);
    }

    private boolean wantsHtml(HttpServletRequest req) {
        String uri = req.getRequestURI();
        if (uri != null && uri.startsWith("/api/")) return false;
        String accept = req.getHeader("Accept");
        return accept != null && accept.contains("text/html");
    }
}

