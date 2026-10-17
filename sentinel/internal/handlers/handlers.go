// Package handlers 提供 HTTP API 与页面路由。
// 注意：本文件是 internal/handlers 包，不含 main、不监听端口、不 embed 静态文件。
package handlers

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"log/slog"
	"net/http"
	"strconv"
	"strings"

	"sentinel/internal/log"
	"sentinel/internal/metrics"
	"sentinel/internal/middleware"
	"sentinel/internal/notify"
	"sentinel/internal/scheduler"
	"sentinel/internal/store"
	"sentinel/internal/web"
)

// Server 持有 store、scheduler 与认证中间件依赖。
type Server struct {
	store        *store.Store
	sched        *scheduler.Scheduler
	auth         *middleware.Auth
	checkRetries int
	mailer       notify.Mailer
	publicURL    string
}

// New 构造 Server。
func New(st *store.Store, sc *scheduler.Scheduler, checkRetries int) *Server {
	return &Server{store: st, sched: sc, auth: middleware.NewAuth(st), checkRetries: checkRetries}
}

// Routes 返回全部路由（含中间件链）。
func (s *Server) Routes() http.Handler {
	mux := http.NewServeMux()

	// 健康检查与运维端点
	mux.HandleFunc("GET /api/health", s.handleHealth)
	mux.HandleFunc("GET /healthz", s.handleHealthz)
	mux.HandleFunc("GET /api/healthz", s.handleHealthz)
	mux.HandleFunc("GET /readyz", s.handleReadyz)
	mux.HandleFunc("GET /api/readyz", s.handleReadyz)
	mux.HandleFunc("GET /api/metrics", s.handleMetrics)

	// 监控目标
	mux.HandleFunc("GET /api/monitors", s.handleListMonitors)
	mux.HandleFunc("POST /api/monitors", s.handleCreateMonitor)
	mux.HandleFunc("GET /api/monitors/{id}", s.handleGetMonitor)
	mux.HandleFunc("PUT /api/monitors/{id}", s.handleUpdateMonitor)
	mux.HandleFunc("DELETE /api/monitors/{id}", s.handleDeleteMonitor)
	mux.HandleFunc("POST /api/monitors/{id}/check", s.handleCheckNow)
	mux.HandleFunc("GET /api/monitors/{id}/checks", s.handleListChecks)
	mux.HandleFunc("GET /api/monitors/{id}/stats", s.handleStats)

	// 事件与概览
	mux.HandleFunc("GET /api/incidents", s.handleListIncidents)
	mux.HandleFunc("GET /api/overview", s.handleOverview)
	mux.HandleFunc("GET /api/alerts/deliveries", s.handleListDeliveries)
	mux.HandleFunc("POST /api/alerts/deliveries/{id}/retry", s.handleRetryDelivery)
	mux.HandleFunc("POST /api/silences", s.handleCreateSilence)
	mux.HandleFunc("GET /api/silences", s.handleListSilences)
	mux.HandleFunc("DELETE /api/silences/{id}", s.handleDeleteSilence)
	// 静态页面与资源
	mux.HandleFunc("GET /{$}", s.handleIndex)
	mux.HandleFunc("GET /monitors", s.handleMonitorsPage)
	mux.HandleFunc("GET /incidents", s.handleIncidentsPage)
	mux.HandleFunc("GET /deliveries", s.handleDeliveriesPage)
	mux.HandleFunc("GET /profile", s.handleProfilePage)
	mux.HandleFunc("GET /status/{slug}", s.handleStatusPage)
	subStatic, err := fs.Sub(web.FS, "static")
	if err != nil {
		panic(err)
	}
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.FS(subStatic))))

	s.RegisterSoulRoutes(mux)

	// 中间件链：RequestID -> Logging -> Auth -> mux
	exact := []string{"/healthz", "/readyz", "/api/healthz", "/api/readyz", "/api/health",
		"/", "/monitors", "/incidents", "/profile", "/deliveries"}
	prefix := []string{"/api/status/", "/status/", "/static/"}
	return middleware.RequestID(middleware.Logging(s.auth.Middleware(exact, prefix)(mux)))
}

// ---------- 通用辅助 ----------

func writeJSON(w http.ResponseWriter, status int, v interface{}) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeErr(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

func parseID(r *http.Request) (int64, bool) {
	raw := r.PathValue("id")
	if raw == "" {
		return 0, false
	}
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		return 0, false
	}
	return id, true
}

// logErr 记录错误日志，统一携带 request_id、handler 与 err。
func logErr(r *http.Request, handler string, err error) {
	slog.Error("handler error",
		"request_id", log.RequestIDFrom(r.Context()),
		"handler", handler,
		"err", err,
	)
}

// monitorInput 是创建/更新监控目标的请求体。
type monitorInput struct {
	Name           *string `json:"name"`
	Kind           *string `json:"kind"`
	Target         *string `json:"target"`
	Method         *string `json:"method"`
	ExpectedStatus *int    `json:"expected_status"`
	TimeoutSec     *int    `json:"timeout_sec"`
	IntervalSec    *int    `json:"interval_sec"`
	Enabled        *int    `json:"enabled"`
	WebhookURL     *string `json:"webhook_url"`
	NotifyChannels *string `json:"notify_channels"`
	SMSPhones      *string `json:"sms_phones"`
}

// toMonitor 把请求体转为 store.Monitor 并填默认值。
func (in *monitorInput) toMonitor() store.Monitor {
	m := store.Monitor{
		Kind:           "http",
		Method:         "GET",
		ExpectedStatus: 200,
		TimeoutSec:     10,
		IntervalSec:    60,
		Enabled:        1,
	}
	if in.Name != nil {
		m.Name = *in.Name
	}
	if in.Kind != nil {
		m.Kind = *in.Kind
	}
	if in.Target != nil {
		m.Target = *in.Target
	}
	if in.Method != nil {
		m.Method = *in.Method
	}
	if in.ExpectedStatus != nil {
		m.ExpectedStatus = *in.ExpectedStatus
	}
	if in.TimeoutSec != nil {
		m.TimeoutSec = *in.TimeoutSec
	}
	if in.IntervalSec != nil {
		m.IntervalSec = *in.IntervalSec
	}
	if in.Enabled != nil {
		m.Enabled = *in.Enabled
	}
	if in.WebhookURL != nil {
		m.WebhookURL = *in.WebhookURL
	}
	if in.NotifyChannels != nil {
		m.NotifyChannels = *in.NotifyChannels
	}
	if in.SMSPhones != nil {
		m.SMSPhones = *in.SMSPhones
	}
	return m
}

// validateMonitor 校验业务规则，返回中文错误信息。
func validateMonitor(m *store.Monitor) error {
	m.Name = strings.TrimSpace(m.Name)
	m.Kind = strings.TrimSpace(m.Kind)
	m.Target = strings.TrimSpace(m.Target)
	m.Method = strings.TrimSpace(m.Method)
	m.WebhookURL = strings.TrimSpace(m.WebhookURL)
	m.NotifyChannels = strings.TrimSpace(m.NotifyChannels)
	m.SMSPhones = strings.TrimSpace(m.SMSPhones)

	if m.Name == "" {
		return errors.New("名称不能为空")
	}
	if m.Kind != "http" && m.Kind != "tcp" {
		return errors.New("kind 只能为 http 或 tcp")
	}
	if m.Target == "" {
		return errors.New("目标地址不能为空")
	}
	if m.Kind == "http" {
		if !strings.HasPrefix(m.Target, "http://") && !strings.HasPrefix(m.Target, "https://") {
			return errors.New("http 目标必须以 http:// 或 https:// 开头")
		}
	} else {
		if !strings.Contains(m.Target, ":") {
			return errors.New("tcp 目标必须为 host:port 形式")
		}
	}
	switch m.Method {
	case "GET", "HEAD", "POST":
	default:
		return errors.New("method 仅支持 GET/HEAD/POST")
	}
	if m.ExpectedStatus < 100 || m.ExpectedStatus > 599 {
		return errors.New("expected_status 必须在 100~599 之间")
	}
	if m.TimeoutSec < 1 || m.TimeoutSec > 60 {
		return errors.New("timeout_sec 必须在 1~60 之间")
	}
	if m.IntervalSec < 10 || m.IntervalSec > 3600 {
		return errors.New("interval_sec 必须在 10~3600 之间")
	}
	if m.Enabled != 0 && m.Enabled != 1 {
		return errors.New("enabled 只能为 0 或 1")
	}
	if m.NotifyChannels != "" {
		parsed := notify.ParseChannels(m.NotifyChannels)
		if len(parsed) == 0 {
			return errors.New("notify_channels 非法：仅支持 webhook/smtp/wecom/sms（逗号分隔）")
		}
		m.NotifyChannels = strings.Join(parsed, ",")
	}
	if m.SMSPhones != "" {
		parsed, err := notify.ParsePhones(m.SMSPhones)
		if err != nil {
			return fmt.Errorf("sms_phones 非法: %w", err)
		}
		m.SMSPhones = strings.Join(parsed, ",")
	}
	return nil
}

// checkJSON 把 store.Check 转为 API 输出结构。
func checkJSON(c store.Check) map[string]interface{} {
	var sc interface{}
	if c.StatusCode.Valid {
		sc = c.StatusCode.Int64
	}
	var cdl interface{}
	if c.CertDaysLeft.Valid {
		cdl = c.CertDaysLeft.Int64
	}
	return map[string]interface{}{
		"id":             c.ID,
		"monitor_id":     c.MonitorID,
		"checked_at":     c.CheckedAt,
		"ok":             c.Ok == 1,
		"status_code":    sc,
		"latency_ms":     c.LatencyMs,
		"error":          c.Error,
		"cert_days_left": cdl,
	}
}

// monitorJSON 把 store.Monitor 转为 API 输出结构（snake_case）。
func monitorJSON(m store.Monitor) map[string]interface{} {
	return map[string]interface{}{
		"id":              m.ID,
		"name":            m.Name,
		"kind":            m.Kind,
		"target":          m.Target,
		"method":          m.Method,
		"expected_status": m.ExpectedStatus,
		"timeout_sec":     m.TimeoutSec,
		"interval_sec":    m.IntervalSec,
		"enabled":         m.Enabled,
		"webhook_url":     m.WebhookURL,
		"notify_channels": m.NotifyChannels,
		"sms_phones":      m.SMSPhones,
		"tenant_id":       m.TenantID,
		"is_public":       m.IsPublic,
		"created_at":      m.CreatedAt,
		"updated_at":      m.UpdatedAt,
	}
}

// ---------- 页面路由 ----------

func (s *Server) serveStaticFile(w http.ResponseWriter, name, contentType string) {
	data, err := fs.ReadFile(web.FS, "static/"+name)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "页面资源不存在")
		return
	}
	w.Header().Set("Content-Type", contentType)
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}

func (s *Server) handleIndex(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "index.html", "text/html; charset=utf-8")
}

func (s *Server) handleMonitorsPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "monitors.html", "text/html; charset=utf-8")
}

func (s *Server) handleIncidentsPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "incidents.html", "text/html; charset=utf-8")
}

// handleDeliveriesPage 渲染投递队列控制台页。
func (s *Server) handleDeliveriesPage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "deliveries.html", "text/html; charset=utf-8")
}

// handleProfilePage 渲染用户资料页。
func (s *Server) handleProfilePage(w http.ResponseWriter, r *http.Request) {
	s.serveStaticFile(w, "profile.html", "text/html; charset=utf-8")
}

// handleStatusPage 渲染公开状态页，slug 需非空且合法。
func (s *Server) handleStatusPage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	if strings.TrimSpace(slug) == "" {
		logErr(r, "handleStatusPage", errors.New("empty slug"))
		writeErr(w, http.StatusBadRequest, "无效的状态页标识")
		return
	}
	s.serveStaticFile(w, "status.html", "text/html; charset=utf-8")
}

// ---------- API 处理器 ----------

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok", "version": "0.1.0"})
}

// handleHealthz 简单存活探针。
func (s *Server) handleHealthz(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// handleReadyz 就绪探针，依赖数据库 Ping。
func (s *Server) handleReadyz(w http.ResponseWriter, r *http.Request) {
	if err := s.store.Ping(); err != nil {
		logErr(r, "handleReadyz", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"status": "not ready"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]string{"status": "ready"})
}

// handleMetrics 输出 Prometheus 文本格式指标。
//
// 除 Registry 内的计数器外，还会附加 webhook 投递队列积压 gauge。
// 积压数据来自数据库查询，属于易抖动的外部依赖：一旦查询失败，
// 只记录错误并跳过该 gauge，绝不中断整个 Prometheus 抓取，
// 仍然返回 200 与已收集到的指标，避免一次 DB 抖动导致抓取目标被判 down。
func (s *Server) handleMetrics(w http.ResponseWriter, r *http.Request) {
	out := metrics.Default.RenderPrometheus()
	if counts, err := s.store.CountDeliveriesByStatus(); err != nil {
		logErr(r, "handleMetrics", err)
	} else {
		// map 缺 key 时读到的零值即为 0，无需额外判断。
		out += metrics.RenderQueueBacklog(int64(counts["pending"]), int64(counts["retrying"]))
	}
	w.Header().Set("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(out))
}

func (s *Server) handleListMonitors(w http.ResponseWriter, r *http.Request) {
	tenantID := middleware.TenantIDFrom(r.Context())
	if tenantID <= 0 {
		tenantID = 1
	}
	monitors, err := s.store.ListMonitorsByTenant(tenantID)
	if err != nil {
		logErr(r, "handleListMonitors", err)
		writeErr(w, http.StatusInternalServerError, "读取监控列表失败")
		return
	}
	items := make([]map[string]interface{}, 0, len(monitors))
	for _, m := range monitors {
		item := monitorJSON(m)
		last, err := s.store.LastCheck(m.ID)
		if err == nil && last != nil {
			ok := last.Ok == 1
			item["last_ok"] = ok
			item["last_checked_at"] = last.CheckedAt
		} else {
			item["last_ok"] = nil
			item["last_checked_at"] = ""
		}
		uptime, _, _, _, err := s.store.MonitorStats(m.ID, 1)
		if err != nil {
			uptime = 100.0
		}
		item["uptime_24h"] = uptime
		items = append(items, item)
	}
	writeJSON(w, http.StatusOK, items)
}

func (s *Server) handleCreateMonitor(w http.ResponseWriter, r *http.Request) {
	var in monitorInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		logErr(r, "handleCreateMonitor", err)
		writeErr(w, http.StatusBadRequest, "请求体 JSON 解析失败")
		return
	}
	m := in.toMonitor()
	if tid := middleware.TenantIDFrom(r.Context()); tid > 0 {
		m.TenantID = tid
	} else {
		m.TenantID = 1
	}
	if err := validateMonitor(&m); err != nil {
		logErr(r, "handleCreateMonitor", err)
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	id, err := s.store.CreateMonitor(m)
	if err != nil {
		logErr(r, "handleCreateMonitor", err)
		writeErr(w, http.StatusInternalServerError, "创建监控失败")
		return
	}
	created, err := s.store.GetMonitor(id)
	if err != nil {
		logErr(r, "handleCreateMonitor", err)
		writeErr(w, http.StatusInternalServerError, "读取新建监控失败")
		return
	}
	writeJSON(w, http.StatusCreated, monitorJSON(created))
}

func (s *Server) handleGetMonitor(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleGetMonitor", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	m, err := s.store.GetMonitor(id)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleGetMonitor", err)
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}
	checks, err := s.store.ListChecks(id, 50)
	if err != nil {
		checks = nil
	}
	recent := make([]map[string]interface{}, 0, len(checks))
	for _, c := range checks {
		recent = append(recent, checkJSON(c))
	}
	out := monitorJSON(m)
	out["recent_checks"] = recent
	writeJSON(w, http.StatusOK, out)
}

func (s *Server) handleUpdateMonitor(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleUpdateMonitor", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleUpdateMonitor", err)
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}
	var in monitorInput
	if err := json.NewDecoder(r.Body).Decode(&in); err != nil {
		logErr(r, "handleUpdateMonitor", err)
		writeErr(w, http.StatusBadRequest, "请求体 JSON 解析失败")
		return
	}
	m := in.toMonitor()
	if tid := middleware.TenantIDFrom(r.Context()); tid > 0 {
		m.TenantID = tid
	} else {
		m.TenantID = 1
	}
	if err := validateMonitor(&m); err != nil {
		logErr(r, "handleUpdateMonitor", err)
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	if err := s.store.UpdateMonitor(id, m); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleUpdateMonitor", err)
		writeErr(w, http.StatusInternalServerError, "更新监控失败")
		return
	}
	updated, err := s.store.GetMonitor(id)
	if err != nil {
		logErr(r, "handleUpdateMonitor", err)
		writeErr(w, http.StatusInternalServerError, "读取更新后的监控失败")
		return
	}
	writeJSON(w, http.StatusOK, monitorJSON(updated))
}

func (s *Server) handleDeleteMonitor(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleDeleteMonitor", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	if err := s.store.DeleteMonitor(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleDeleteMonitor", err)
		writeErr(w, http.StatusInternalServerError, "删除监控失败")
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (s *Server) handleCheckNow(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleCheckNow", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleCheckNow", err)
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}
	c, err := s.sched.CheckNow(id, s.checkRetries)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleCheckNow", err)
		writeErr(w, http.StatusInternalServerError, "执行检查失败")
		return
	}
	writeJSON(w, http.StatusOK, checkJSON(c))
}

func (s *Server) handleListChecks(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleListChecks", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleListChecks", err)
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}
	limit := 100
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = n
		}
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 1000 {
		limit = 1000
	}
	checks, err := s.store.ListChecks(id, limit)
	if err != nil {
		logErr(r, "handleListChecks", err)
		writeErr(w, http.StatusInternalServerError, "读取检查记录失败")
		return
	}
	total, err := s.store.CheckCount(id)
	if err != nil {
		total = 0
	}
	items := make([]map[string]interface{}, 0, len(checks))
	for _, c := range checks {
		items = append(items, checkJSON(c))
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"items": items, "total": total})
}

func (s *Server) handleStats(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		logErr(r, "handleStats", errors.New("invalid monitor id"))
		writeErr(w, http.StatusBadRequest, "无效的监控 ID")
		return
	}
	if _, err := s.store.GetMonitor(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "监控不存在")
			return
		}
		logErr(r, "handleStats", err)
		writeErr(w, http.StatusInternalServerError, "读取监控失败")
		return
	}
	days := 7
	if v := r.URL.Query().Get("days"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			days = n
		}
	}
	if days < 1 {
		days = 1
	}
	if days > 90 {
		days = 90
	}
	uptime, avgLat, total, downInc, err := s.store.MonitorStats(id, days)
	if err != nil {
		logErr(r, "handleStats", err)
		writeErr(w, http.StatusInternalServerError, "统计失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"uptime_pct":     uptime,
		"avg_latency_ms": avgLat,
		"total_checks":   total,
		"down_incidents": downInc,
	})
}

func (s *Server) handleListIncidents(w http.ResponseWriter, r *http.Request) {
	var monitorID int64
	if v := r.URL.Query().Get("monitor_id"); v != "" {
		if n, err := strconv.ParseInt(v, 10, 64); err == nil {
			monitorID = n
		}
	}
	limit := 100
	if v := r.URL.Query().Get("limit"); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			limit = n
		}
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 1000 {
		limit = 1000
	}
	incidents, err := s.store.ListIncidents(monitorID, limit)
	if err != nil {
		logErr(r, "handleListIncidents", err)
		writeErr(w, http.StatusInternalServerError, "读取事件失败")
		return
	}
	items := make([]map[string]interface{}, 0, len(incidents))
	for _, inc := range incidents {
		var endedAt interface{}
		if inc.EndedAt.Valid {
			endedAt = inc.EndedAt.String
		}
		var downtime interface{}
		if inc.DowntimeSec.Valid {
			downtime = inc.DowntimeSec.Int64
		}
		items = append(items, map[string]interface{}{
			"id":           inc.ID,
			"monitor_id":   inc.MonitorID,
			"monitor_name": inc.MonitorName,
			"started_at":   inc.StartedAt,
			"ended_at":     endedAt,
			"downtime_sec": downtime,
			"start_error":  inc.StartError,
		})
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"items": items})
}

func (s *Server) handleOverview(w http.ResponseWriter, r *http.Request) {
	total, enabled, up, down, unknown, checks24h, incidents7d, err := s.store.Overview()
	if err != nil {
		logErr(r, "handleOverview", err)
		writeErr(w, http.StatusInternalServerError, "概览统计失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"total":        total,
		"enabled":      enabled,
		"up":           up,
		"down":         down,
		"unknown":      unknown,
		"checks_24h":   checks24h,
		"incidents_7d": incidents7d,
	})
}
