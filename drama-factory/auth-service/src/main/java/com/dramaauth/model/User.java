package com.dramaauth.model;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;

import java.time.LocalDateTime;

/**
 * 用户实体。
 * 密码只存 PBKDF2-HMAC-SHA256 hash（离线仓库无 BCrypt，采用 OWASP 推荐参数的等价方案），永不存明文。
 */
@Entity
@Table(name = "users")
public class User {

    /** 主键 */
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    /** 登录邮箱，唯一 */
    @Column(nullable = false, unique = true, length = 255)
    private String email;

    /** 密码 hash，OAuth 纯用户可空 */
    @Column(name = "password_hash", length = 255)
    private String passwordHash;

    /** 昵称 */
    @Column(nullable = false, length = 64)
    private String nickname;

    /** 头像 URL，可空（默认几何/插画头像，禁字母头像） */
    @Column(name = "avatar_url", length = 512)
    private String avatarUrl;

    /** 角色：USER/ADMIN，首个注册用户为 ADMIN */
    @Column(nullable = false, length = 16)
    private String role = "USER";

    /** 状态：ACTIVE/DISABLED */
    @Column(nullable = false, length = 16)
    private String status = "ACTIVE";

    @Column(name = "created_at")
    private LocalDateTime createdAt;

    @Column(name = "updated_at")
    private LocalDateTime updatedAt;

    @PrePersist
    void onCreate() {
        createdAt = LocalDateTime.now();
        updatedAt = createdAt;
    }

    @PreUpdate
    void onUpdate() {
        updatedAt = LocalDateTime.now();
    }

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPasswordHash() { return passwordHash; }
    public void setPasswordHash(String passwordHash) { this.passwordHash = passwordHash; }
    public String getNickname() { return nickname; }
    public void setNickname(String nickname) { this.nickname = nickname; }
    public String getAvatarUrl() { return avatarUrl; }
    public void setAvatarUrl(String avatarUrl) { this.avatarUrl = avatarUrl; }
    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
    public String getStatus() { return status; }
    public void setStatus(String status) { this.status = status; }
    public LocalDateTime getCreatedAt() { return createdAt; }
    public LocalDateTime getUpdatedAt() { return updatedAt; }
}
