package com.dramaauth.service;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * 数据库在线热备份服务。
 *
 * <p>H2 嵌入式文件库对库文件持有独占文件锁，独立 JVM 进程无法在应用运行时打开同一库文件执行
 * {@code BACKUP TO}（会报 {@code Database may be already in use}）。因此备份必须由持有库连接的
 * 应用进程自己执行，即本服务通过注入的 {@link JdbcTemplate} 在应用内发起 {@code BACKUP TO}，
 * 实现真正的在线热备，无文件锁冲突。</p>
 *
 * <p>安全：{@code BACKUP TO} 的目标路径完全由服务端生成（固定目录 {@code ./data/backups} +
 * 时间戳文件名），绝不接受客户端传入路径，防止路径穿越。</p>
 */
@Service
public class BackupService {

    private static final DateTimeFormatter TS_FORMAT = DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss");

    private final JdbcTemplate jdbcTemplate;

    public BackupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    /**
     * 执行在线热备份。
     *
     * <p>备份目录固定为 {@code ./data/backups}（相对工作目录），不存在则创建；文件名由服务端
     * 按时间戳生成，形如 {@code db-20250101-120000.zip}。随后通过 JDBC 连接执行 H2 的
     * {@code BACKUP TO '<abs zip path>'}，由应用进程自身完成备份，避免文件锁冲突。</p>
     *
     * @return 生成的备份 zip 文件路径
     * @throws IOException 创建备份目录失败时抛出
     */
    public Path backup() throws IOException {
        Path backupDir = Paths.get("data", "backups");
        if (!Files.exists(backupDir)) {
            Files.createDirectories(backupDir);
        }

        String timestamp = LocalDateTime.now().format(TS_FORMAT);
        Path zipPath = backupDir.resolve("db-" + timestamp + ".zip");

        jdbcTemplate.execute("BACKUP TO '" + zipPath.toAbsolutePath() + "'");

        return zipPath;
    }
}
