package com.scaffold.system.service;

import com.scaffold.system.mapper.MonitorStatsMapper;
import org.springframework.stereotype.Service;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 监控日志只读统计：操作 / 登录日志概览与趋势，以及当日按模块聚合的时间轴泳道。
 */
@Service
public class MonitorStatsService {

    /** 同一模块两次操作间隔不超过 15 分钟时合并为一个时间块 */
    static final int MERGE_GAP_SECONDS = 15 * 60;
    /** 每个时间块最多回传的日志 ID 数，供前端定位明细 */
    static final int BLOCK_ID_LIMIT = 50;

    private static final DateTimeFormatter DB_TIME = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");
    private static final DateTimeFormatter HOUR_LABEL = DateTimeFormatter.ofPattern("HH:00");
    private static final DateTimeFormatter DAY_LABEL = DateTimeFormatter.ofPattern("MM-dd");

    private final MonitorStatsMapper mapper;

    public MonitorStatsService(MonitorStatsMapper mapper) {
        this.mapper = mapper;
    }

    public Map<String, Object> operStats(String range) {
        Window window = window(range);
        Map<String, Object> overview = mapper.selectOperOverview(window.since);
        long total = number(overview.get("total"));
        long failed = number(overview.get("failed"));
        long costCount = number(overview.get("costCount"));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("range", window.range);
        data.put("total", total);
        data.put("failed", failed);
        data.put("successRate", successRate(total, failed));
        data.put("avgCost", number(overview.get("avgCost")));
        data.put("p95Cost", costCount == 0 ? 0 : valueOrZero(mapper.selectOperCostAt(window.since, (long) Math.ceil(costCount * 0.95) - 1)));
        data.put("activeUsers", number(overview.get("activeUsers")));
        data.put("series", series(window, window.hourly
                ? mapper.selectOperHourly(window.since, window.now)
                : mapper.selectOperDaily(window.since, window.now)));
        return data;
    }

    public Map<String, Object> loginStats(String range) {
        Window window = window(range);
        Map<String, Object> overview = mapper.selectLoginOverview(window.since);
        long total = number(overview.get("total"));
        long failed = number(overview.get("failed"));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("range", window.range);
        data.put("total", total);
        data.put("failed", failed);
        data.put("successRate", successRate(total, failed));
        data.put("users", number(overview.get("users")));
        data.put("ips", number(overview.get("ips")));
        data.put("series", series(window, window.hourly
                ? mapper.selectLoginHourly(window.since, window.now)
                : mapper.selectLoginDaily(window.since, window.now)));
        return data;
    }

    /** 登录失败达到该次数即列为异常，可由参数 sys.login.alertThreshold 覆盖 */
    static final int DEFAULT_ALERT_THRESHOLD = 5;

    /**
     * 登录热力：最近 days 天按「星期 × 小时」聚合，cells 只回传有数据的格子；
     * anomalies 为同一 IP / 同一账号失败次数达到阈值的聚合告警。
     */
    public Map<String, Object> loginHeatmap(int days) {
        int span = days >= 30 ? 30 : 7;
        LocalDateTime now = LocalDateTime.parse(mapper.selectDbNow(), DB_TIME);
        String since = now.toLocalDate().minusDays(span - 1L).atStartOfDay().format(DB_TIME);
        int threshold = DEFAULT_ALERT_THRESHOLD;
        try {
            String configured = mapper.selectLoginAlertThreshold();
            if (configured != null && !configured.isBlank()) threshold = Math.max(1, Integer.parseInt(configured.trim()));
        } catch (NumberFormatException ignored) {
            // 参数值不是数字时沿用默认阈值
        }
        List<Map<String, Object>> cells = mapper.selectLoginHeatmap(since).stream()
                .map(row -> {
                    Map<String, Object> cell = new LinkedHashMap<>();
                    cell.put("dow", number(row.get("dow")));
                    cell.put("hour", number(row.get("hour")));
                    cell.put("total", number(row.get("total")));
                    cell.put("failed", number(row.get("failed")));
                    return cell;
                }).toList();
        List<Map<String, Object>> anomalies = new ArrayList<>();
        mapper.selectLoginIpAnomalies(since, threshold).forEach(row -> anomalies.add(anomaly("ip", row)));
        mapper.selectLoginUserAnomalies(since, threshold).forEach(row -> anomalies.add(anomaly("user", row)));
        anomalies.sort((a, b) -> Long.compare((long) b.get("failed"), (long) a.get("failed")));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("days", span);
        data.put("since", since);
        data.put("threshold", threshold);
        data.put("cells", cells);
        data.put("anomalies", anomalies);
        return data;
    }

    private Map<String, Object> anomaly(String kind, Map<String, Object> row) {
        Map<String, Object> item = new LinkedHashMap<>();
        item.put("kind", kind);
        item.put("key", String.valueOf(row.get("key")));
        item.put("failed", number(row.get("failed")));
        item.put("total", number(row.get("total")));
        item.put("spread", number(row.get("users")));
        item.put("firstTime", row.get("firstTime"));
        item.put("lastTime", row.get("lastTime"));
        return item;
    }

    /**
     * 当日泳道：按模块分道，同模块相邻操作间隔不超过 15 分钟合为一块。
     * 时间以当日秒数表示（0–86400），前端按比例落在 00:00–24:00 横轴上。
     */
    public Map<String, Object> operTimeline(LocalDate date) {
        LocalDateTime dbNow = LocalDateTime.parse(mapper.selectDbNow(), DB_TIME);
        LocalDate day = date == null ? dbNow.toLocalDate() : date;

        Map<String, List<Map<String, Object>>> lanes = new LinkedHashMap<>();
        Map<String, Map<String, Object>> open = new HashMap<>();
        for (Map<String, Object> point : mapper.selectOperPointsOfDay(day.atStartOfDay().format(DB_TIME))) {
            String module = String.valueOf(point.get("module"));
            int sec = (int) number(point.get("sec"));
            Map<String, Object> block = open.get(module);
            if (block == null || sec - (int) block.get("endSec") > MERGE_GAP_SECONDS) {
                block = newBlock(sec);
                lanes.computeIfAbsent(module, key -> new ArrayList<>()).add(block);
                open.put(module, block);
            }
            absorb(block, point, sec);
        }

        List<Map<String, Object>> laneRows = new ArrayList<>();
        lanes.forEach((module, blocks) -> {
            Map<String, Object> lane = new LinkedHashMap<>();
            lane.put("module", module);
            lane.put("count", blocks.stream().mapToLong(b -> number(b.get("count"))).sum());
            lane.put("blocks", blocks);
            laneRows.add(lane);
        });
        laneRows.sort((a, b) -> Long.compare(number(b.get("count")), number(a.get("count"))));

        Map<String, Object> data = new LinkedHashMap<>();
        data.put("date", day.toString());
        data.put("nowSec", day.equals(dbNow.toLocalDate()) ? dbNow.toLocalTime().toSecondOfDay() : null);
        data.put("lanes", laneRows);
        return data;
    }

    private Map<String, Object> newBlock(int sec) {
        Map<String, Object> block = new LinkedHashMap<>();
        block.put("startSec", sec);
        block.put("endSec", sec);
        block.put("count", 0L);
        block.put("failed", 0L);
        block.put("maxCost", 0L);
        block.put("ids", new ArrayList<Long>());
        return block;
    }

    @SuppressWarnings("unchecked")
    private void absorb(Map<String, Object> block, Map<String, Object> point, int sec) {
        block.put("endSec", sec);
        block.put("count", number(block.get("count")) + 1);
        if (number(point.get("result")) == 0) {
            block.put("failed", number(block.get("failed")) + 1);
        }
        block.put("maxCost", Math.max(number(block.get("maxCost")), number(point.get("cost"))));
        List<Long> ids = (List<Long>) block.get("ids");
        if (ids.size() < BLOCK_ID_LIMIT) {
            ids.add(number(point.get("id")));
        }
    }

    private List<Map<String, Object>> series(Window window, List<Map<String, Object>> rows) {
        Map<Integer, Map<String, Object>> byAgo = new HashMap<>();
        rows.forEach(row -> byAgo.put((int) number(row.get("ago")), row));
        List<Map<String, Object>> result = new ArrayList<>();
        for (int i = 0; i < window.buckets; i++) {
            int ago = window.buckets - 1 - i;
            Map<String, Object> row = byAgo.get(ago);
            Map<String, Object> bucket = new LinkedHashMap<>();
            bucket.put("bucket", window.hourly
                    ? window.nowTime.minusHours(ago).format(HOUR_LABEL)
                    : window.nowTime.toLocalDate().minusDays(ago).format(DAY_LABEL));
            bucket.put("total", row == null ? 0 : number(row.get("total")));
            bucket.put("failed", row == null ? 0 : number(row.get("failed")));
            result.add(bucket);
        }
        return result;
    }

    private Window window(String range) {
        LocalDateTime now = LocalDateTime.parse(mapper.selectDbNow(), DB_TIME);
        return switch (range == null ? "" : range) {
            case "7d" -> new Window("7d", false, 7, now, now.toLocalDate().minusDays(6).atStartOfDay());
            case "30d" -> new Window("30d", false, 30, now, now.toLocalDate().minusDays(29).atStartOfDay());
            default -> new Window("24h", true, 24, now, now.minusHours(24));
        };
    }

    private static double successRate(long total, long failed) {
        return total > 0 ? Math.round((total - failed) * 1000.0 / total) / 10.0 : 100.0;
    }

    private static long valueOrZero(Long value) {
        return value == null ? 0 : value;
    }

    private static long number(Object value) {
        return value instanceof Number number ? number.longValue() : 0;
    }

    private static final class Window {
        final String range;
        final boolean hourly;
        final int buckets;
        final LocalDateTime nowTime;
        final String now;
        final String since;

        Window(String range, boolean hourly, int buckets, LocalDateTime now, LocalDateTime since) {
            this.range = range;
            this.hourly = hourly;
            this.buckets = buckets;
            this.nowTime = now;
            this.now = now.format(DB_TIME);
            this.since = since.format(DB_TIME);
        }
    }
}
