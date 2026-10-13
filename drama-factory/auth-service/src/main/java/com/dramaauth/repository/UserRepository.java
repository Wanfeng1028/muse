package com.dramaauth.repository;

import com.dramaauth.model.User;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/** 用户仓储。 */
public interface UserRepository extends JpaRepository<User, Long> {

    Optional<User> findByEmail(String email);

    boolean existsByEmail(String email);

    long count();
}
