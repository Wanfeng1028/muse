package com.dramaauth.repository;

import com.dramaauth.model.UserSession;
import org.springframework.data.jpa.repository.JpaRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Optional;

/** 会话仓储。 */
public interface SessionRepository extends JpaRepository<UserSession, Long> {

    Optional<UserSession> findByTokenJti(String tokenJti);

    Optional<UserSession> findByAccessJti(String accessJti);

    List<UserSession> findByUserIdOrderByCreatedAtDesc(Long userId);

    List<UserSession> findByUserIdAndRevokedFalse(Long userId);

long countByRevokedFalseAndExpiresAtAfter(LocalDateTime expiresAt);
}
