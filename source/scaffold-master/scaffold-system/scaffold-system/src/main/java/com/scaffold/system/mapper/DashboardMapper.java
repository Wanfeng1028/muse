package com.scaffold.system.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

@Mapper
public interface DashboardMapper {

    @Select("SELECT COUNT(*) FROM sys_user WHERE deleted = 0")
    long countUsers();

    @Select("""
            SELECT COUNT(*)
            FROM sys_login_log
            WHERE status = 1 AND login_time >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            """)
    long countOnlineUsers();

    @Select("SELECT COUNT(*) FROM sys_role WHERE deleted = 0")
    long countRoles();

    @Select("SELECT COUNT(*) FROM sys_menu")
    long countMenus();

    @Select("SELECT COUNT(*) FROM sys_dept WHERE deleted = 0")
    long countDepts();

    @Select("""
            SELECT COUNT(*)
            FROM sys_oper_log
            WHERE oper_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """)
    long countApiCalls();

    @Select("""
            SELECT HOUR(login_time) AS hourValue, COUNT(*) AS total
            FROM sys_login_log
            WHERE login_time >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY HOUR(login_time)
            """)
    List<Map<String, Object>> selectLoginTrend();

    @Select("SELECT COUNT(*) FROM sys_user WHERE deleted = 0 AND create_time >= DATE_SUB(NOW(), INTERVAL 1 DAY)")
    long countUsersCreatedSince1d();

    @Select("SELECT COUNT(*) FROM sys_login_log WHERE status = 1 AND login_time >= DATE_SUB(NOW(), INTERVAL 2 HOUR)")
    long countOnlineUsers2h();

    @Select("SELECT COUNT(*) FROM sys_role WHERE deleted = 0 AND create_time >= DATE_SUB(NOW(), INTERVAL 1 DAY)")
    long countRolesCreatedSince1d();

    @Select("SELECT COUNT(*) FROM sys_oper_log WHERE oper_time >= DATE_SUB(NOW(), INTERVAL 48 HOUR) AND oper_time < DATE_SUB(NOW(), INTERVAL 24 HOUR)")
    long countApiCallsPrev24h();

    @Select("""
            SELECT r.data_scope AS label, COUNT(u.id) AS value
            FROM sys_role r
            LEFT JOIN sys_user_role ur ON r.id = ur.role_id
            LEFT JOIN sys_user u ON u.id = ur.user_id AND u.deleted = 0
            WHERE r.deleted = 0
            GROUP BY r.data_scope
            ORDER BY value DESC
            """)
    List<Map<String, Object>> selectRoleDistribution();

    @Select("SELECT COUNT(*) FROM sys_oper_log WHERE oper_time >= DATE_SUB(NOW(), INTERVAL #{hours} HOUR)")
    long countApiCallsInHours(int hours);

    @Select("SELECT COUNT(*) FROM sys_oper_log WHERE oper_time >= DATE_SUB(NOW(), INTERVAL #{hours} HOUR) AND result = 1")
    long countApiCallsSuccessInHours(int hours);

    @Select("""
            SELECT DATEDIFF(DATE(login_time), CURDATE() - INTERVAL (#{days} - 1) DAY) AS dayIndex, COUNT(*) AS total
            FROM sys_login_log
            WHERE login_time >= CURDATE() - INTERVAL (#{days} - 1) DAY
            GROUP BY dayIndex
            ORDER BY dayIndex
            """)
    List<Map<String, Object>> selectLoginTrendByDay(int days);

    @Select("""
            SELECT username AS who,
                   CASE status WHEN 1 THEN '登录系统' ELSE '登录失败' END AS action,
                   COALESCE(msg, '登录') AS target,
                   DATE_FORMAT(login_time, '%Y-%m-%d %H:%i') AS time,
                   CASE status WHEN 1 THEN 'ok' ELSE 'danger' END AS tint
            FROM sys_login_log
            ORDER BY login_time DESC, id DESC
            LIMIT 8
            """)
    List<Map<String, Object>> selectActivities();

    /** 上一周期登录数（24 小时档）：48 小时前到 24 小时前 */
    @Select("SELECT COUNT(*) FROM sys_login_log WHERE login_time >= DATE_SUB(NOW(), INTERVAL 48 HOUR) AND login_time < DATE_SUB(NOW(), INTERVAL 24 HOUR)")
    long countLoginsPrev24h();

    /** 上一周期登录数（按天档）：与当前 days 天窗口等长的前一段 */
    @Select("""
            SELECT COUNT(*)
            FROM sys_login_log
            WHERE login_time >= CURDATE() - INTERVAL (#{days} * 2 - 1) DAY
              AND login_time < CURDATE() - INTERVAL (#{days} - 1) DAY
            """)
    long countLoginsPrevDays(int days);

    @Select("SELECT DATE_FORMAT(CURDATE(), '%Y-%m-%d')")
    String selectToday();

    /** 近 7 天按日操作量：dayIndex 0 为 6 天前，6 为今天 */
    @Select("""
            SELECT DATEDIFF(DATE(oper_time), CURDATE() - INTERVAL 6 DAY) AS dayIndex,
                   COUNT(*) AS total,
                   COALESCE(SUM(result = 0), 0) AS failed
            FROM sys_oper_log
            WHERE oper_time >= CURDATE() - INTERVAL 6 DAY
            GROUP BY dayIndex
            """)
    List<Map<String, Object>> selectDailyOps();
}
