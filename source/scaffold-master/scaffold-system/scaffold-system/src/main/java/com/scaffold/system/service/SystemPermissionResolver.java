package com.scaffold.system.service;

import com.scaffold.framework.security.PermissionResolver;
import com.scaffold.system.mapper.AuthMapper;
import org.springframework.stereotype.Service;

@Service
public class SystemPermissionResolver implements PermissionResolver {

    private static final String SUPER_ADMIN = "super_admin";

    private final AuthMapper authMapper;

    public SystemPermissionResolver(AuthMapper authMapper) {
        this.authMapper = authMapper;
    }

    @Override
    public boolean hasPermission(String username, String permission) {
        var user = authMapper.selectUserByUsername(username);
        if (user == null || user.getStatus() == null || user.getStatus() != 1) {
            return false;
        }
        if (authMapper.selectRoleCodes(user.getId()).contains(SUPER_ADMIN)) {
            return true;
        }
        return authMapper.selectPermissions(user.getId()).contains(permission);
    }
}
