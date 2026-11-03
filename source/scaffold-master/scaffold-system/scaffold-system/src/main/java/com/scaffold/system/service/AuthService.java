package com.scaffold.system.service;

import com.scaffold.common.exception.BusinessException;
import com.scaffold.framework.security.JwtService;
import com.scaffold.framework.security.TokenStore;
import com.scaffold.system.domain.AuthUserRow;
import com.scaffold.system.domain.MenuRow;
import com.scaffold.system.domain.dto.ChangePasswordRequest;
import com.scaffold.system.domain.dto.LoginRequest;
import com.scaffold.system.domain.vo.CurrentUserResponse;
import com.scaffold.system.domain.vo.LoginResponse;
import com.scaffold.system.domain.vo.RouteVO;
import com.scaffold.system.mapper.AuthMapper;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class AuthService {

    private static final String SUPER_ADMIN = "super_admin";

    private final AuthMapper authMapper;
    private final PasswordEncoder passwordEncoder;
    private final JwtService jwtService;
    private final TokenStore tokenStore;

    public AuthService(AuthMapper authMapper, PasswordEncoder passwordEncoder, JwtService jwtService, TokenStore tokenStore) {
        this.authMapper = authMapper;
        this.passwordEncoder = passwordEncoder;
        this.jwtService = jwtService;
        this.tokenStore = tokenStore;
    }

    public LoginResponse login(LoginRequest request) {
        AuthUserRow user = authMapper.selectUserByUsername(request.getUsername());
        if (user == null || !passwordEncoder.matches(request.getPassword(), user.getPassword())) {
            authMapper.insertLoginLog(request.getUsername(), 0, "账号或密码错误");
            throw new BusinessException("账号或密码错误");
        }
        if (user.getStatus() == null || user.getStatus() != 1) {
            authMapper.insertLoginLog(request.getUsername(), 0, "账号已停用");
            throw new BusinessException("账号已停用");
        }
        String token = jwtService.generateToken(user.getId(), user.getUsername());
        tokenStore.store(token, user.getUsername(), jwtService.expiresSeconds());
        authMapper.insertLoginLog(user.getUsername(), 1, "登录成功");
        authMapper.updateLastLoginTime(user.getId());
        return new LoginResponse(token, jwtService.expiresSeconds());
    }

    public void logout() {
        Authentication authentication = SecurityContextHolder.getContext().getAuthentication();
        if (authentication != null && authentication.getCredentials() instanceof String token) {
            tokenStore.revoke(token);
            authMapper.insertLoginLog(String.valueOf(authentication.getPrincipal()), 1, "退出登录");
        }
        SecurityContextHolder.clearContext();
    }

    public CurrentUserResponse currentUser() {
        AuthUserRow user = currentUserRow();
        List<String> roleCodes = authMapper.selectRoleCodes(user.getId());
        return new CurrentUserResponse(
                user.getId(),
                user.getUsername(),
                user.getNickname(),
                user.getDeptId(),
                user.getDeptName(),
                roleCodes,
                roleCodes.contains(SUPER_ADMIN) ? authMapper.selectAllPermissions() : authMapper.selectPermissions(user.getId())
        );
    }

    public Map<String, Object> routes() {
        AuthUserRow user = currentUserRow();
        // 超级管理员不受角色菜单分配限制，新增菜单无需再授权即可见
        List<MenuRow> menus = authMapper.selectRoleCodes(user.getId()).contains(SUPER_ADMIN)
                ? authMapper.selectAllRouteMenus()
                : authMapper.selectRouteMenus(user.getId());
        return Map.of("routes", buildRoutes(menus));
    }

    public void changePassword(ChangePasswordRequest request) {
        AuthUserRow user = currentUserRow();
        if (!passwordEncoder.matches(request.getOldPassword(), user.getPassword())) {
            throw new BusinessException("旧密码不正确");
        }
        if (passwordEncoder.matches(request.getNewPassword(), user.getPassword())) {
            throw new BusinessException("新密码不能与旧密码一致");
        }
        int updated = authMapper.updatePassword(user.getId(), user.getUsername(), passwordEncoder.encode(request.getNewPassword()));
        if (updated == 0) {
            throw new BusinessException("密码修改失败");
        }
    }

    private AuthUserRow currentUserRow() {
        String username = String.valueOf(SecurityContextHolder.getContext().getAuthentication().getPrincipal());
        AuthUserRow user = authMapper.selectUserByUsername(username);
        if (user == null || user.getStatus() == null || user.getStatus() != 1) {
            throw new BusinessException(401, "未认证或登录已过期");
        }
        return user;
    }

    private List<RouteVO> buildRoutes(List<MenuRow> menus) {
        Map<Long, RouteVO> byId = new LinkedHashMap<>();
        menus.stream()
                .sorted(Comparator.comparing(MenuRow::getParentId).thenComparing(MenuRow::getSort).thenComparing(MenuRow::getId))
                .forEach(menu -> byId.put(menu.getId(), toRoute(menu)));
        List<RouteVO> roots = new ArrayList<>();
        for (RouteVO route : byId.values()) {
            RouteVO parent = byId.get(route.getParentId());
            if (parent == null) {
                roots.add(route);
            } else {
                parent.getChildren().add(route);
            }
        }
        return roots;
    }

    private RouteVO toRoute(MenuRow menu) {
        RouteVO route = new RouteVO();
        route.setId(menu.getId());
        route.setParentId(menu.getParentId());
        route.setName(menu.getMenuName());
        route.setPath(menu.getPath());
        route.setComponent(menu.getComponent());
        route.setIcon(menu.getIcon());
        route.setPermission(menu.getPermission());
        return route;
    }
}
