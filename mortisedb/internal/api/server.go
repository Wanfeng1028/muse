// Package api 提供 MortiseDB 的 HTTP API 服务。
package api

import (
	"encoding/csv"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"net/http"
	"strconv"
	"strings"

	"github.com/Wanfeng1028/muse/mortisedb/internal/config"
	"github.com/Wanfeng1028/muse/mortisedb/internal/connector"
	"github.com/Wanfeng1028/muse/mortisedb/internal/infer"
	"github.com/Wanfeng1028/muse/mortisedb/internal/log"
	"github.com/Wanfeng1028/muse/mortisedb/internal/store"
	syncpkg "github.com/Wanfeng1028/muse/mortisedb/internal/sync"
	"github.com/Wanfeng1028/muse/mortisedb/internal/views"
	"github.com/Wanfeng1028/muse/mortisedb/internal/web"
)

// Version 为 API 版本号。
var Version = "0.1.0"

// server 保存 API 依赖。
type server struct {
	st     *store.Store
	cfg    *config.Config
	logger *log.Logger
}

// NewServer 构造 HTTP 处理器。
func NewServer(st *store.Store, cfg *config.Config, logger *log.Logger) http.Handler {
	s := &server{st: st, cfg: cfg, logger: logger}
	mux := http.NewServeMux()

	// 健康检查
	mux.HandleFunc("GET /api/health", s.handleHealth)
	// 数据源列表
	mux.HandleFunc("GET /api/sources", s.handleSources)
	// 手动同步
	mux.HandleFunc("POST /api/sync", s.handleSync)
	// 运行记录
	mux.HandleFunc("GET /api/runs", s.handleRuns)
	// 冲突列表
	mux.HandleFunc("GET /api/conflicts", s.handleConflicts)
	// 冲突解决
	mux.HandleFunc("POST /api/conflicts/{id}/resolve", s.handleResolveConflict)
	// 表列表
	mux.HandleFunc("GET /api/tables", s.handleTables)
	// 表数据
	mux.HandleFunc("GET /api/tables/{name}/rows", s.handleTableRows)
	// 视图
	mux.HandleFunc("GET /api/views", s.handleListViews)
	mux.HandleFunc("POST /api/views", s.handleAddView)
	mux.HandleFunc("DELETE /api/views/{name}", s.handleDropView)
	mux.HandleFunc("GET /api/views/{name}/rows", s.handleViewRows)
	// 自由查询
	mux.HandleFunc("POST /api/query", s.handleQuery)

	// 静态资源与首页
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServerFS(web.StaticFS())))
	mux.HandleFunc("GET /", s.handleIndex)

	// 包装请求 ID 中间件
	return log.RequestIDMiddleware(mux, logger)
}

// writeJSON 写出 JSON 响应。
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError 写出统一错误响应。
func writeError(w http.ResponseWriter, status int, err error) {
	writeJSON(w, status, map[string]string{"error": err.Error()})
}

// handleHealth 返回健康状态。
func (s *server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "version": Version})
}

// sourceTableInfo 数据源表信息。
type sourceTableInfo struct {
	Name    string `json:"name"`
	Rows    int64  `json:"rows"`
	Primary string `json:"primary"`
}

// sourceInfo 数据源信息。
type sourceInfo struct {
	Name     string            `json:"name"`
	Type     string            `json:"type"`
	Path     string            `json:"path"`
	Tables   []sourceTableInfo `json:"tables"`
	LastSync string            `json:"last_sync"`
}

// handleSources 返回数据源列表。
func (s *server) handleSources(w http.ResponseWriter, r *http.Request) {
	result := make([]sourceInfo, 0, len(s.cfg.Sources))
	for i := range s.cfg.Sources {
		sc := s.cfg.Sources[i]
		info := sourceInfo{Name: sc.Name, Type: sc.Type, Path: sc.Path, Tables: []sourceTableInfo{}}

		// 尝试打开连接器获取表结构
		conn, err := openSource(sc)
		if err != nil {
			s.logger.Warn("打开数据源失败", map[string]any{"source": sc.Name, "error": err.Error()})
			info.LastSync = s.lastSync(sc.Name)
			result = append(result, info)
			continue
		}
		tables, terr := conn.Tables()
		_ = conn.Close()
		if terr != nil {
			s.logger.Warn("列举数据源表失败", map[string]any{"source": sc.Name, "error": terr.Error()})
			info.LastSync = s.lastSync(sc.Name)
			result = append(result, info)
			continue
		}
		for _, t := range tables {
			cnt, _ := s.st.TableCount(t.Name)
			info.Tables = append(info.Tables, sourceTableInfo{Name: t.Name, Rows: cnt, Primary: t.Primary})
		}
		info.LastSync = s.lastSync(sc.Name)
		result = append(result, info)
	}
	writeJSON(w, http.StatusOK, result)
}

// lastSync 从运行记录里取该源最新完成时间。
func (s *server) lastSync(source string) string {
	runs, err := s.st.ListRuns(200)
	if err != nil {
		return ""
	}
	for _, r := range runs {
		if r.Job == source || strings.Contains(r.Job, source) {
			if r.FinishedAt != "" {
				return r.FinishedAt
			}
		}
	}
	return ""
}

// handleSync 执行手动同步。
func (s *server) handleSync(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Sources []string `json:"sources"`
		Job     string   `json:"job"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("解析请求失败: %w", err))
		return
	}
	if req.Job == "" {
		req.Job = "manual"
	}
	stats, err := syncpkg.Sync(s.cfg, s.st, req.Sources, req.Job)
	if err != nil {
		s.logger.Error("同步失败", map[string]any{"job": req.Job, "error": err.Error()})
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"stats": stats})
}

// handleRuns 返回运行记录。
func (s *server) handleRuns(w http.ResponseWriter, r *http.Request) {
	limit := parseLimit(r.URL.Query().Get("limit"), 50)
	runs, err := s.st.ListRuns(limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, runs)
}

// handleConflicts 返回冲突列表。
func (s *server) handleConflicts(w http.ResponseWriter, r *http.Request) {
	status := r.URL.Query().Get("status")
	conflicts, err := s.st.ListConflicts(status)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, conflicts)
}

// handleResolveConflict 解决冲突。
func (s *server) handleResolveConflict(w http.ResponseWriter, r *http.Request) {
	idStr := r.PathValue("id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("非法冲突 id: %w", err))
		return
	}

	var req struct {
		RowJSON string `json:"row_json"`
		Table   string `json:"table"`
		PKCol   string `json:"pk_col"`
		PK      string `json:"pk"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("解析请求失败: %w", err))
		return
	}
	if req.Table == "" || req.PKCol == "" {
		writeError(w, http.StatusBadRequest, errors.New("table 与 pk_col 不能为空"))
		return
	}

	// 解析 row_json
	var rowMap map[string]any
	if err := json.Unmarshal([]byte(req.RowJSON), &rowMap); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("解析 row_json 失败: %w", err))
		return
	}

	// 查找该表的列顺序
	cols, _, err := s.st.Query(fmt.Sprintf(`SELECT * FROM "%s" LIMIT 0`, escapeIdent(req.Table)))
	if err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("查询表结构失败: %w", err))
		return
	}

	// 按表列顺序拆出 cols/vals（跳过内部元数据列，缺失填 nil）
	outCols := make([]string, 0, len(cols))
	outVals := make([]any, 0, len(cols))
	for _, c := range cols {
		if strings.HasPrefix(c, "_m_") {
			continue
		}
		outCols = append(outCols, c)
		if v, ok := rowMap[c]; ok {
			outVals = append(outVals, v)
		} else {
			outVals = append(outVals, nil)
		}
	}

	// 从冲突记录中取 source_b 作为写入来源
	conflicts, err := s.st.ListConflicts("")
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	sourceB := ""
	for _, c := range conflicts {
		if c.ID == id {
			sourceB = c.SourceB
			break
		}
	}

	// 重算 hash
	hash := syncpkg.HashRow(req.PK, outCols, outVals)

	// 执行 upsert
	if err := s.st.UpsertRow(req.Table, req.PKCol, req.PK, outCols, outVals, hash, sourceB); err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Errorf("写入冲突行失败: %w", err))
		return
	}

	if err := s.st.ResolveConflict(id, "resolved"); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "resolved"})
}

// tableSummary 表信息。
type tableSummary struct {
	Name string `json:"name"`
	Rows int64  `json:"rows"`
}

// handleTables 返回所有用户表。
func (s *server) handleTables(w http.ResponseWriter, r *http.Request) {
	names, err := s.st.Tables()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	out := make([]tableSummary, 0, len(names))
	for _, n := range names {
		cnt, _ := s.st.TableCount(n)
		out = append(out, tableSummary{Name: n, Rows: cnt})
	}
	writeJSON(w, http.StatusOK, out)
}

// handleTableRows 返回某表数据。
func (s *server) handleTableRows(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
	limit := parseLimit(r.URL.Query().Get("limit"), 100)
	offset := parseLimit(r.URL.Query().Get("offset"), 0)

	total, err := s.st.TableCount(name)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	cols, rows, err := s.st.Query(
		fmt.Sprintf(`SELECT * FROM "%s" WHERE _m_deleted=0 LIMIT ? OFFSET ?`, escapeIdent(name)),
		limit, offset,
	)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"columns": cols,
		"rows":    rows,
		"total":   total,
	})
}

// handleListViews 返回视图列表。
func (s *server) handleListViews(w http.ResponseWriter, r *http.Request) {
	vs, err := s.st.ListViews()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, vs)
}

// handleAddView 新增视图。
func (s *server) handleAddView(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Name        string `json:"name"`
		SQL         string `json:"sql"`
		Description string `json:"description"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("解析请求失败: %w", err))
		return
	}
	if req.Name == "" {
		writeError(w, http.StatusBadRequest, errors.New("name 不能为空"))
		return
	}
	if err := views.Add(s.st, req.Name, req.SQL, req.Description); err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// handleDropView 删除视图。
func (s *server) handleDropView(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
	if err := s.st.DropView(name); err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// handleViewRows 执行视图查询。
func (s *server) handleViewRows(w http.ResponseWriter, r *http.Request) {
	name := r.PathValue("name")
	format := r.URL.Query().Get("format")
	limit := parseLimit(r.URL.Query().Get("limit"), 500)

	cols, rows, err := views.Run(s.st, name, limit)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err)
		return
	}

	if format == "csv" {
		w.Header().Set("Content-Type", "text/csv; charset=utf-8")
		w.WriteHeader(http.StatusOK)
		cw := csv.NewWriter(w)
		if err := cw.Write(cols); err != nil {
			s.logger.Error("写 CSV 表头失败", map[string]any{"error": err.Error()})
			return
		}
		for _, row := range rows {
			rec := make([]string, len(row))
			for i, v := range row {
				rec[i] = infer.Stringify(v)
			}
			if err := cw.Write(rec); err != nil {
				s.logger.Error("写 CSV 行失败", map[string]any{"error": err.Error()})
				return
			}
		}
		cw.Flush()
		return
	}

	writeJSON(w, http.StatusOK, map[string]any{"columns": cols, "rows": rows})
}

// handleQuery 执行自由查询。
func (s *server) handleQuery(w http.ResponseWriter, r *http.Request) {
	var req struct {
		SQL   string `json:"sql"`
		Limit int    `json:"limit"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, fmt.Errorf("解析请求失败: %w", err))
		return
	}
	if req.Limit <= 0 {
		req.Limit = 500
	}
	cols, rows, err := s.st.Query(req.SQL)
	if err != nil {
		writeError(w, http.StatusBadRequest, err)
		return
	}
	// 截断到 limit
	if len(rows) > req.Limit {
		rows = rows[:req.Limit]
	}
	writeJSON(w, http.StatusOK, map[string]any{"columns": cols, "rows": rows})
}

// handleIndex 返回首页。
func (s *server) handleIndex(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	data, err := fs.ReadFile(web.StaticFS(), "index.html")
	if err != nil {
		writeError(w, http.StatusInternalServerError, fmt.Errorf("读取首页失败: %w", err))
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

// parseLimit 解析数字参数。
func parseLimit(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 {
		return def
	}
	return n
}

// escapeIdent 转义 SQL 标识符（双引号内转义双引号）。
func escapeIdent(s string) string {
	return strings.ReplaceAll(s, `"`, `""`)
}

// openSource 打开数据源连接器。
func openSource(cfg config.SourceConfig) (connector.Source, error) {
	return connector.Open(cfg)
}
