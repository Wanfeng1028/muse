package handlers

import (
	"encoding/json"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"sentinel/internal/middleware"
	"sentinel/internal/store"
)

// RegisterSoulRoutes 注册 profile / SLA / 状态页相关路由。
// 需要在 handlers.go 的 Routes() 末尾（返回 mux 之前）调用：
//
//	s.RegisterSoulRoutes(mux)
//
// 注册的 9 条路由：
//
//	GET    /api/monitors/{id}/profile
//	GET    /api/monitors/{id}/sla
//	PUT    /api/monitors/{id}/public
//	POST   /api/status-pages
//	GET    /api/status-pages
//	DELETE /api/status-pages/{id}
//	POST   /api/status-pages/{id}/monitors
//	DELETE /api/status-pages/{id}/monitors/{monitor_id}
//	POST   /api/status-pages/auto
//	GET    /api/status/{slug}          （公开，白名单已含 /api/status/ 前缀）
func (s *Server) RegisterSoulRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/monitors/{id}/profile", s.handleMonitorProfile)
	mux.HandleFunc("GET /api/monitors/{id}/sla", s.handleMonitorSLA)
	mux.HandleFunc("PUT /api/monitors/{id}/public", s.handleMonitorSetPublic)

	mux.HandleFunc("POST /api/status-pages", s.handleCreateStatusPage)
	mux.HandleFunc("GET /api/status-pages", s.handleListStatusPages)
	mux.HandleFunc("DELETE /api/status-pages/{id}", s.handleDeleteStatusPage)
	mux.HandleFunc("POST /api/status-pages/{id}/monitors", s.handleAddPageMonitor)
	mux.HandleFunc("DELETE /api/status-pages/{id}/monitors/{monitor_id}", s.handleRemovePageMonitor)
	mux.HandleFunc("POST /api/status-pages/auto", s.handleAutoStatusPage)

	// 公开路由。
	mux.HandleFunc("GET /api/status/{slug}", s.handlePublicStatus)
}

// parsePathID 从路径参数读取 int64 ID。
func parsePathID(r *http.Request, name string) (int64, bool) {
	raw := r.PathValue(name)
	if raw == "" {
		return 0, false
	}
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		return 0, false
	}
	return id, true
}

var statusPageSlugRe = regexp.MustCompile(`^[a-z0-9-]{1,64}$`)

// handleMonitorProfile 返回 monitor 的聚合画像。
func (s *Server) handleMonitorProfile(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		return
	}
	m, err := s.store.GetMonitor(id)
	if err != nil {
		writeErr(w, http.StatusNotFound, "monitor 不存在")
		return
	}

	up7, _, _, _, err := s.store.MonitorStats(id, 7)
	if err != nil {
		logErr(r, "handleMonitorProfile", err)
	}
	up30, _, _, incidents30, err := s.store.MonitorStats(id, 30)
	if err != nil {
		logErr(r, "handleMonitorProfile", err)
	}

	p50, p95, p99, err := s.store.LatencyPercentiles(id, 30)
	if err != nil {
		logErr(r, "handleMonitorProfile", err)
	}

	daily, err := s.store.DailyBreakdown(id, 30)
	if err != nil {
		logErr(r, "handleMonitorProfile", err)
	}
	if daily == nil {
		daily = []store.DayStat{}
	}

	var current any = nil
	var certDays any = nil
	last, err := s.store.LastCheck(id)
	if err == nil && last != nil {
		current = checkJSON(*last)
		if last.CertDaysLeft.Valid {
			certDays = last.CertDaysLeft.Int64
		}
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"monitor":        monitorJSON(m),
		"uptime_7d":      up7,
		"uptime_30d":     up30,
		"latency":        map[string]any{"p50": p50, "p95": p95, "p99": p99},
		"incidents_30d":  incidents30,
		"current":        current,
		"cert_days_left": certDays,
		"daily":          daily,
	})
}

// handleMonitorSLA 返回指定月份的 SLA 报告。
func (s *Server) handleMonitorSLA(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		writeErr(w, http.StatusNotFound, "monitor 不存在")
		return
	}

	month := r.URL.Query().Get("month")
	now := time.Now().UTC()
	year, mon := now.Year(), int(now.Month())
	if month != "" {
		parts := strings.SplitN(month, "-", 2)
		if len(parts) != 2 {
			writeErr(w, http.StatusBadRequest, "month 格式应为 YYYY-MM")
			return
		}
		y, err1 := strconv.Atoi(parts[0])
		mn, err2 := strconv.Atoi(parts[1])
		if err1 != nil || err2 != nil || mn < 1 || mn > 12 || y < 1970 || y > 9999 {
			writeErr(w, http.StatusBadRequest, "month 格式应为 YYYY-MM")
			return
		}
		year, mon = y, mn
	}

	rep, err := s.store.MonthlySLA(id, year, mon)
	if err != nil {
		logErr(r, "handleMonitorSLA", err)
		writeErr(w, http.StatusInternalServerError, "生成 SLA 报告失败")
		return
	}
	writeJSON(w, http.StatusOK, rep)
}

// handleMonitorSetPublic 更新 monitor 的公开可见性。
func (s *Server) handleMonitorSetPublic(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		writeErr(w, http.StatusNotFound, "monitor 不存在")
		return
	}
	var body struct {
		IsPublic int `json:"is_public"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体非法")
		return
	}
	if body.IsPublic != 0 && body.IsPublic != 1 {
		writeErr(w, http.StatusBadRequest, "is_public 只能为 0 或 1")
		return
	}
	if err := s.store.SetMonitorPublic(id, body.IsPublic); err != nil {
		logErr(r, "handleMonitorSetPublic", err)
		writeErr(w, http.StatusInternalServerError, "更新失败")
		return
	}
	m, err := s.store.GetMonitor(id)
	if err != nil {
		logErr(r, "handleMonitorSetPublic", err)
		writeErr(w, http.StatusInternalServerError, "读取失败")
		return
	}
	writeJSON(w, http.StatusOK, monitorJSON(m))
}

// handleCreateStatusPage 创建状态页。
func (s *Server) handleCreateStatusPage(w http.ResponseWriter, r *http.Request) {
	var body struct {
		Slug  string `json:"slug"`
		Title string `json:"title"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体非法")
		return
	}
	if !statusPageSlugRe.MatchString(body.Slug) {
		writeErr(w, http.StatusBadRequest, "slug 非法")
		return
	}
	if strings.TrimSpace(body.Title) == "" {
		writeErr(w, http.StatusBadRequest, "title 不能为空")
		return
	}
	tenantID := middleware.TenantIDFrom(r.Context())
	if tenantID <= 0 {
		tenantID = 1
	}

	// 检查 slug 冲突。
	if _, err := s.store.GetStatusPageBySlug(body.Slug); err == nil {
		writeErr(w, http.StatusConflict, "slug 已存在")
		return
	}

	id, err := s.store.CreateStatusPage(tenantID, body.Slug, body.Title)
	if err != nil {
		logErr(r, "handleCreateStatusPage", err)
		writeErr(w, http.StatusConflict, "创建失败")
		return
	}
	sp, err := s.store.GetStatusPage(id)
	if err != nil {
		logErr(r, "handleCreateStatusPage", err)
		writeErr(w, http.StatusInternalServerError, "读取失败")
		return
	}
	writeJSON(w, http.StatusCreated, sp)
}

// handleListStatusPages 列出当前租户的状态页。
func (s *Server) handleListStatusPages(w http.ResponseWriter, r *http.Request) {
	tenantID := middleware.TenantIDFrom(r.Context())
	if tenantID <= 0 {
		tenantID = 1
	}
	pages, err := s.store.ListStatusPages(tenantID)
	if err != nil {
		logErr(r, "handleListStatusPages", err)
		writeErr(w, http.StatusInternalServerError, "查询失败")
		return
	}
	if pages == nil {
		pages = []store.StatusPage{}
	}
	writeJSON(w, http.StatusOK, map[string]any{"pages": pages})
}

// handleDeleteStatusPage 删除状态页。
func (s *Server) handleDeleteStatusPage(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(id); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	if err := s.store.DeleteStatusPage(id); err != nil {
		logErr(r, "handleDeleteStatusPage", err)
		writeErr(w, http.StatusInternalServerError, "删除失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted": id})
}

// handleAddPageMonitor 将 monitor 加入状态页。
func (s *Server) handleAddPageMonitor(w http.ResponseWriter, r *http.Request) {
	pageID, ok := parseID(r)
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(pageID); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	var body struct {
		MonitorID int64 `json:"monitor_id"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || body.MonitorID <= 0 {
		writeErr(w, http.StatusBadRequest, "monitor_id 非法")
		return
	}
	if _, err := s.store.GetMonitor(body.MonitorID); err != nil {
		writeErr(w, http.StatusNotFound, "monitor 不存在")
		return
	}
	if err := s.store.AddMonitorToPage(pageID, body.MonitorID); err != nil {
		logErr(r, "handleAddPageMonitor", err)
		writeErr(w, http.StatusInternalServerError, "添加失败")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"page_id": pageID, "monitor_id": body.MonitorID})
}

// handleRemovePageMonitor 从状态页移除 monitor。
func (s *Server) handleRemovePageMonitor(w http.ResponseWriter, r *http.Request) {
	pageID, ok := parseID(r)
	if !ok {
		return
	}
	mid, ok := parsePathID(r, "monitor_id")
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(pageID); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	if err := s.store.RemoveMonitorFromPage(pageID, mid); err != nil {
		logErr(r, "handleRemovePageMonitor", err)
		writeErr(w, http.StatusInternalServerError, "移除失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"page_id": pageID, "monitor_id": mid})
}

// handleAutoStatusPage 自动创建/复用 slug=status 的状态页，并同步所有公开 monitor。
func (s *Server) handleAutoStatusPage(w http.ResponseWriter, r *http.Request) {
	tenantID := middleware.TenantIDFrom(r.Context())
	if tenantID <= 0 {
		tenantID = 1
	}

	page, err := s.store.GetStatusPageBySlug("status")
	if err != nil {
		// 不存在则创建。
		id, cerr := s.store.CreateStatusPage(tenantID, "status", "服务状态")
		if cerr != nil {
			logErr(r, "handleAutoStatusPage", cerr)
			writeErr(w, http.StatusInternalServerError, "创建状态页失败")
			return
		}
		page, err = s.store.GetStatusPage(id)
		if err != nil {
			logErr(r, "handleAutoStatusPage", err)
			writeErr(w, http.StatusInternalServerError, "读取状态页失败")
			return
		}
	}

	// 拉取该租户所有公开 monitor。
	mons, err := s.store.ListMonitorsByTenant(tenantID)
	if err != nil {
		logErr(r, "handleAutoStatusPage", err)
		writeErr(w, http.StatusInternalServerError, "查询 monitor 失败")
		return
	}

	// 先清空该页旧映射，再全量添加（幂等）。
	existing, err := s.store.ListPageMonitors(page.ID)
	if err == nil {
		for _, m := range existing {
			if err := s.store.RemoveMonitorFromPage(page.ID, m.ID); err != nil {
				logErr(r, "handleAutoStatusPage", err)
			}
		}
	}

	var added int
	for _, m := range mons {
		if m.IsPublic != 1 {
			continue
		}
		if err := s.store.AddMonitorToPage(page.ID, m.ID); err != nil {
			logErr(r, "handleAutoStatusPage", err)
			continue
		}
		added++
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"page":          page,
		"monitor_count": added,
	})
}

// handlePublicStatus 公开访问状态页。
func (s *Server) handlePublicStatus(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	if slug == "" {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	page, err := s.store.GetStatusPageBySlug(slug)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	mons, err := s.store.ListPageMonitors(page.ID)
	if err != nil {
		logErr(r, "handlePublicStatus", err)
		writeErr(w, http.StatusInternalServerError, "查询失败")
		return
	}

	items := make([]map[string]any, 0, len(mons))
	for _, m := range mons {
		up30, _, _, _, err := s.store.MonitorStats(m.ID, 30)
		if err != nil {
			logErr(r, "handlePublicStatus", err)
		}
		var status = "unknown"
		var lastChecked any = nil
		var latency any = nil
		last, lerr := s.store.LastCheck(m.ID)
		if lerr == nil && last != nil {
			if last.Ok == 1 {
				status = "up"
			} else {
				status = "down"
			}
			lastChecked = last.CheckedAt
			latency = last.LatencyMs
		}
		items = append(items, map[string]any{
			"id":              m.ID,
			"name":            m.Name,
			"kind":            m.Kind,
			"status":          status,
			"uptime_30d":      up30,
			"last_checked_at": lastChecked,
			"latency_ms":      latency,
		})
	}

	writeJSON(w, http.StatusOK, map[string]any{
		"slug":       page.Slug,
		"title":      page.Title,
		"updated_at": time.Now().UTC().Format(time.RFC3339),
		"monitors":   items,
	})
}

// 确保 errors 被使用（供将来扩展）。
var _ = errors.Is
