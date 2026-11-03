package com.scaffold.system.service;

import com.scaffold.system.mapper.DashboardMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class DashboardService {

    private final DashboardMapper mapper;

    public DashboardService(DashboardMapper mapper) {
        this.mapper = mapper;
    }

    public Map<String, Object> summary(String range) {
        int hours = switch (range) {
            case "7d" -> 168;
            case "30d" -> 720;
            default -> 24;
        };
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("stats", stats());
        data.put("trend", trend(hours));
        data.put("trendPrev", hours <= 24 ? mapper.countLoginsPrev24h() : mapper.countLoginsPrevDays(hours / 24));
        data.put("dailyOps", dailyOps());
        data.put("activities", mapper.selectActivities());
        data.put("roleDist", mapper.selectRoleDistribution());

        long totalCalls = mapper.countApiCallsInHours(hours);
        long successCalls = mapper.countApiCallsSuccessInHours(hours);
        data.put("trendTotal", totalCalls);
        data.put("successRate", totalCalls > 0 ? Math.round(successCalls * 1000.0 / totalCalls) / 10.0 : 100.0);

        return data;
    }

    /** 近 7 天按日操作量，缺失的日期补 0；日期取数据库当天，避免与会话时区错位 */
    private List<Map<String, Object>> dailyOps() {
        Map<Integer, Map<String, Object>> byDay = new LinkedHashMap<>();
        for (Map<String, Object> row : mapper.selectDailyOps()) {
            if (row.get("dayIndex") instanceof Number index) {
                byDay.put(index.intValue(), row);
            }
        }
        LocalDate today = LocalDate.parse(mapper.selectToday());
        List<Map<String, Object>> days = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            Map<String, Object> row = byDay.get(i);
            Map<String, Object> day = new LinkedHashMap<>();
            day.put("date", today.minusDays(6 - i).toString());
            day.put("total", row == null ? 0 : ((Number) row.get("total")).longValue());
            day.put("failed", row == null ? 0 : ((Number) row.get("failed")).longValue());
            days.add(day);
        }
        return days;
    }

    private List<Map<String, Object>> stats() {
        long users = mapper.countUsers();
        long online = mapper.countOnlineUsers();
        long roles = mapper.countRoles();
        long apiCalls = mapper.countApiCalls();

        long usersNew = mapper.countUsersCreatedSince1d();
        long online2h = mapper.countOnlineUsers2h();
        long rolesNew = mapper.countRolesCreatedSince1d();
        long apiPrev = mapper.countApiCallsPrev24h();

        return List.of(
                stat("users", "用户总数", users, "users", "ok", delta(users, usersNew)),
                stat("online", "在线用户", online, "monitor", "info", delta(online, online2h)),
                stat("roles", "角色数量", roles, "shield", "warn", delta(roles, rolesNew)),
                stat("api", "24h 接口调用", apiCalls, "command", "purple", deltaCompare(apiCalls, apiPrev)),
                stat("menus", "菜单项", mapper.countMenus(), "menu", "info", delta(1, 0)),
                stat("depts", "部门数", mapper.countDepts(), "dept", "ok", delta(1, 0))
        );
    }

    private Map<String, Object> stat(String key, String label, long value, String icon, String tone, double[] deltaInfo) {
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("key", key);
        row.put("label", label);
        row.put("value", value);
        row.put("icon", icon);
        row.put("tone", tone);
        row.put("delta", deltaInfo[0]);
        row.put("up", deltaInfo[1] > 0);
        row.put("fresh", deltaInfo.length > 2 && deltaInfo[2] > 0);
        row.put("sub", subText(key));
        return row;
    }

    private double[] delta(long total, long recent) {
        if (total == 0) return new double[]{0, 0};
        double pct = Math.round(recent * 1000.0 / Math.max(total, 1)) / 10.0;
        return new double[]{pct, 1};
    }

    private double[] deltaCompare(long current, long previous) {
        // 上一周期为 0 时无法计算环比，标记为「新增」（第三位），前端不再显示误导的 +100%
        if (previous == 0) return new double[]{0, current > 0 ? 1 : 0, current > 0 ? 1 : 0};
        double pct = Math.round((current - previous) * 1000.0 / previous) / 10.0;
        return new double[]{Math.abs(pct), pct >= 0 ? 1 : -1};
    }

    private String subText(String key) {
        return switch (key) {
            case "users" -> "当前启用账号";
            case "online" -> "最近 1 小时登录";
            case "roles" -> "已启用角色";
            case "api" -> "最近 24 小时操作";
            case "menus" -> "目录 / 菜单 / 按钮";
            case "depts" -> "未删除部门";
            default -> "";
        };
    }

    private List<Integer> trend(int hours) {
        int buckets = Math.min(hours, 24);
        Map<Integer, Integer> totalsByBucket = new LinkedHashMap<>();

        if (hours <= 24) {
            for (Map<String, Object> row : mapper.selectLoginTrend()) {
                Number hourVal = (Number) row.get("hourValue");
                Number totalVal = (Number) row.get("total");
                if (hourVal != null && totalVal != null) {
                    totalsByBucket.put(hourVal.intValue(), totalVal.intValue());
                }
            }
            List<Integer> values = new ArrayList<>();
            LocalDateTime now = LocalDateTime.now();
            for (int i = 23; i >= 0; i--) {
                int hour = now.minusHours(i).getHour();
                values.add(totalsByBucket.getOrDefault(hour, 0));
            }
            return values;
        }

        int days = hours / 24;
        for (Map<String, Object> row : mapper.selectLoginTrendByDay(days)) {
            Number dayIdx = (Number) row.get("dayIndex");
            Number totalVal = (Number) row.get("total");
            if (dayIdx != null && totalVal != null) {
                totalsByBucket.put(dayIdx.intValue(), totalVal.intValue());
            }
        }
        List<Integer> values = new ArrayList<>();
        for (int i = 0; i < days; i++) {
            values.add(totalsByBucket.getOrDefault(i, 0));
        }
        return values;
    }
}
