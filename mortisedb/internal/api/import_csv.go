package api

import (
	"crypto/sha256"
	"database/sql"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/notify"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
)

const (
	importCSVMaxFileBytes = 32 << 20
	importCSVMaxDataRows  = 100000
	importCSVMaxErrors    = 100
)

type importCSVError struct {
	Line   int    `json:"line"`
	Reason string `json:"reason"`
}

type importCSVResult struct {
	Source           string           `json:"source"`
	Table            string           `json:"table"`
	FileHash         string           `json:"file_hash"`
	Filename         string           `json:"filename"`
	Duplicate        bool             `json:"duplicate"`
	TotalRows        int              `json:"total_rows"`
	Inserted         int              `json:"inserted"`
	Updated          int              `json:"updated"`
	Unchanged        int              `json:"unchanged"`
	ErrorRows        int              `json:"error_rows"`
	Errors           []importCSVError `json:"errors"`
	ErrorsTruncated  bool             `json:"errors_truncated"`
	ConflictsPending int              `json:"conflicts_pending"`
	Conflicts        []store.Conflict `json:"conflicts,omitempty"`
}

// importCSV 执行 CSV 增量导入。st 已打开；sourceName 为数据源名称；r 为文件内容；filename 为文件名。
// 兼容旧端点：默认选项走流式实现。
func importCSV(st *store.Store, cfg *config.Config, sourceName string, r io.Reader, filename string) (importCSVResult, error) {
	return importCSVStream(st, cfg, sourceName, r, filename, importCSVOptions{})
}

func importCSVStream(st *store.Store, cfg *config.Config, sourceName string, r io.Reader, filename string, opts importCSVOptions) (importCSVResult, error) {
	var res importCSVResult
	res.Source = sourceName
	res.Filename = filename
	res.Errors = []importCSVError{}

	var sc *config.SourceConfig
	for i := range cfg.Sources {
		if cfg.Sources[i].Name == sourceName {
			sc = &cfg.Sources[i]
			break
		}
	}
	if sc == nil {
		return res, errImportSourceNotFound
	}

	table := strings.TrimSpace(opts.Table)
	if table == "" {
		table = sc.Table
	}
	pkCol := strings.TrimSpace(opts.PrimaryKey)
	if pkCol == "" {
		pkCol = sc.PrimaryKey
	}
	if strings.TrimSpace(table) == "" || strings.TrimSpace(pkCol) == "" {
		return res, errImportSourceNotConfigured
	}
	res.Table = table

	tmpDir := filepath.Join(filepath.Dir(cfg.Database), ".import-tmp")
	if err := os.MkdirAll(tmpDir, 0o755); err != nil {
		return res, err
	}
	tmpFile, err := os.CreateTemp(tmpDir, "import-*.csv")
	if err != nil {
		return res, err
	}
	defer os.Remove(tmpFile.Name())

	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(tmpFile, h), io.LimitReader(r, importCSVMaxFileBytes+1))
	if err != nil {
		return res, err
	}
	if n > importCSVMaxFileBytes {
		return res, errImportFileTooLarge
	}
	if err := tmpFile.Close(); err != nil {
		return res, err
	}
	res.FileHash = hex.EncodeToString(h.Sum(nil))

	found, summary, err := st.FindImport(sourceName, res.FileHash)
	if err != nil {
		return res, err
	}
	if found {
		res.Duplicate = true
		if v, ok := summary["filename"].(string); ok {
			res.Filename = v
		}
		if v, ok := summary["rows_total"].(int); ok {
			res.TotalRows = v
		}
		if v, ok := summary["inserted"].(int); ok {
			res.Inserted = v
		}
		if v, ok := summary["updated"].(int); ok {
			res.Updated = v
		}
		if v, ok := summary["error_rows"].(int); ok {
			res.ErrorRows = v
		}
		return res, nil
	}

	f, err := os.Open(tmpFile.Name())
	if err != nil {
		return res, err
	}
	defer f.Close()

	cr := csv.NewReader(f)
	cr.FieldsPerRecord = -1
	cr.TrimLeadingSpace = true
	cr.LazyQuotes = false

	header, err := cr.Read()
	if err != nil {
		if err == io.EOF {
			return res, errImportEmptyFile
		}
		return res, fmt.Errorf("读取表头失败: %w", err)
	}

	colNames := make([]string, 0, len(header))
	seen := make(map[string]bool, len(header))
	for _, raw := range header {
		name := strings.TrimSpace(raw)
		target := name
		if opts.ColumnMapping != nil {
			if mapped, ok := opts.ColumnMapping[name]; ok {
				target = strings.TrimSpace(mapped)
			}
		}
		if target == "" {
			return res, errImportEmptyColumn
		}
		if !importCSVTargetColRe.MatchString(target) {
			return res, errImportInvalidColumnName
		}
		if seen[target] {
			return res, errImportDuplicateColumn
		}
		seen[target] = true
		colNames = append(colNames, target)
	}

	pkIdx := -1
	for i, n := range colNames {
		if n == pkCol {
			pkIdx = i
			break
		}
	}
	if pkIdx < 0 {
		return res, errImportPrimaryKeyMissing
	}

	cols := make([]infer.Column, 0, len(colNames))
	for _, n := range colNames {
		cols = append(cols, infer.Column{Name: n, Type: "TEXT"})
	}
	if err := st.EnsureTable(table, pkCol, cols); err != nil {
		return res, err
	}

	tx, err := st.DB.Begin()
	if err != nil {
		return res, err
	}
	committed := false
	defer func() {
		if !committed {
			_ = tx.Rollback()
		}
	}()

	line := 1
	for {
		row, err := cr.Read()
		if err == io.EOF {
			break
		}
		line++
		if err != nil {
			res.ErrorRows++
			if len(res.Errors) < importCSVMaxErrors {
				res.Errors = append(res.Errors, importCSVError{Line: line, Reason: err.Error()})
			} else {
				res.ErrorsTruncated = true
			}
			continue
		}
		if len(row) != len(colNames) {
			res.ErrorRows++
			reason := fmt.Sprintf("列数不符：期望 %d，实际 %d", len(colNames), len(row))
			if len(res.Errors) < importCSVMaxErrors {
				res.Errors = append(res.Errors, importCSVError{Line: line, Reason: reason})
			} else {
				res.ErrorsTruncated = true
			}
			continue
		}
		pk := strings.TrimSpace(row[pkIdx])
		if pk == "" {
			res.ErrorRows++
			if len(res.Errors) < importCSVMaxErrors {
				res.Errors = append(res.Errors, importCSVError{Line: line, Reason: "主键为空"})
			} else {
				res.ErrorsTruncated = true
			}
			continue
		}
		if res.TotalRows >= importCSVMaxDataRows {
			return res, errImportTooManyRows
		}
		res.TotalRows++

		vals := make([]any, len(colNames))
		for i, v := range row {
			vals[i] = v
		}
		hash := syncpkg.HashRow(pk, colNames, vals)

		action, pending, err := decideUpsert(tx, st, cfg, table, pkCol, pk, colNames, vals, hash, sourceName)
		if err != nil {
			return res, err
		}
		switch action {
		case "inserted":
			res.Inserted++
		case "updated":
			res.Updated++
		case "unchanged":
			res.Unchanged++
		case "conflict":
			res.ConflictsPending++
			if pending != nil {
				res.Conflicts = append(res.Conflicts, *pending)
			}
		}
	}

	if err := tx.Commit(); err != nil {
		return res, err
	}
	committed = true

	if err := st.RecordImport(sourceName, res.FileHash, res.Filename, res.TotalRows, res.Inserted, res.Updated, res.ErrorRows); err != nil {
		return res, err
	}
	return res, nil
}

// decideUpsert 执行逐行 upsert 决策，返回动作 "inserted"/"updated"/"unchanged"/"conflict"。
// 冲突策略（cfg.Sync.Conflict）语义与 sync.go 完全一致：
//   - "manual"：跨源（existSource 非空且与本源不同）且行哈希不同 → 不覆盖，
//     写入 _m_conflicts（SourceA=现有方来源名，SourceB=挑战方来源名，
//     RowJSON=挑战方行数据 JSON，Status=pending），返回 "conflict" 及该冲突记录。
//   - "priority"：复用 syncpkg.PriorityIndex 按源优先级裁决；本源优先则覆盖并记录
//     resolved_auto 冲突，返回 "updated"；否则挂起 pending 冲突，返回 "conflict"。
//   - 其他值：默认按 "priority" 处理（与 sync.go 一致；本源优先时只覆盖不额外记录冲突）。
//   - 同源（existSource 为空或与本源相同）内容变化：直接覆盖，并将该主键的 pending
//     冲突标记为 resolved_auto，返回 "updated"。
func decideUpsert(tx *sql.Tx, st *store.Store, cfg *config.Config, table, pkCol, pk string, colNames []string, vals []any, hash, source string) (string, *store.Conflict, error) {
	prevHash, existSource, _, found, err := st.GetHash(tx, table, pkCol, pk)
	if err != nil {
		return "", nil, err
	}
	if !found {
		if err := st.UpsertRow(tx, table, pkCol, pk, colNames, vals, hash, source); err != nil {
			return "", nil, err
		}
		return "inserted", nil, nil
	}
	if prevHash == hash {
		return "unchanged", nil, nil
	}
	// 主键已存在且行哈希不同 → 冲突判定
	if existSource != "" && existSource != source {
		rowJSON := importBuildRowJSON(pkCol, pk, colNames, vals)
		newConflict := func(status string) store.Conflict {
			return store.Conflict{
				TableName: table,
				PK:        pk,
				SourceA:   existSource,
				SourceB:   source,
				RowJSON:   rowJSON,
				Status:    status,
				CreatedAt: time.Now().UTC().Format(time.RFC3339),
			}
		}
		recordPending := func() (*store.Conflict, error) {
			c := newConflict("pending")
			id, err := st.RecordConflict(tx, c)
			if err != nil {
				return nil, err
			}
			c.ID = id
			return &c, nil
		}
		switch cfg.Sync.Conflict {
		case "priority":
			if syncpkg.PriorityIndex(cfg.Sync.Priority, source) < syncpkg.PriorityIndex(cfg.Sync.Priority, existSource) {
				// 本源优先，覆盖并记录自动解决
				if err := st.UpsertRow(tx, table, pkCol, pk, colNames, vals, hash, source); err != nil {
					return "", nil, err
				}
				if _, err := st.RecordConflict(tx, newConflict("resolved_auto")); err != nil {
					return "", nil, err
				}
				return "updated", nil, nil
			}
			// 本源优先级低，挂起冲突
			c, err := recordPending()
			if err != nil {
				return "", nil, err
			}
			return "conflict", c, nil
		case "manual":
			// 手动模式，记录冲突并跳过（不覆盖）
			c, err := recordPending()
			if err != nil {
				return "", nil, err
			}
			return "conflict", c, nil
		default:
			// 默认按 priority 处理（与 sync.go 一致）
			if syncpkg.PriorityIndex(cfg.Sync.Priority, source) < syncpkg.PriorityIndex(cfg.Sync.Priority, existSource) {
				if err := st.UpsertRow(tx, table, pkCol, pk, colNames, vals, hash, source); err != nil {
					return "", nil, err
				}
				return "updated", nil, nil
			}
			c, err := recordPending()
			if err != nil {
				return "", nil, err
			}
			return "conflict", c, nil
		}
	}
	// 同源内容变化，直接更新；该主键的 pending 冲突视为自动胜出
	if err := st.UpsertRow(tx, table, pkCol, pk, colNames, vals, hash, source); err != nil {
		return "", nil, err
	}
	if _, err := st.ResolveConflictsByPK(tx, table, pk, "resolved_auto"); err != nil {
		return "", nil, err
	}
	return "updated", nil, nil
}

// importBuildRowJSON 构造挑战方行数据的 JSON（形状与 sync.buildRowJSON 一致：主键与各目标列）。
func importBuildRowJSON(pkCol, pk string, cols []string, vals []any) string {
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

var (
	errImportSourceNotFound      = errors.New("数据源不存在")
	errImportSourceNotConfigured = errors.New("该数据源未配置 table/primary_key，无法导入")
	errImportFileTooLarge        = errors.New("文件超过 32MB 限制")
	errImportTooManyRows         = errors.New("数据行超过 100000 限制")
	errImportEmptyFile           = errors.New("文件为空")
	errImportEmptyColumn         = errors.New("表头存在空列名")
	errImportDuplicateColumn     = errors.New("表头存在重复列名")
	errImportPrimaryKeyMissing   = errors.New("表头未包含主键列")
)

var importCSVTargetColRe = regexp.MustCompile(`^[A-Za-z_][A-Za-z0-9_]*$`)

var (
	errImportInvalidColumnName = errors.New("映射后列名非法：必须以字母或下划线开头，后跟字母、数字或下划线")
	errImportInvalidMapping    = errors.New("column_mapping 必须是 JSON 对象")
	errImportMissingSource     = errors.New("缺少 source 参数")
)

type importCSVOptions struct {
	Table         string
	PrimaryKey    string
	ColumnMapping map[string]string
}

func (s *server) handleImportCSV(w http.ResponseWriter, r *http.Request) {
	// 冲突 webhook 回查的起始时间（RFC3339 秒级；同秒边界可能多投，接收端按 delivery_id 去重）
	importStartedAt := time.Now().UTC().Format(time.RFC3339)
	id := r.PathValue("id")
	if id == "" {
		writeError(w, http.StatusBadRequest, errors.New("缺少数据源名称"))
		return
	}
	if err := r.ParseMultipartForm(importCSVMaxFileBytes); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	f, hdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	defer f.Close()

	res, err := importCSV(s.st, s.cfg, id, f, hdr.Filename)
	if err != nil {
		switch {
		case errors.Is(err, errImportSourceNotFound):
			writeError(w, http.StatusNotFound, err)
		case errors.Is(err, errImportSourceNotConfigured),
			errors.Is(err, errImportFileTooLarge),
			errors.Is(err, errImportTooManyRows),
			errors.Is(err, errImportEmptyFile),
			errors.Is(err, errImportEmptyColumn),
			errors.Is(err, errImportDuplicateColumn),
			errors.Is(err, errImportPrimaryKeyMissing):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusInternalServerError, err)
		}
		return
	}

	// 冲突 webhook：importCSV 内事务已提交；回查本表本次新增的冲突（pending/自动解决）异步投递
	notify.FromConfig(s.cfg, s.logger).FireTableConflicts(s.st, res.Table, importStartedAt)

	if len(res.Conflicts) > 0 {
		s.logger.Info("CSV 导入存在挂起冲突", map[string]any{
			"source":            res.Source,
			"table":             res.Table,
			"conflicts_pending": res.ConflictsPending,
		})
		writeJSON(w, http.StatusConflict, res.Conflicts)
		return
	}

	if !res.Duplicate {
		s.logger.Info("CSV 导入完成", map[string]any{
			"source":     res.Source,
			"table":      res.Table,
			"inserted":   res.Inserted,
			"updated":    res.Updated,
			"error_rows": res.ErrorRows,
		})
	}

	writeJSON(w, http.StatusOK, res)
}

func (s *server) handleImportCSVNew(w http.ResponseWriter, r *http.Request) {
	// 冲突 webhook 回查的起始时间（RFC3339 秒级；同秒边界可能多投，接收端按 delivery_id 去重）
	importStartedAt := time.Now().UTC().Format(time.RFC3339)
	if err := r.ParseMultipartForm(importCSVMaxFileBytes); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	f, hdr, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	defer f.Close()

	source := strings.TrimSpace(r.FormValue("source"))
	if source == "" {
		writeError(w, http.StatusBadRequest, errImportMissingSource)
		return
	}

	opts := importCSVOptions{
		Table:      strings.TrimSpace(r.FormValue("table")),
		PrimaryKey: strings.TrimSpace(r.FormValue("primary_key")),
	}

	mappingRaw := strings.TrimSpace(r.FormValue("column_mapping"))
	if mappingRaw != "" {
		var m map[string]string
		if err := json.Unmarshal([]byte(mappingRaw), &m); err != nil {
			writeError(w, http.StatusBadRequest, errImportInvalidMapping)
			return
		}
		opts.ColumnMapping = m
	}

	res, err := importCSVStream(s.st, s.cfg, source, f, hdr.Filename, opts)
	if err != nil {
		switch {
		case errors.Is(err, errImportSourceNotFound):
			writeError(w, http.StatusNotFound, err)
		case errors.Is(err, errImportFileTooLarge):
			writeError(w, http.StatusRequestEntityTooLarge, err)
		case errors.Is(err, errImportSourceNotConfigured),
			errors.Is(err, errImportTooManyRows),
			errors.Is(err, errImportEmptyFile),
			errors.Is(err, errImportEmptyColumn),
			errors.Is(err, errImportDuplicateColumn),
			errors.Is(err, errImportPrimaryKeyMissing),
			errors.Is(err, errImportInvalidColumnName),
			errors.Is(err, errImportInvalidMapping),
			errors.Is(err, errImportMissingSource):
			writeError(w, http.StatusBadRequest, err)
		default:
			writeError(w, http.StatusInternalServerError, err)
		}
		return
	}

	// 冲突 webhook：importCSVStream 内事务已提交；回查本表本次新增的冲突（pending/自动解决）异步投递
	notify.FromConfig(s.cfg, s.logger).FireTableConflicts(s.st, res.Table, importStartedAt)

	if len(res.Conflicts) > 0 {
		s.logger.Info("CSV 导入存在挂起冲突", map[string]any{
			"source":            res.Source,
			"table":             res.Table,
			"conflicts_pending": res.ConflictsPending,
		})
		writeJSON(w, http.StatusConflict, res.Conflicts)
		return
	}

	if !res.Duplicate {
		s.logger.Info("CSV 导入完成", map[string]any{
			"source":     res.Source,
			"table":      res.Table,
			"inserted":   res.Inserted,
			"updated":    res.Updated,
			"error_rows": res.ErrorRows,
		})
	}

	writeJSON(w, http.StatusOK, res)
}
