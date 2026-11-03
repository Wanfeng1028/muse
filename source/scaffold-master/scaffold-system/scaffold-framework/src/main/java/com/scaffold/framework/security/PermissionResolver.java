package com.scaffold.framework.security;

public interface PermissionResolver {

    boolean hasPermission(String username, String permission);
}
