package com.scaffold.system.mapper;

import com.scaffold.system.domain.AuthUserRow;
import com.scaffold.system.domain.MenuRow;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;

@Mapper
public interface AuthMapper {

    @Select("""
            SELECT u.id, u.username, u.password, u.nickname, u.status, u.dept_id, d.dept_name
            FROM sys_user u
            LEFT JOIN sys_dept d ON d.id = u.dept_id
            WHERE u.username = #{username} AND u.deleted = 0
            LIMIT 1
            """)
    AuthUserRow selectUserByUsername(@Param("username") String username);

    @Select("""
            SELECT r.role_code
            FROM sys_user_role ur
            JOIN sys_role r ON r.id = ur.role_id
            WHERE ur.user_id = #{userId} AND r.status = 1 AND r.deleted = 0
            ORDER BY r.sort, r.id
            """)
    List<String> selectRoleCodes(@Param("userId") Long userId);

    @Select("""
            SELECT DISTINCT m.permission
            FROM sys_user_role ur
            JOIN sys_role r ON r.id = ur.role_id AND r.status = 1 AND r.deleted = 0
            JOIN sys_role_menu rm ON rm.role_id = ur.role_id
            JOIN sys_menu m ON m.id = rm.menu_id
            WHERE ur.user_id = #{userId}
              AND m.status = 1
              AND m.permission IS NOT NULL
              AND m.permission <> ''
            ORDER BY m.permission
            """)
    List<String> selectPermissions(@Param("userId") Long userId);

    @Select("""
            SELECT DISTINCT m.id, m.parent_id, m.menu_name, m.menu_type, m.icon, m.path,
                   m.component, m.permission, m.sort
            FROM sys_user_role ur
            JOIN sys_role r ON r.id = ur.role_id AND r.status = 1 AND r.deleted = 0
            JOIN sys_role_menu rm ON rm.role_id = ur.role_id
            JOIN sys_menu m ON m.id = rm.menu_id
            WHERE ur.user_id = #{userId}
              AND m.status = 1
              AND m.visible = 1
              AND m.menu_type IN ('dir', 'menu')
            ORDER BY m.parent_id, m.sort, m.id
            """)
    List<MenuRow> selectRouteMenus(@Param("userId") Long userId);

    /** 超级管理员：全部启用的权限码 */
    @Select("""
            SELECT DISTINCT permission
            FROM sys_menu
            WHERE status = 1 AND permission IS NOT NULL AND permission <> ''
            ORDER BY permission
            """)
    List<String> selectAllPermissions();

    /** 超级管理员：全部启用且可见的目录与菜单 */
    @Select("""
            SELECT id, parent_id, menu_name, menu_type, icon, path, component, permission, sort
            FROM sys_menu
            WHERE status = 1 AND visible = 1 AND menu_type IN ('dir', 'menu')
            ORDER BY parent_id, sort, id
            """)
    List<MenuRow> selectAllRouteMenus();

    @Insert("""
            INSERT INTO sys_login_log (username, status, msg, login_time)
            VALUES (#{username}, #{status}, #{msg}, NOW())
            """)
    void insertLoginLog(@Param("username") String username, @Param("status") int status, @Param("msg") String msg);

    /** 登录成功后记录最近登录时间（sys_user.last_login_time），用户列表与看板据此展示 */
    @Update("UPDATE sys_user SET last_login_time = NOW() WHERE id = #{userId} AND deleted = 0")
    void updateLastLoginTime(@Param("userId") Long userId);

    @Update("""
            UPDATE sys_user
            SET password = #{password}, update_by = #{username}, update_time = NOW()
            WHERE id = #{userId} AND deleted = 0
            """)
    int updatePassword(@Param("userId") Long userId, @Param("username") String username, @Param("password") String password);
}
