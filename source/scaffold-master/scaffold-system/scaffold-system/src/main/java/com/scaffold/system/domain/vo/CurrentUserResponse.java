package com.scaffold.system.domain.vo;

import java.util.List;

public record CurrentUserResponse(
        Long userId,
        String username,
        String nickname,
        Long deptId,
        String deptName,
        List<String> roles,
        List<String> permissions
) {
}
