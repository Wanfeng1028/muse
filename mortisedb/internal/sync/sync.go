package sync

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/connector"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/metrics"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
)

// TableStats 单表同步统计
type TableStats struct {
	Table     string `json:"table"`
	Inserted  int    `json:"inserted"`
	Updated   int    `json:"updated"`
	Deleted   int    `json:"deleted"`
	Skipped   int    `json:"skipped"`
	Conflicts int    `json:"conflicts"`
}

// SourceStats 单源同步统计
type SourceStats struct {
	Source string       `json:"source"`
	Tables []TableStats `json:"tables"`
}

// HashRow 计算行内容哈希：按列名排序拼接 "pk\x00col=val"，sha256 hex
func HashRow(pk string, cols []string, vals []any) string {
	sorted := make([]string, len(cols))
	copy(sorted, cols)
	sort.Strings(sorted)
	// 建立列名→值映射
	m := make(map[string]any, len(cols))
	for i, c := range cols {
		if i < len(vals) {
			m[c] = vals[i]
		}
	}
	var sb strings.Builder
	sb.WriteString(pk)
	sb.WriteByte(0)
	for i, c := range sorted {
		if i > 0 {
			sb.WriteByte(0)
		}
		sb.WriteString(c)
		sb.WriteByte('=')
		sb.WriteString(infer.Stringify(m[c]))
	}
	sum := sha256.Sum256([]byte(sb.String()))
	return hex.EncodeToString(sum[:])
}

// PriorityIndex 返回 name 在优先级列表中的位置，不在则返回一个很大的数
func PriorityIndex(priority []string, name string) int {
	for i, p := range priority {
		if p == name {
			return i
		}
	}
	return 1 << 30
}

// Sync 执行一次同步。sourceNames 为空则同步全部源。
func Sync(cfg *config.Config, st *store.Store, sourceNames []string, jobName string) ([]SourceStats, error) {
	// 确定要同步的源列表
	var sources []config.SourceConfig
	if len(sourceNames) == 0 {
		sources = cfg.Sources
	} else {
		for _, n := range sourceNames {
			sc := cfg.SourceByName(n)
			if sc == nil {
				return nil, fmt.Errorf("源不存在: %s", n)
			}
			sources = append(sources, *sc)
		}
	}

	var allStats []SourceStats
	var firstErr error

	for _, sc := range sources {
		srcStats := SourceStats{Source: sc.Name}
		err := syncOneSource(cfg, st, sc, jobName, &srcStats)
		if err != nil {
			// 记录失败的 run
			jobLabel := jobName
			if !strings.Contains(jobName, sc.Name) {
				jobLabel = jobName + ":" + sc.Name
			}
			_ = st.RecordRun(store.RunRecord{
				Job:        jobLabel,
				StartedAt:  nowRFC3339(),
				FinishedAt: nowRFC3339(),
				Error:      err.Error(),
			})
			if firstErr == nil {
				firstErr = err
			}
			// 继续同步其他源，但保留错误
		}
		allStats = append(allStats, srcStats)
	}

	return allStats, firstErr
}

// syncOneSource 同步单个源
func syncOneSource(cfg *config.Config, st *store.Store, sc config.SourceConfig, jobName string, srcStats *SourceStats) error {
	startedAt := nowRFC3339()
	startTime := time.Now()

	src, err := connector.Open(sc)
	if err != nil {
		return fmt.Errorf("打开源失败 %s: %w", sc.Name, err)
	}
	defer src.Close()

	tables, err := src.Tables()
	if err != nil {
		return fmt.Errorf("列举源表失败 %s: %w", sc.Name, err)
	}

	// 判断是否为全量模式（Incremental 为空或未配置 column:X 时为全量）
	incrementalCol := ""
	if strings.HasPrefix(sc.Incremental, "column:") {
		incrementalCol = strings.TrimPrefix(sc.Incremental, "column:")
	}

	totalInserted := 0
	totalUpdated := 0
	totalDeleted := 0
	totalConflicts := 0

	for _, ti := range tables {
		ts, err := syncOneTable(cfg, st, src, sc, ti, incrementalCol)
		if err != nil {
			return fmt.Errorf("同步表失败 %s.%s: %w", sc.Name, ti.Name, err)
		}
		srcStats.Tables = append(srcStats.Tables, ts)
		totalInserted += ts.Inserted
		totalUpdated += ts.Updated
		totalDeleted += ts.Deleted
		totalConflicts += ts.Conflicts
	}

	// 记录本次 run（Job 带上源名，方便按源查询上次同步时间）
	jobLabel := jobName
	if !strings.Contains(jobName, sc.Name) {
		jobLabel = jobName + ":" + sc.Name
	}
	_ = st.RecordRun(store.RunRecord{
		Job:        jobLabel,
		StartedAt:  startedAt,
		FinishedAt: nowRFC3339(),
		Inserted:   totalInserted,
		Updated:    totalUpdated,
		Deleted:    totalDeleted,
		Conflicts:  totalConflicts,
	})

	// 指标埋点：按表累加 rows_total 各 op；记录 duration 与 runs_total{ok}
	m := metrics.Default()
	for _, ts := range srcStats.Tables {
		m.Add("mortise_sync_rows_total", float64(ts.Inserted), sc.Name, ts.Table, "inserted")
		m.Add("mortise_sync_rows_total", float64(ts.Updated), sc.Name, ts.Table, "updated")
		m.Add("mortise_sync_rows_total", float64(ts.Deleted), sc.Name, ts.Table, "deleted")
		m.Add("mortise_sync_rows_total", float64(ts.Skipped), sc.Name, ts.Table, "skipped")
		m.Add("mortise_sync_rows_total", float64(ts.Conflicts), sc.Name, ts.Table, "conflicts")
	}
	dur := time.Since(startTime).Seconds()
	m.Set("mortise_sync_last_duration_seconds", dur, sc.Name)
	m.Inc("mortise_sync_runs_total", jobLabel, "ok")

	return nil
}

// syncOneTable 同步单张表，返回统计
func syncOneTable(cfg *config.Config, st *store.Store, src connector.Source, sc config.SourceConfig, ti connector.TableInfo, incrementalCol string) (TableStats, error) {
	ts := TableStats{Table: ti.Name}

	// 确保目标表存在
	if err := st.EnsureTable(ti.Name, ti.Primary, ti.Columns); err != nil {
		return ts, fmt.Errorf("建表失败 %s: %w", ti.Name, err)
	}

	// 主键列
	pkCol := ti.Primary
	if pkCol == "" {
		// 尝试从列中找 Primary 标记
		for _, c := range ti.Columns {
			_ = c
		}
	}
	if pkCol == "" {
		return ts, fmt.Errorf("表 %s 缺少主键定义", ti.Name)
	}

	// 目标列名集合
	colNames := make([]string, 0, len(ti.Columns))
	for _, c := range ti.Columns {
		colNames = append(colNames, c.Name)
	}

	// 读水位线
	since := map[string]string{}
	if incrementalCol != "" {
		wm, err := st.GetWatermark(sc.Name, ti.Name, incrementalCol)
		if err != nil {
			return ts, fmt.Errorf("读水位线失败: %w", err)
		}
		if wm != "" {
			since[incrementalCol] = wm
		}
	}

	// 拉取行
	rows, err := src.Rows(ti.Name, since)
	if err != nil {
		return ts, fmt.Errorf("拉取行失败: %w", err)
	}

	// 全量模式下记录所有出现过的 pk，用于检测删除
	fullMode := len(since) == 0
	var seenPKs map[string]bool
	if fullMode {
		existing, err := st.ExistingPKs(ti.Name, pkCol, sc.Name)
		if err != nil {
			return ts, fmt.Errorf("读取已有主键失败: %w", err)
		}
		seenPKs = make(map[string]bool, len(existing))
		for k := range existing {
			seenPKs[k] = true
		}
	}

	// 记录水位线最大值
	maxWatermark := ""
	if incrementalCol != "" && len(since) > 0 {
		maxWatermark = since[incrementalCol]
	}

	// 批量事务：每 batchSize 行提交一次，大幅减少 WAL fsync 次数。
	// batchSize <= 0 时 validate 已置为 5000，这里再兜底一次。
	batchSize := cfg.Sync.BatchSize
	if batchSize <= 0 {
		batchSize = 5000
	}
	tx, err := st.DB.Begin()
	if err != nil {
		return ts, fmt.Errorf("开启批量事务失败: %w", err)
	}
	// 出错回滚并返回原错误
	rollback := func() { _ = tx.Rollback() }
	processed := 0
	commitBatch := func() error {
		if err := tx.Commit(); err != nil {
			return err
		}
		tx, err = st.DB.Begin()
		return err
	}

	for _, row := range rows {
		// 取出主键值
		pkRaw, ok := row[pkCol]
		if !ok || pkRaw == nil {
			// 无主键的行跳过
			ts.Skipped++
			continue
		}
		pk := infer.Stringify(pkRaw)

		// 收集列值（按 TableInfo.Columns 顺序）
		vals := make([]any, 0, len(colNames))
		for _, c := range colNames {
			vals = append(vals, row[c])
		}

		// 计算行哈希
		hash := HashRow(pk, colNames, vals)

		// 查询现有记录
		existHash, existSource, existDeleted, found, err := st.GetHash(tx, ti.Name, pkCol, pk)
		if err != nil {
			rollback()
			return ts, fmt.Errorf("查询已有哈希失败: %w", err)
		}

		if !found {
			// 插入
			if err := st.UpsertRow(tx, ti.Name, pkCol, pk, colNames, vals, hash, sc.Name); err != nil {
				rollback()
				return ts, fmt.Errorf("插入失败: %w", err)
			}
			ts.Inserted++
		} else if existDeleted || existHash != hash {
			// 内容变化或此前被标记删除 → 冲突判定
			if existSource != "" && existSource != sc.Name {
				// 跨源冲突
				conflictRow := buildRowJSON(pkCol, pk, colNames, vals)
				switch cfg.Sync.Conflict {
				case "priority":
					if PriorityIndex(cfg.Sync.Priority, sc.Name) < PriorityIndex(cfg.Sync.Priority, existSource) {
						// 本源优先，覆盖并记录自动解决
						if err := st.UpsertRow(tx, ti.Name, pkCol, pk, colNames, vals, hash, sc.Name); err != nil {
							rollback()
							return ts, fmt.Errorf("覆盖写入失败: %w", err)
						}
						ts.Updated++
						if _, err := st.RecordConflict(tx, store.Conflict{
							TableName: ti.Name,
							PK:        pk,
							SourceA:   existSource,
							SourceB:   sc.Name,
							RowJSON:   conflictRow,
							Status:    "resolved_auto",
							CreatedAt: nowRFC3339(),
						}); err != nil {
							rollback()
							return ts, fmt.Errorf("记录冲突失败: %w", err)
						}
					} else {
						// 本源优先级低，挂起冲突
						if _, err := st.RecordConflict(tx, store.Conflict{
							TableName: ti.Name,
							PK:        pk,
							SourceA:   existSource,
							SourceB:   sc.Name,
							RowJSON:   conflictRow,
							Status:    "pending",
							CreatedAt: nowRFC3339(),
						}); err != nil {
							rollback()
							return ts, fmt.Errorf("记录冲突失败: %w", err)
						}
						ts.Conflicts++
					}
				case "manual":
					// 手动模式，记录冲突并跳过
					if _, err := st.RecordConflict(tx, store.Conflict{
						TableName: ti.Name,
						PK:        pk,
						SourceA:   existSource,
						SourceB:   sc.Name,
						RowJSON:   conflictRow,
						Status:    "pending",
						CreatedAt: nowRFC3339(),
					}); err != nil {
						rollback()
						return ts, fmt.Errorf("记录冲突失败: %w", err)
					}
					ts.Conflicts++
				default:
					// 默认按 priority 处理
					if PriorityIndex(cfg.Sync.Priority, sc.Name) < PriorityIndex(cfg.Sync.Priority, existSource) {
						if err := st.UpsertRow(tx, ti.Name, pkCol, pk, colNames, vals, hash, sc.Name); err != nil {
							rollback()
							return ts, fmt.Errorf("覆盖写入失败: %w", err)
						}
						ts.Updated++
					} else {
						if _, err := st.RecordConflict(tx, store.Conflict{
							TableName: ti.Name,
							PK:        pk,
							SourceA:   existSource,
							SourceB:   sc.Name,
							RowJSON:   conflictRow,
							Status:    "pending",
							CreatedAt: nowRFC3339(),
						}); err != nil {
							rollback()
							return ts, fmt.Errorf("记录冲突失败: %w", err)
						}
						ts.Conflicts++
					}
				}
			} else {
				// 同源内容变化，直接更新；若该主键有 pending 冲突（此前他源挑战被挂起），
				// 本源重新写入视为自动胜出，标记 resolved_auto
				if err := st.UpsertRow(tx, ti.Name, pkCol, pk, colNames, vals, hash, sc.Name); err != nil {
					rollback()
					return ts, fmt.Errorf("更新失败: %w", err)
				}
				ts.Updated++
				if n, err := st.ResolveConflictsByPK(tx, ti.Name, pk, "resolved_auto"); err != nil {
					rollback()
					return ts, fmt.Errorf("自动解决冲突失败: %w", err)
				} else {
					ts.Conflicts += int(n)
				}
			}
		} else {
			// 哈希相同，跳过
			ts.Skipped++
		}

		if fullMode {
			delete(seenPKs, pk)
		}

		// 更新水位线最大值（字符串比较，要求 ISO8601）
		if incrementalCol != "" {
			if v, ok := row[incrementalCol]; ok && v != nil {
				sv := infer.Stringify(v)
				if sv > maxWatermark {
					maxWatermark = sv
				}
			}
		}

		// 批量提交
		processed++
		if processed%batchSize == 0 {
			if err := commitBatch(); err != nil {
				rollback()
				return ts, fmt.Errorf("批量提交失败: %w", err)
			}
		}
	}

	// 全量模式下处理删除
	if fullMode {
		for pk := range seenPKs {
			if cfg.Sync.SoftDelete {
				if err := st.MarkDeleted(tx, ti.Name, pkCol, pk); err != nil {
					rollback()
					return ts, fmt.Errorf("标记删除失败: %w", err)
				}
			} else {
				if err := st.DeleteRow(tx, ti.Name, pkCol, pk); err != nil {
					rollback()
					return ts, fmt.Errorf("删除失败: %w", err)
				}
			}
			ts.Deleted++
		}
	}

	// 提交最后一段批量事务；水位线在提交成功后写回
	if err := tx.Commit(); err != nil {
		rollback()
		return ts, fmt.Errorf("提交批量事务失败: %w", err)
	}
	// 写回水位线
	if incrementalCol != "" && maxWatermark != "" {
		if err := st.SetWatermark(sc.Name, ti.Name, incrementalCol, maxWatermark); err != nil {
			return ts, fmt.Errorf("写水位线失败: %w", err)
		}
	}

	return ts, nil
}

// buildRowJSON 构造待写入行的 JSON 字符串（含目标列与主键）
func buildRowJSON(pkCol, pk string, cols []string, vals []any) string {
	m := make(map[string]any, len(cols)+1)
	m[pkCol] = pk
	for i, c := range cols {
		if i < len(vals) {
			m[c] = vals[i]
		}
	}
	b, err := json.Marshal(m)
	if err != nil {
		return "{}"
	}
	return string(b)
}

func nowRFC3339() string {
	return time.Now().UTC().Format(time.RFC3339)
}
