package com.scaffold.system.mapper;

import com.scaffold.framework.datascope.DataScopeCriteria;
import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Delete;
import org.apache.ibatis.annotations.Insert;
import org.apache.ibatis.annotations.Options;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;
import org.apache.ibatis.annotations.Update;

import java.util.List;
import java.util.Map;

@Mapper
public interface SystemManagementMapper {

    @Select("""
            <script>
            SELECT COUNT(DISTINCT u.id)
            FROM sys_user u
            LEFT JOIN sys_dept d ON d.id = u.dept_id
            WHERE u.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR u.username LIKE CONCAT('%', #{keyword}, '%')
                   OR u.nickname LIKE CONCAT('%', #{keyword}, '%')
                   OR u.phone LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR u.status = #{status})
              AND (#{deptId} IS NULL OR u.dept_id IN (SELECT sd.id FROM sys_dept sd WHERE sd.id = #{deptId} OR FIND_IN_SET(#{deptId}, sd.ancestors)))
              AND (#{postId} IS NULL OR EXISTS (SELECT 1 FROM sys_user_post fup WHERE fup.user_id = u.id AND fup.post_id = #{postId}))
              AND (
                  #{scope.allScope} = TRUE
                  OR u.id = #{scope.userId}
                  <if test="scope.deptIds != null and scope.deptIds.size > 0">
                  OR u.dept_id IN
                  <foreach collection="scope.deptIds" item="scopeDeptId" open="(" separator="," close=")">
                      #{scopeDeptId}
                  </foreach>
                  </if>
              )
            </script>
            """)
    long countUsers(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("deptId") Long deptId,
            @Param("postId") Long postId,
            @Param("scope") DataScopeCriteria scope
    );

    @Select("""
            <script>
            SELECT u.id,
                   u.username,
                   u.nickname,
                   u.phone,
                   u.email,
                   d.dept_name AS deptName,
                   COALESCE(GROUP_CONCAT(DISTINCT p.post_name ORDER BY p.sort, p.id SEPARATOR ','), '') AS postName,
                   COALESCE(GROUP_CONCAT(DISTINCT r.role_name ORDER BY r.sort, r.id SEPARATOR ','), '') AS roleName,
                   u.status,
                   DATE_FORMAT(u.create_time, '%Y-%m-%d %H:%i') AS createTime,
                   DATE_FORMAT(u.last_login_time, '%Y-%m-%d %H:%i') AS lastLogin
            FROM sys_user u
            LEFT JOIN sys_dept d ON d.id = u.dept_id
            LEFT JOIN sys_user_post up ON up.user_id = u.id
            LEFT JOIN sys_post p ON p.id = up.post_id AND p.deleted = 0
            LEFT JOIN sys_user_role ur ON ur.user_id = u.id
            LEFT JOIN sys_role r ON r.id = ur.role_id AND r.deleted = 0
            WHERE u.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR u.username LIKE CONCAT('%', #{keyword}, '%')
                   OR u.nickname LIKE CONCAT('%', #{keyword}, '%')
                   OR u.phone LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR u.status = #{status})
              AND (#{deptId} IS NULL OR u.dept_id IN (SELECT sd.id FROM sys_dept sd WHERE sd.id = #{deptId} OR FIND_IN_SET(#{deptId}, sd.ancestors)))
              AND (#{postId} IS NULL OR EXISTS (SELECT 1 FROM sys_user_post fup WHERE fup.user_id = u.id AND fup.post_id = #{postId}))
              AND (
                  #{scope.allScope} = TRUE
                  OR u.id = #{scope.userId}
                  <if test="scope.deptIds != null and scope.deptIds.size > 0">
                  OR u.dept_id IN
                  <foreach collection="scope.deptIds" item="scopeDeptId" open="(" separator="," close=")">
                      #{scopeDeptId}
                  </foreach>
                  </if>
              )
            GROUP BY u.id, u.username, u.nickname, u.phone, u.email, d.dept_name, u.status, u.create_time, u.last_login_time
            ORDER BY u.id
            LIMIT #{offset}, #{pageSize}
            </script>
            """)
    List<Map<String, Object>> selectUsers(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("deptId") Long deptId,
            @Param("postId") Long postId,
            @Param("scope") DataScopeCriteria scope,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT u.id, u.dept_id AS deptId
            FROM sys_user u
            WHERE u.username = #{username} AND u.deleted = 0 AND u.status = 1
            LIMIT 1
            """)
    Map<String, Object> selectUserProfileByUsername(@Param("username") String username);

    @Select("""
            SELECT r.id, r.data_scope AS dataScope
            FROM sys_user_role ur
            JOIN sys_role r ON r.id = ur.role_id
            WHERE ur.user_id = #{userId} AND r.status = 1 AND r.deleted = 0
            ORDER BY r.sort, r.id
            """)
    List<Map<String, Object>> selectActiveRoleScopes(@Param("userId") Long userId);

    @Select("""
            SELECT d.id
            FROM sys_dept d
            WHERE d.deleted = 0
              AND (d.id = #{deptId} OR FIND_IN_SET(#{deptId}, d.ancestors))
            ORDER BY d.id
            """)
    List<Long> selectDeptAndChildIds(@Param("deptId") Long deptId);

    @Select("SELECT dept_id FROM sys_role_dept WHERE role_id = #{roleId} ORDER BY dept_id")
    List<Long> selectRoleDeptIds(@Param("roleId") Long roleId);

    @Select("""
            SELECT COUNT(*)
            FROM sys_role r
            WHERE r.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR r.role_name LIKE CONCAT('%', #{keyword}, '%')
                   OR r.role_code LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR r.status = #{status})
            """)
    long countRoles(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT r.id,
                   r.role_name AS name,
                   r.role_code AS code,
                   CASE r.data_scope
                       WHEN 'ALL' THEN '全部数据权限'
                       WHEN 'DEPT_AND_CHILD' THEN '本部门及以下'
                       WHEN 'DEPT' THEN '本部门数据权限'
                       WHEN 'CUSTOM' THEN '自定义数据权限'
                       ELSE '仅本人数据权限'
                   END AS dataScope,
                   (SELECT COUNT(*) FROM sys_user_role ur JOIN sys_user cu ON cu.id = ur.user_id AND cu.deleted = 0 WHERE ur.role_id = r.id) AS userCount,
                   r.sort,
                   r.status,
                   r.builtin,
                   DATE_FORMAT(r.create_time, '%Y-%m-%d %H:%i') AS createTime,
                   (SELECT GROUP_CONCAT(rm.menu_id ORDER BY rm.menu_id)
                    FROM sys_role_menu rm
                    WHERE rm.role_id = r.id) AS menuIdsText,
                   r.remark
            FROM sys_role r
            WHERE r.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR r.role_name LIKE CONCAT('%', #{keyword}, '%')
                   OR r.role_code LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR r.status = #{status})
            ORDER BY r.sort, r.id
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectRoles(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT m.id,
                   m.parent_id AS parentId,
                   m.menu_name AS name,
                   m.menu_type AS type,
                   m.icon,
                   m.path,
                   m.component,
                   m.permission,
                   m.sort,
                   m.visible,
                   m.status
            FROM sys_menu m
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR m.menu_name LIKE CONCAT('%', #{keyword}, '%')
                   OR m.permission LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR m.status = #{status})
            ORDER BY m.parent_id, m.sort, m.id
            """)
    List<Map<String, Object>> selectMenus(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT d.id,
                   d.parent_id AS parentId,
                   d.dept_name AS name,
                   d.leader,
                   d.phone,
                   d.email,
                   d.sort,
                   d.status,
                   (SELECT COUNT(*) FROM sys_user u WHERE u.dept_id = d.id AND u.deleted = 0) AS memberCount
            FROM sys_dept d
            WHERE d.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR d.dept_name LIKE CONCAT('%', #{keyword}, '%')
                   OR d.leader LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR d.status = #{status})
            ORDER BY d.parent_id, d.sort, d.id
            """)
    List<Map<String, Object>> selectDepts(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT COUNT(*)
            FROM sys_post p
            WHERE p.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR p.post_name LIKE CONCAT('%', #{keyword}, '%')
                   OR p.post_code LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR p.status = #{status})
            """)
    long countPosts(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT p.id,
                   p.post_code AS postCode,
                   p.post_name AS postName,
                   p.sort,
                   p.status,
                   p.remark,
                   DATE_FORMAT(p.create_time, '%Y-%m-%d %H:%i') AS createTime,
                   (SELECT COUNT(*) FROM sys_user_post up JOIN sys_user cu ON cu.id = up.user_id AND cu.deleted = 0 WHERE up.post_id = p.id) AS userCount
            FROM sys_post p
            WHERE p.deleted = 0
              AND (#{keyword} IS NULL OR #{keyword} = ''
                   OR p.post_name LIKE CONCAT('%', #{keyword}, '%')
                   OR p.post_code LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR p.status = #{status})
            ORDER BY p.sort, p.id
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectPosts(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT COUNT(*)
            FROM sys_dict_type t
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR t.dict_name LIKE CONCAT('%', #{keyword}, '%')
                   OR t.dict_type LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR t.status = #{status})
            """)
    long countDictTypes(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT t.id,
                   t.dict_name AS dictName,
                   t.dict_type AS dictType,
                   t.status,
                   DATE_FORMAT(t.create_time, '%Y-%m-%d %H:%i') AS createTime,
                   t.remark
            FROM sys_dict_type t
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR t.dict_name LIKE CONCAT('%', #{keyword}, '%')
                   OR t.dict_type LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR t.status = #{status})
            ORDER BY t.id
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectDictTypes(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT d.id,
                   d.dict_label AS label,
                   d.dict_value AS value,
                   d.sort,
                   d.status,
                   d.tone,
                   d.is_default AS def
            FROM sys_dict_data d
            WHERE d.dict_type = #{dictType}
            ORDER BY d.sort, d.id
            """)
    List<Map<String, Object>> selectDictData(@Param("dictType") String dictType);

    /** 业务下拉只提供启用字典的启用选项，管理接口仍按字典管理权限保护。 */
    @Select("""
            SELECT d.dict_label AS label, d.dict_value AS value, d.tone,
                   d.is_default AS def, d.status
            FROM sys_dict_data d
            JOIN sys_dict_type t ON t.dict_type = d.dict_type AND t.status = 1
            WHERE d.dict_type = #{dictType} AND d.status = 1
            ORDER BY d.sort, d.id
            """)
    List<Map<String, Object>> selectDictOptions(@Param("dictType") String dictType);

    @Select("""
            SELECT COUNT(*)
            FROM sys_config c
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR c.config_name LIKE CONCAT('%', #{keyword}, '%')
                   OR c.config_key LIKE CONCAT('%', #{keyword}, '%'))
            """)
    long countConfigs(@Param("keyword") String keyword);

    @Select("""
            SELECT c.id,
                   c.config_name AS name,
                   c.config_key AS `key`,
                   c.config_value AS value,
                   c.config_type AS type,
                   c.builtin,
                   DATE_FORMAT(c.create_time, '%Y-%m-%d %H:%i') AS createTime,
                   c.remark
            FROM sys_config c
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR c.config_name LIKE CONCAT('%', #{keyword}, '%')
                   OR c.config_key LIKE CONCAT('%', #{keyword}, '%'))
            ORDER BY c.id
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectConfigs(
            @Param("keyword") String keyword,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT COUNT(*)
            FROM sys_oper_log l
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR l.module LIKE CONCAT('%', #{keyword}, '%')
                   OR l.action LIKE CONCAT('%', #{keyword}, '%')
                   OR l.oper_name LIKE CONCAT('%', #{keyword}, '%')
                   OR l.request_url LIKE CONCAT('%', #{keyword}, '%')
                   OR l.request_params LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{result} IS NULL OR l.result = #{result})
            """)
    long countOperLogs(@Param("keyword") String keyword, @Param("result") Integer result);

    @Select("""
            SELECT l.id,
                   l.module,
                   l.action,
                   l.request_method AS method,
                   l.request_url AS url,
                   l.request_params AS params,
                   l.oper_name AS operName,
                   l.dept_name AS dept,
                   l.ip,
                   l.location,
                   l.cost,
                   l.result,
                   l.error_msg AS errorMsg,
                   DATE_FORMAT(l.oper_time, '%Y-%m-%d %H:%i:%s') AS operTime
            FROM sys_oper_log l
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR l.module LIKE CONCAT('%', #{keyword}, '%')
                   OR l.action LIKE CONCAT('%', #{keyword}, '%')
                   OR l.oper_name LIKE CONCAT('%', #{keyword}, '%')
                   OR l.request_url LIKE CONCAT('%', #{keyword}, '%')
                   OR l.request_params LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{result} IS NULL OR l.result = #{result})
            ORDER BY l.oper_time DESC, l.id DESC
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectOperLogs(
            @Param("keyword") String keyword,
            @Param("result") Integer result,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Select("""
            SELECT COUNT(*)
            FROM sys_login_log l
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR l.username LIKE CONCAT('%', #{keyword}, '%')
                   OR l.ip LIKE CONCAT('%', #{keyword}, '%')
                   OR l.msg LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR l.status = #{status})
            """)
    long countLoginLogs(@Param("keyword") String keyword, @Param("status") Integer status);

    @Select("""
            SELECT l.id,
                   l.username,
                   l.ip,
                   l.location,
                   l.browser,
                   l.os,
                   l.status,
                   l.msg,
                   DATE_FORMAT(l.login_time, '%Y-%m-%d %H:%i:%s') AS loginTime
            FROM sys_login_log l
            WHERE (#{keyword} IS NULL OR #{keyword} = ''
                   OR l.username LIKE CONCAT('%', #{keyword}, '%')
                   OR l.ip LIKE CONCAT('%', #{keyword}, '%')
                   OR l.msg LIKE CONCAT('%', #{keyword}, '%'))
              AND (#{status} IS NULL OR l.status = #{status})
            ORDER BY l.login_time DESC, l.id DESC
            LIMIT #{offset}, #{pageSize}
            """)
    List<Map<String, Object>> selectLoginLogs(
            @Param("keyword") String keyword,
            @Param("status") Integer status,
            @Param("offset") int offset,
            @Param("pageSize") int pageSize
    );

    @Delete("DELETE FROM sys_oper_log WHERE id = #{id}")
    int deleteOperLog(@Param("id") Long id);

    @Delete("DELETE FROM sys_oper_log")
    int clearOperLogs();

    @Delete("DELETE FROM sys_login_log WHERE id = #{id}")
    int deleteLoginLog(@Param("id") Long id);

    @Delete("DELETE FROM sys_login_log")
    int clearLoginLogs();

    @Select("""
            SELECT COUNT(*)
            FROM sys_post
            WHERE post_code = #{postCode}
              AND deleted = 0
              AND (#{excludeId} IS NULL OR id <> #{excludeId})
            """)
    long countPostCode(@Param("postCode") String postCode, @Param("excludeId") Long excludeId);

    @Insert("""
            INSERT INTO sys_post (post_code, post_name, sort, status, remark, create_by, update_by)
            VALUES (#{row.postCode}, #{row.postName}, #{row.sort}, #{row.status}, #{row.remark}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertPost(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_post
            SET post_name = COALESCE(#{row.postName}, post_name),
                sort = COALESCE(#{row.sort}, sort),
                status = COALESCE(#{row.status}, status),
                remark = COALESCE(#{row.remark}, remark),
                update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int updatePost(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_post
            SET deleted = 1, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int softDeletePost(@Param("id") Long id, @Param("operator") String operator);

    @Select("""
            SELECT COUNT(*)
            FROM sys_user
            WHERE username = #{username}
              AND deleted = 0
              AND (#{excludeId} IS NULL OR id <> #{excludeId})
            """)
    long countUsername(@Param("username") String username, @Param("excludeId") Long excludeId);

    @Insert("""
            INSERT INTO sys_user (username, password, nickname, phone, email, dept_id, status, create_by, update_by)
            VALUES (#{row.username}, #{row.password}, #{row.nickname}, #{row.phone}, #{row.email}, #{row.deptId}, #{row.status}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertUser(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_user
            SET nickname = COALESCE(#{row.nickname}, nickname),
                phone = COALESCE(#{row.phone}, phone),
                email = COALESCE(#{row.email}, email),
                dept_id = COALESCE(#{row.deptId}, dept_id),
                status = COALESCE(#{row.status}, status),
                update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int updateUser(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_user
            SET status = #{status}, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int updateUserStatus(@Param("id") Long id, @Param("status") Integer status, @Param("operator") String operator);

    @Update("""
            UPDATE sys_user
            SET password = #{password}, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int resetUserPassword(@Param("id") Long id, @Param("password") String password, @Param("operator") String operator);

    @Update("""
            UPDATE sys_user
            SET deleted = 1, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int softDeleteUser(@Param("id") Long id, @Param("operator") String operator);

    @Delete("DELETE FROM sys_user_role WHERE user_id = #{userId}")
    void deleteUserRoles(@Param("userId") Long userId);

    @Insert("INSERT IGNORE INTO sys_user_role (user_id, role_id) VALUES (#{userId}, #{roleId})")
    void insertUserRole(@Param("userId") Long userId, @Param("roleId") Long roleId);

    @Delete("DELETE FROM sys_user_post WHERE user_id = #{userId}")
    void deleteUserPosts(@Param("userId") Long userId);

    @Insert("INSERT IGNORE INTO sys_user_post (user_id, post_id) VALUES (#{userId}, #{postId})")
    void insertUserPost(@Param("userId") Long userId, @Param("postId") Long postId);

    @Select("""
            SELECT COUNT(*)
            FROM sys_role
            WHERE role_code = #{code}
              AND deleted = 0
              AND (#{excludeId} IS NULL OR id <> #{excludeId})
            """)
    long countRoleCode(@Param("code") String code, @Param("excludeId") Long excludeId);

    @Insert("""
            INSERT INTO sys_role (role_name, role_code, data_scope, sort, status, builtin, remark, create_by, update_by)
            VALUES (#{row.name}, #{row.code}, #{row.dataScope}, #{row.sort}, #{row.status}, 0, #{row.remark}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertRole(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_role
            SET role_name = COALESCE(#{row.name}, role_name),
                data_scope = COALESCE(#{row.dataScope}, data_scope),
                sort = COALESCE(#{row.sort}, sort),
                status = COALESCE(#{row.status}, status),
                remark = COALESCE(#{row.remark}, remark),
                update_by = #{operator}
            WHERE id = #{id} AND deleted = 0 AND builtin = 0
            """)
    int updateRole(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_role
            SET deleted = 1, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0 AND builtin = 0
            """)
    int softDeleteRole(@Param("id") Long id, @Param("operator") String operator);

    @Delete("DELETE FROM sys_role_menu WHERE role_id = #{roleId}")
    void deleteRoleMenus(@Param("roleId") Long roleId);

    @Insert("INSERT IGNORE INTO sys_role_menu (role_id, menu_id) VALUES (#{roleId}, #{menuId})")
    void insertRoleMenu(@Param("roleId") Long roleId, @Param("menuId") Long menuId);

    @Select("SELECT menu_id FROM sys_role_menu WHERE role_id = #{roleId} ORDER BY menu_id")
    List<Long> selectRoleMenuIds(@Param("roleId") Long roleId);

    /** 权限关系图的用户节点：遵守数据权限，只取图谱展示所需字段。 */
    @Select("""
            <script>
            SELECT u.id, u.username, u.nickname, d.dept_name AS deptName, u.status
            FROM sys_user u
            LEFT JOIN sys_dept d ON d.id = u.dept_id
            WHERE u.deleted = 0
              AND (
                  #{scope.allScope} = TRUE
                  OR u.id = #{scope.userId}
                  <if test="scope.deptIds != null and scope.deptIds.size > 0">
                  OR u.dept_id IN
                  <foreach collection="scope.deptIds" item="scopeDeptId" open="(" separator="," close=")">
                      #{scopeDeptId}
                  </foreach>
                  </if>
              )
            ORDER BY u.id
            LIMIT 2000
            </script>
            """)
    List<Map<String, Object>> selectGraphUsers(@Param("scope") DataScopeCriteria scope);

    @Select("""
            SELECT ur.user_id AS userId, ur.role_id AS roleId
            FROM sys_user_role ur
            JOIN sys_user u ON u.id = ur.user_id AND u.deleted = 0
            JOIN sys_role r ON r.id = ur.role_id AND r.deleted = 0
            ORDER BY ur.user_id, ur.role_id
            """)
    List<Map<String, Object>> selectUserRoleLinks();

    @Select("""
            SELECT COUNT(*)
            FROM sys_user_role ur
            JOIN sys_user u ON u.id = ur.user_id
            WHERE ur.role_id = #{roleId} AND u.deleted = 0
            """)
    long countRoleUsers(@Param("roleId") Long roleId);

    @Select("""
            SELECT ancestors
            FROM sys_dept
            WHERE id = #{id} AND deleted = 0
            """)
    String selectDeptAncestors(@Param("id") Long id);

    @Insert("""
            INSERT INTO sys_dept (parent_id, ancestors, dept_name, leader, phone, email, sort, status, create_by, update_by)
            VALUES (#{row.parentId}, #{row.ancestors}, #{row.name}, #{row.leader}, #{row.phone}, #{row.email}, #{row.sort}, #{row.status}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertDept(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_dept
            SET parent_id = COALESCE(#{row.parentId}, parent_id),
                ancestors = COALESCE(#{row.ancestors}, ancestors),
                dept_name = COALESCE(#{row.name}, dept_name),
                leader = COALESCE(#{row.leader}, leader),
                phone = COALESCE(#{row.phone}, phone),
                email = COALESCE(#{row.email}, email),
                sort = COALESCE(#{row.sort}, sort),
                status = COALESCE(#{row.status}, status),
                update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int updateDept(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_dept
            SET deleted = 1, update_by = #{operator}
            WHERE id = #{id} AND deleted = 0
            """)
    int softDeleteDept(@Param("id") Long id, @Param("operator") String operator);

    @Select("SELECT COUNT(*) FROM sys_dept WHERE parent_id = #{deptId} AND deleted = 0")
    long countDeptChildren(@Param("deptId") Long deptId);

    @Select("SELECT COUNT(*) FROM sys_user WHERE dept_id = #{deptId} AND deleted = 0")
    long countDeptUsers(@Param("deptId") Long deptId);

    @Select("SELECT COALESCE(MAX(id), 0) + 1 FROM sys_menu")
    Long nextMenuId();

    @Insert("""
            INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, icon, path, component, permission, sort, visible, status, create_by, update_by)
            VALUES (#{row.id}, #{row.parentId}, #{row.name}, #{row.type}, #{row.icon}, #{row.path}, #{row.component}, #{row.permission}, #{row.sort}, #{row.visible}, #{row.status}, #{operator}, #{operator})
            """)
    int insertMenu(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_menu
            SET parent_id = COALESCE(#{row.parentId}, parent_id),
                menu_name = COALESCE(#{row.name}, menu_name),
                menu_type = COALESCE(#{row.type}, menu_type),
                icon = COALESCE(#{row.icon}, icon),
                path = COALESCE(#{row.path}, path),
                component = COALESCE(#{row.component}, component),
                permission = COALESCE(#{row.permission}, permission),
                sort = COALESCE(#{row.sort}, sort),
                visible = COALESCE(#{row.visible}, visible),
                status = COALESCE(#{row.status}, status),
                update_by = #{operator}
            WHERE id = #{id}
            """)
    int updateMenu(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Delete("DELETE FROM sys_menu WHERE id = #{id}")
    int deleteMenu(@Param("id") Long id);

    @Select("SELECT COUNT(*) FROM sys_menu WHERE parent_id = #{menuId}")
    long countMenuChildren(@Param("menuId") Long menuId);

    @Select("SELECT COUNT(*) FROM sys_role_menu WHERE menu_id = #{menuId}")
    long countMenuRoles(@Param("menuId") Long menuId);

    @Select("""
            SELECT COUNT(*)
            FROM sys_dict_type
            WHERE dict_type = #{dictType}
              AND (#{excludeId} IS NULL OR id <> #{excludeId})
            """)
    long countDictType(@Param("dictType") String dictType, @Param("excludeId") Long excludeId);

    @Insert("""
            INSERT INTO sys_dict_type (dict_name, dict_type, status, remark, create_by, update_by)
            VALUES (#{row.dictName}, #{row.dictType}, #{row.status}, #{row.remark}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertDictType(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_dict_type
            SET dict_name = COALESCE(#{row.dictName}, dict_name),
                status = COALESCE(#{row.status}, status),
                remark = COALESCE(#{row.remark}, remark),
                update_by = #{operator}
            WHERE id = #{id}
            """)
    int updateDictType(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Delete("DELETE FROM sys_dict_type WHERE id = #{id}")
    int deleteDictType(@Param("id") Long id);

    @Select("SELECT COUNT(*) FROM sys_dict_data WHERE dict_type = #{dictType}")
    long countDictDataByType(@Param("dictType") String dictType);

    @Select("SELECT dict_type FROM sys_dict_type WHERE id = #{id}")
    String selectDictTypeCode(@Param("id") Long id);

    @Insert("""
            INSERT INTO sys_dict_data (dict_type, dict_label, dict_value, sort, status, tone, is_default, remark, create_by, update_by)
            VALUES (#{row.dictType}, #{row.label}, #{row.value}, #{row.sort}, #{row.status}, #{row.tone}, #{row.def}, #{row.remark}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertDictData(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_dict_data
            SET dict_type = COALESCE(#{row.dictType}, dict_type),
                dict_label = COALESCE(#{row.label}, dict_label),
                dict_value = COALESCE(#{row.value}, dict_value),
                sort = COALESCE(#{row.sort}, sort),
                status = COALESCE(#{row.status}, status),
                tone = COALESCE(#{row.tone}, tone),
                is_default = COALESCE(#{row.def}, is_default),
                remark = COALESCE(#{row.remark}, remark),
                update_by = #{operator}
            WHERE id = #{id}
            """)
    int updateDictData(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Delete("DELETE FROM sys_dict_data WHERE id = #{id}")
    int deleteDictData(@Param("id") Long id);

    @Select("""
            SELECT COUNT(*)
            FROM sys_config
            WHERE config_key = #{key}
              AND (#{excludeId} IS NULL OR id <> #{excludeId})
            """)
    long countConfigKey(@Param("key") String key, @Param("excludeId") Long excludeId);

    @Insert("""
            INSERT INTO sys_config (config_name, config_key, config_value, config_type, builtin, remark, create_by, update_by)
            VALUES (#{row.name}, #{row.key}, #{row.value}, #{row.type}, #{row.builtin}, #{row.remark}, #{operator}, #{operator})
            """)
    @Options(useGeneratedKeys = true, keyProperty = "row.id")
    int insertConfig(@Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Update("""
            UPDATE sys_config
            SET config_name = COALESCE(#{row.name}, config_name),
                config_value = COALESCE(#{row.value}, config_value),
                config_type = COALESCE(#{row.type}, config_type),
                builtin = COALESCE(#{row.builtin}, builtin),
                remark = COALESCE(#{row.remark}, remark),
                update_by = #{operator}
            WHERE id = #{id} AND builtin = 0
            """)
    int updateConfig(@Param("id") Long id, @Param("row") Map<String, Object> row, @Param("operator") String operator);

    @Delete("DELETE FROM sys_config WHERE id = #{id} AND builtin = 0")
    int deleteConfig(@Param("id") Long id);
}
