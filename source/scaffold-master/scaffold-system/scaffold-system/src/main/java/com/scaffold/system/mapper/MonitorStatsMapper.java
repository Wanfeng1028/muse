package com.scaffold.system.mapper;

import org.apache.ibatis.annotations.Mapper;
import org.apache.ibatis.annotations.Param;
import org.apache.ibatis.annotations.Select;

import java.util.List;
import java.util.Map;

/**
 * 监控日志只读聚合：概览读数、按时间桶趋势、当日泳道原始点。
 * 时间边界统一由数据库时钟给出（字符串 yyyy-MM-dd HH:mm:ss），避免 JVM 与会话时区不一致。
 */
@Mapper
public interface MonitorStatsMapper {

    @Select("SELECT DATE_FORMAT(NOW(), '%Y-%m-%d %H:%i:%s')")
    String selectDbNow();

    /* ── 操作日志 ─────────────────────────────────────────── */

    @Select("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(result = 0), 0) AS failed,
                   COALESCE(ROUND(AVG(cost)), 0) AS avgCost,
                   COUNT(cost) AS costCount,
                   COUNT(DISTINCT oper_name) AS activeUsers
            FROM sys_oper_log
            WHERE oper_time >= #{since}
            """)
    Map<String, Object> selectOperOverview(@Param("since") String since);

    @Select("""
            SELECT cost
            FROM sys_oper_log
            WHERE oper_time >= #{since} AND cost IS NOT NULL
            ORDER BY cost
            LIMIT 1 OFFSET #{offset}
            """)
    Long selectOperCostAt(@Param("since") String since, @Param("offset") long offset);

    @Select("""
            SELECT TIMESTAMPDIFF(HOUR, oper_time, #{now}) AS ago, COUNT(*) AS total, COALESCE(SUM(result = 0), 0) AS failed
            FROM sys_oper_log
            WHERE oper_time >= #{since}
            GROUP BY ago
            """)
    List<Map<String, Object>> selectOperHourly(@Param("since") String since, @Param("now") String now);

    @Select("""
            SELECT DATEDIFF(DATE(#{now}), DATE(oper_time)) AS ago, COUNT(*) AS total, COALESCE(SUM(result = 0), 0) AS failed
            FROM sys_oper_log
            WHERE oper_time >= #{since}
            GROUP BY ago
            """)
    List<Map<String, Object>> selectOperDaily(@Param("since") String since, @Param("now") String now);

    @Select("""
            SELECT id,
                   module,
                   TIME_TO_SEC(TIME(oper_time)) AS sec,
                   result,
                   cost
            FROM sys_oper_log
            WHERE oper_time >= #{start} AND oper_time < DATE_ADD(#{start}, INTERVAL 1 DAY)
            ORDER BY module, oper_time, id
            LIMIT 5000
            """)
    List<Map<String, Object>> selectOperPointsOfDay(@Param("start") String start);

    /* ── 登录日志 ─────────────────────────────────────────── */

    @Select("""
            SELECT COUNT(*) AS total,
                   COALESCE(SUM(status = 0), 0) AS failed,
                   COUNT(DISTINCT username) AS users,
                   COUNT(DISTINCT ip) AS ips
            FROM sys_login_log
            WHERE login_time >= #{since}
            """)
    Map<String, Object> selectLoginOverview(@Param("since") String since);

    @Select("""
            SELECT TIMESTAMPDIFF(HOUR, login_time, #{now}) AS ago, COUNT(*) AS total, COALESCE(SUM(status = 0), 0) AS failed
            FROM sys_login_log
            WHERE login_time >= #{since}
            GROUP BY ago
            """)
    List<Map<String, Object>> selectLoginHourly(@Param("since") String since, @Param("now") String now);

    @Select("""
            SELECT DATEDIFF(DATE(#{now}), DATE(login_time)) AS ago, COUNT(*) AS total, COALESCE(SUM(status = 0), 0) AS failed
            FROM sys_login_log
            WHERE login_time >= #{since}
            GROUP BY ago
            """)
    List<Map<String, Object>> selectLoginDaily(@Param("since") String since, @Param("now") String now);

    /* ── 登录热力与异常聚合 ─────────────────────────────────── */

    /** 星期（0 周一 … 6 周日）× 小时 的登录量与失败量 */
    @Select("""
            SELECT WEEKDAY(login_time) AS dow, HOUR(login_time) AS hour,
                   COUNT(*) AS total, COALESCE(SUM(status = 0), 0) AS failed
            FROM sys_login_log
            WHERE login_time >= #{since}
            GROUP BY dow, hour
            """)
    List<Map<String, Object>> selectLoginHeatmap(@Param("since") String since);

    /** 同一 IP 失败次数达到阈值：users 为该 IP 尝试过的不同账号数 */
    @Select("""
            SELECT ip AS `key`,
                   COALESCE(SUM(status = 0), 0) AS failed,
                   COUNT(*) AS total,
                   COUNT(DISTINCT username) AS users,
                   DATE_FORMAT(MIN(login_time), '%Y-%m-%d %H:%i') AS firstTime,
                   DATE_FORMAT(MAX(login_time), '%Y-%m-%d %H:%i') AS lastTime
            FROM sys_login_log
            WHERE login_time >= #{since} AND ip IS NOT NULL AND ip <> ''
            GROUP BY ip
            HAVING failed >= #{threshold}
            ORDER BY failed DESC, lastTime DESC
            LIMIT 12
            """)
    List<Map<String, Object>> selectLoginIpAnomalies(@Param("since") String since, @Param("threshold") int threshold);

    /** 同一账号失败次数达到阈值：users 位置返回来源 IP 数 */
    @Select("""
            SELECT username AS `key`,
                   COALESCE(SUM(status = 0), 0) AS failed,
                   COUNT(*) AS total,
                   COUNT(DISTINCT ip) AS users,
                   DATE_FORMAT(MIN(login_time), '%Y-%m-%d %H:%i') AS firstTime,
                   DATE_FORMAT(MAX(login_time), '%Y-%m-%d %H:%i') AS lastTime
            FROM sys_login_log
            WHERE login_time >= #{since} AND username IS NOT NULL AND username <> ''
            GROUP BY username
            HAVING failed >= #{threshold}
            ORDER BY failed DESC, lastTime DESC
            LIMIT 12
            """)
    List<Map<String, Object>> selectLoginUserAnomalies(@Param("since") String since, @Param("threshold") int threshold);

    @Select("SELECT config_value FROM sys_config WHERE config_key = 'sys.login.alertThreshold' LIMIT 1")
    String selectLoginAlertThreshold();
}
