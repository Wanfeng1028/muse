package api

import (
	"crypto/sha256"
	"encoding/csv"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
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
	Source          string           `json:"source"`
	Table           string           `json:"table"`
	FileHash        string           `json:"file_hash"`
	Filename        string           `json:"filename"`
	Duplicate       bool             `json:"duplicate"`
	TotalRows       int              `json:"total_rows"`
	Inserted        int              `json:"inserted"`
	Updated         int              `json:"updated"`
	Unchanged       int              `json:"unchanged"`
	ErrorRows       int              `json:"error_rows"`
	Errors          []importCSVError `json:"errors"`
	ErrorsTruncated bool             `json:"errors_truncated"`
}

// importCSV 执行 CSV 增量导入。st 已打开；sourceName 为数据源名称；r 为文件内容；filename 为文件名。
func importCSV(st *store.Store, cfg *config.Config, sourceName string, r io.Reader, filename string) (importCSVResult, error) {
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
	if strings.TrimSpace(sc.Table) == "" || strings.TrimSpace(sc.PrimaryKey) == "" {
		return res, errImportSourceNotConfigured
	}
	res.Table = sc.Table

	data, err := io.ReadAll(io.LimitReader(r, importCSVMaxFileBytes+1))
	if err != nil {
		return res, err
	}
	if len(data) > importCSVMaxFileBytes {
		return res, errImportFileTooLarge
	}

	sum := sha256.Sum256(data)
	res.FileHash = hex.EncodeToString(sum[:])

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

	cr := csv.NewReader(strings.NewReader(string(data)))
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
	for _, h := range header {
		name := strings.TrimSpace(h)
		if name == "" {
			return res, errImportEmptyColumn
		}
		if seen[name] {
			return res, errImportDuplicateColumn
		}
		seen[name] = true
		colNames = append(colNames, name)
	}

	pkCol := sc.PrimaryKey
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
	if err := st.EnsureTable(sc.Table, pkCol, cols); err != nil {
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

		prevHash, _, _, found, err := st.GetHash(tx, sc.Table, pkCol, pk)
		if err != nil {
			return res, err
		}
		if found && prevHash == hash {
			res.Unchanged++
			continue
		}
		if err := st.UpsertRow(tx, sc.Table, pkCol, pk, colNames, vals, hash, sourceName); err != nil {
			return res, err
		}
		if found {
			res.Updated++
		} else {
			res.Inserted++
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

func (s *server) handleImportCSV(w http.ResponseWriter, r *http.Request) {
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
