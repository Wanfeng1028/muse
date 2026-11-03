package com.scaffold.framework.security;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class PermissionAspect {

    private final PermissionResolver permissionResolver;

    public PermissionAspect(PermissionResolver permissionResolver) {
        this.permissionResolver = permissionResolver;
    }

    @Around("@annotation(requiresPermission)")
    public Object checkPermission(ProceedingJoinPoint joinPoint, RequiresPermission requiresPermission) throws Throwable {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        String username = authentication == null ? null : String.valueOf(authentication.getPrincipal());
        if (username == null || !permissionResolver.hasPermission(username, requiresPermission.value())) {
            throw new AccessDeniedException("没有访问权限");
        }
        return joinPoint.proceed();
    }
}
