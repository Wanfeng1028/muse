package com.dramaauth.controller;

import com.dramaauth.exception.ApiException;
import com.dramaauth.security.AuthInterceptor;
import com.dramaauth.service.BackupService;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.IOException;
import java.nio.file.Path;

/**
 * 管理员专用端点。
 *
 * <p>{@code /api/auth/admin/backup} 触发应用内在线备份：由持有库连接的应用进程执行 H2
 * {@code BACKUP TO}，实现无文件锁冲突的在线热备。</p>
 *
 * <p>鉴权：{@link com.dramaauth.security.WebMvcConfig} 的拦截器已覆盖 {@code /api/auth/**}
 * （{@code /api/auth/admin/**} 不在排除名单），因此请求会自动经过 JWT 鉴权，本类无需再配置。
 * 端点内额外校验 {@code ATTR_USER_ROLE} 必须为 {@code ADMIN}。</p>
 */
@RestController
@RequestMapping("/api/auth/admin")
public class AdminController {

    private final BackupService backupService;

    public AdminController(BackupService backupService) {
        this.backupService = backupService;
    }

    /**
     * 执行在线数据库备份并以附件形式返回备份 zip。
     *
     * @param request 当前请求，用于读取 JWT 鉴权阶段写入的角色属性
     * @return 备份 zip 文件流
     * @throws IOException 备份目录创建或文件读取失败
     */
    @PostMapping("/backup")
    public ResponseEntity<Resource> backup(HttpServletRequest request) throws IOException {
        Object role = request.getAttribute(AuthInterceptor.ATTR_USER_ROLE);
        if (!"ADMIN".equals(role)) {
            throw new ApiException(HttpStatus.FORBIDDEN, "FORBIDDEN", "仅管理员可备份");
        }

        Path zipPath = backupService.backup();
        Resource resource = new FileSystemResource(zipPath);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=\"auth-db-" + zipPath.getFileName() + "\"")
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(resource);
    }
}
