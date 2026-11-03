package com.scaffold.framework.datascope;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class DataScopeAspect {

    private final DataScopeResolver dataScopeResolver;

    public DataScopeAspect(DataScopeResolver dataScopeResolver) {
        this.dataScopeResolver = dataScopeResolver;
    }

    @Around("@annotation(com.scaffold.framework.datascope.DataScope) || @within(com.scaffold.framework.datascope.DataScope)")
    public Object applyDataScope(ProceedingJoinPoint joinPoint) throws Throwable {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        String username = authentication == null ? null : String.valueOf(authentication.getPrincipal());
        DataScopeContext.set(dataScopeResolver.resolve(username));
        try {
            return joinPoint.proceed();
        } finally {
            DataScopeContext.clear();
        }
    }
}
