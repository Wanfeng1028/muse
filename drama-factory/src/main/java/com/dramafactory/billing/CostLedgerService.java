package com.dramafactory.billing;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDate;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * 成本账本服务，管理估算/预留/完成/失败/退款状态机与预算守卫。
 */
@Service
public class CostLedgerService {

    /**
     * 某提供方某天的费用汇总。
     * spentUsd 只统计 COMPLETED/FAILED 条目的 actualUsd。
     */
    public record ProviderDailyCost(String provider, double estimatedUsd, double spentUsd, long entryCount) {
    }

    private final CostLedgerEntryRepository repository;

    public CostLedgerService(CostLedgerEntryRepository repository) {
        this.repository = repository;
    }

    /**
     * 创建一条 ESTIMATED 条目并返回其 id。
     *
     * @throws IllegalArgumentException 当 estimatedUsd 为负数时
     */
    @Transactional
    public Long recordEstimate(Long projectId, String provider, String model, String operation,
                               double estimatedUsd, String note) {
        if (estimatedUsd < 0) {
            throw new IllegalArgumentException("estimatedUsd must not be negative: " + estimatedUsd);
        }
        CostLedgerEntry entry = new CostLedgerEntry();
        entry.setProjectId(projectId);
        entry.setProvider(provider);
        entry.setModel(model);
        entry.setOperation(operation);
        entry.setEstimatedUsd(estimatedUsd);
        entry.setStatus(CostLedgerStatus.ESTIMATED);
        entry.setNote(note);
        CostLedgerEntry saved = repository.save(entry);
        return saved.getId();
    }

    /**
     * 将 ESTIMATED 条目预留为 RESERVED，并执行预算守卫。
     *
     * @throws IllegalStateException   当前状态不是 ESTIMATED
     * @throws IllegalArgumentException 条目不存在
     * @throws BudgetExceededException CAP 模式下超预算
     */
    @Transactional
    public void reserve(Long entryId, BudgetPolicy policy) {
        CostLedgerEntry entry = requireEntry(entryId);
        if (entry.getStatus() != CostLedgerStatus.ESTIMATED) {
            throw new IllegalStateException("Entry " + entryId + " is not ESTIMATED, current=" + entry.getStatus());
        }
        BudgetPolicy safePolicy = policy == null
                ? new BudgetPolicy(BudgetMode.WARN, 0d, 0d)
                : policy;
        double reservePct = clamp(safePolicy.reservePct(), 0d, 0.9d);
        double spent = sumActualForStatuses(List.of(CostLedgerStatus.COMPLETED, CostLedgerStatus.FAILED));
        double reserved = sumEstimatedForStatuses(List.of(CostLedgerStatus.RESERVED));
        double usable = safePolicy.budgetTotalUsd() - spent - reserved - safePolicy.budgetTotalUsd() * reservePct;

        if (entry.getEstimatedUsd() > usable) {
            if (safePolicy.mode() == BudgetMode.CAP) {
                throw new BudgetExceededException(
                        "Estimated " + entry.getEstimatedUsd() + " exceeds usable budget " + usable,
                        entry.getEstimatedUsd(), usable);
            }
            String warning = "[BUDGET-WARN] estimated " + entry.getEstimatedUsd()
                    + " exceeds usable budget " + usable;
            entry.setNote(appendNote(entry.getNote(), warning));
        }
        entry.setStatus(CostLedgerStatus.RESERVED);
        repository.save(entry);
    }

    /**
     * 将 RESERVED 条目完成为 COMPLETED，记录实际花费。
     */
    @Transactional
    public void complete(Long entryId, double actualUsd, Long durationMs) {
        CostLedgerEntry entry = requireEntry(entryId);
        if (entry.getStatus() != CostLedgerStatus.RESERVED) {
            throw new IllegalStateException("Entry " + entryId + " is not RESERVED, current=" + entry.getStatus());
        }
        entry.setActualUsd(actualUsd);
        entry.setDurationMs(durationMs);
        entry.setStatus(CostLedgerStatus.COMPLETED);
        repository.save(entry);
    }

    /**
     * 将 RESERVED 条目标记为 FAILED，记录实际花费与补充说明。
     */
    @Transactional
    public void fail(Long entryId, double actualUsd, Long durationMs, String note) {
        CostLedgerEntry entry = requireEntry(entryId);
        if (entry.getStatus() != CostLedgerStatus.RESERVED) {
            throw new IllegalStateException("Entry " + entryId + " is not RESERVED, current=" + entry.getStatus());
        }
        entry.setActualUsd(actualUsd);
        entry.setDurationMs(durationMs);
        entry.setNote(appendNote(entry.getNote(), note));
        entry.setStatus(CostLedgerStatus.FAILED);
        repository.save(entry);
    }

    /**
     * 将 RESERVED 条目退款为 REFUNDED，释放冻结金额。
     */
    @Transactional
    public void refund(Long entryId) {
        CostLedgerEntry entry = requireEntry(entryId);
        if (entry.getStatus() != CostLedgerStatus.RESERVED) {
            throw new IllegalStateException("Entry " + entryId + " is not RESERVED, current=" + entry.getStatus());
        }
        entry.setStatus(CostLedgerStatus.REFUNDED);
        repository.save(entry);
    }

    /**
     * 汇总成本，所有过滤参数均可为 null 表示不过滤。
     */
    @Transactional(readOnly = true)
    public CostSummary summarize(Long projectId, String provider, LocalDateTime from, LocalDateTime to) {
        List<CostLedgerEntry> candidates;
        if (projectId != null) {
            candidates = repository.findByProjectId(projectId);
        } else if (provider != null) {
            candidates = repository.findByProvider(provider);
        } else {
            candidates = repository.findAll();
        }
        List<CostLedgerEntry> filtered = new ArrayList<>();
        for (CostLedgerEntry entry : candidates) {
            if (provider != null && !provider.equals(entry.getProvider())) {
                continue;
            }
            if (from != null && (entry.getCreatedAt() == null || entry.getCreatedAt().isBefore(from))) {
                continue;
            }
            if (to != null && (entry.getCreatedAt() == null || entry.getCreatedAt().isAfter(to))) {
                continue;
            }
            filtered.add(entry);
        }

        long entryCount = filtered.size();
        double totalEstimated = 0d;
        double totalReserved = 0d;
        double totalSpent = 0d;
        Map<CostLedgerStatus, Long> countByStatus = new EnumMap<>(CostLedgerStatus.class);
        for (CostLedgerStatus status : CostLedgerStatus.values()) {
            countByStatus.put(status, 0L);
        }
        for (CostLedgerEntry entry : filtered) {
            totalEstimated += entry.getEstimatedUsd();
            CostLedgerStatus status = entry.getStatus();
            if (status == CostLedgerStatus.RESERVED) {
                totalReserved += entry.getEstimatedUsd();
            }
            if (status == CostLedgerStatus.COMPLETED || status == CostLedgerStatus.FAILED) {
                totalSpent += entry.getActualUsd() == null ? 0d : entry.getActualUsd();
            }
            if (status != null) {
                countByStatus.merge(status, 1L, Long::sum);
            }
        }
        return new CostSummary(entryCount, totalEstimated, totalReserved, totalSpent, countByStatus);
    }

    /**
     * 按天汇总各提供方费用。date 为 null 时使用今天；
     * 按 provider 分组（null/空白归入 unknown），返回按 provider 名称排序的列表。
     */
    @Transactional(readOnly = true)
    public List<ProviderDailyCost> summarizeDaily(LocalDate date) {
        LocalDate day = date != null ? date : LocalDate.now();
        LocalDateTime start = day.atStartOfDay();
        LocalDateTime end = day.plusDays(1).atStartOfDay();

        Map<String, double[]> accumulator = new LinkedHashMap<>();
        Map<String, Long> counts = new LinkedHashMap<>();

        for (CostLedgerEntry entry : repository.findAll()) {
            LocalDateTime createdAt = entry.getCreatedAt();
            if (createdAt == null) {
                continue;
            }
            if (createdAt.isBefore(start) || !createdAt.isBefore(end)) {
                continue;
            }
            String provider = entry.getProvider();
            if (provider == null || provider.isBlank()) {
                provider = "unknown";
            }
            double[] values = accumulator.computeIfAbsent(provider, key -> new double[2]);
            values[0] += entry.getEstimatedUsd();
            CostLedgerStatus status = entry.getStatus();
            if (status == CostLedgerStatus.COMPLETED || status == CostLedgerStatus.FAILED) {
                Double actualUsd = entry.getActualUsd();
                values[1] += actualUsd != null ? actualUsd : 0.0;
            }
            counts.merge(provider, 1L, Long::sum);
        }

        List<ProviderDailyCost> result = new ArrayList<>();
        for (Map.Entry<String, double[]> e : accumulator.entrySet()) {
            String provider = e.getKey();
            double[] values = e.getValue();
            long count = counts.getOrDefault(provider, 0L);
            result.add(new ProviderDailyCost(provider, values[0], values[1], count));
        }
        result.sort(Comparator.comparing(ProviderDailyCost::provider));
        return result;
    }

    /**
     * 按 id 查找条目，缺失时抛 IllegalArgumentException。
     */
    public CostLedgerEntry requireEntry(Long id) {
        if (id == null) {
            throw new IllegalArgumentException("entryId must not be null");
        }
        return repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("CostLedgerEntry not found: " + id));
    }

    private double sumActualForStatuses(List<CostLedgerStatus> statuses) {
        double total = 0d;
        for (CostLedgerStatus status : statuses) {
            for (CostLedgerEntry entry : repository.findByStatus(status)) {
                total += entry.getActualUsd() == null ? 0d : entry.getActualUsd();
            }
        }
        return total;
    }

    private double sumEstimatedForStatuses(List<CostLedgerStatus> statuses) {
        double total = 0d;
        for (CostLedgerStatus status : statuses) {
            for (CostLedgerEntry entry : repository.findByStatus(status)) {
                total += entry.getEstimatedUsd();
            }
        }
        return total;
    }

    private static double clamp(double value, double min, double max) {
        if (value < min) {
            return min;
        }
        if (value > max) {
            return max;
        }
        return value;
    }

    private static String appendNote(String existing, String extra) {
        if (extra == null || extra.isEmpty()) {
            return existing;
        }
        if (existing == null || existing.isEmpty()) {
            return extra;
        }
        return existing + " | " + extra;
    }

}
