package handlers

import (
	"database/sql"
	"encoding/json"
	"errors"
	"html"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"

	"sentinel/internal/middleware"
	"sentinel/internal/notify"
	"sentinel/internal/store"
)

// RegisterSoulRoutes 注册 profile / SLA / 状态页相关路由。
// 需要在 handlers.go 的 Routes() 末尾（返回 mux 之前）调用：
//
//	s.RegisterSoulRoutes(mux)
//
// 注册的 15 条路由：
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
//	PUT    /api/status-pages/{id}/theme
//	POST   /api/status-pages/{id}/snapshot        下载单文件静态 HTML 快照
//	GET    /api/status/{slug}          （公开，白名单已含 /api/status/ 前缀）
//	POST   /api/status/{slug}/subscribe     （公开）
//	GET    /api/status/{slug}/confirm       （公开）
//	GET    /api/status/{slug}/unsubscribe   （公开，退订确认页）
//	POST   /api/status/{slug}/unsubscribe   （公开，执行退订）
func (s *Server) RegisterSoulRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/monitors/{id}/profile", s.handleMonitorProfile)
	mux.HandleFunc("GET /api/monitors/{id}/sla", s.handleMonitorSLAJSON)
	mux.HandleFunc("GET /api/monitors/{id}/sla.html", s.handleMonitorSLAHTML)
	mux.HandleFunc("PUT /api/monitors/{id}/public", s.handleMonitorSetPublic)

	mux.HandleFunc("POST /api/status-pages", s.handleCreateStatusPage)
	mux.HandleFunc("GET /api/status-pages", s.handleListStatusPages)
	mux.HandleFunc("DELETE /api/status-pages/{id}", s.handleDeleteStatusPage)
	mux.HandleFunc("POST /api/status-pages/{id}/monitors", s.handleAddPageMonitor)
	mux.HandleFunc("DELETE /api/status-pages/{id}/monitors/{monitor_id}", s.handleRemovePageMonitor)
	mux.HandleFunc("POST /api/status-pages/auto", s.handleAutoStatusPage)
	mux.HandleFunc("PUT /api/status-pages/{id}/theme", s.handleUpdateStatusPageTheme)
	mux.HandleFunc("POST /api/status-pages/{id}/snapshot", s.handleStatusPageSnapshot)
	mux.HandleFunc("POST /api/status-pages/{id}/publish", s.handlePublishStatusPage)
	mux.HandleFunc("POST /api/status-pages/{id}/publish/rollback", s.handlePublishRollback)
	mux.HandleFunc("GET /api/status-pages/{id}/publish", s.handlePublishInfo)

	// 公开路由。
	mux.HandleFunc("GET /api/status/{slug}", s.handlePublicStatus)
	mux.HandleFunc("POST /api/status/{slug}/subscribe", s.handleSubscribe)
	mux.HandleFunc("GET /api/status/{slug}/confirm", s.handleConfirm)
	mux.HandleFunc("GET /api/status/{slug}/unsubscribe", s.handleUnsubscribePage)
	mux.HandleFunc("POST /api/status/{slug}/unsubscribe", s.handleUnsubscribe)
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
	id, ok := parsePathID(r, "id")
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
	}
	up30, _, _, incidents30, err := s.store.MonitorStats(id, 30)
	if err != nil {
	}

	p50, p95, p99, err := s.store.LatencyPercentiles(id, 30)
	if err != nil {
	}

	daily, err := s.store.DailyBreakdown(id, 30)
	if err != nil {
	}
	if daily == nil {
		daily = []store.DayStat{}
	}
	js, jl, _ := s.store.JitterScore(id, 7)
	tl, _ := s.store.IncidentTimeline(id, 30, 50)
	if tl == nil {
		tl = []store.TimelineEvent{}
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
		"jitter_score":   js,
		"jitter_level":   jl,
		"timeline":       tl,
	})
}

// handleMonitorSetPublic 更新 monitor 的公开可见性。
func (s *Server) handleMonitorSetPublic(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
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
		writeErr(w, http.StatusInternalServerError, "更新失败")
		return
	}
	m, err := s.store.GetMonitor(id)
	if err != nil {
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
		writeErr(w, http.StatusConflict, "创建失败")
		return
	}
	sp, err := s.store.GetStatusPage(id)
	if err != nil {
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
	id, ok := parsePathID(r, "id")
	if !ok {
		return
	}
	if _, err := s.store.GetStatusPage(id); err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	if err := s.store.DeleteStatusPage(id); err != nil {
		writeErr(w, http.StatusInternalServerError, "删除失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"deleted": id})
}

// handleAddPageMonitor 将 monitor 加入状态页。
func (s *Server) handleAddPageMonitor(w http.ResponseWriter, r *http.Request) {
	pageID, ok := parsePathID(r, "id")
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
		writeErr(w, http.StatusInternalServerError, "添加失败")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"page_id": pageID, "monitor_id": body.MonitorID})
}

// handleRemovePageMonitor 从状态页移除 monitor。
func (s *Server) handleRemovePageMonitor(w http.ResponseWriter, r *http.Request) {
	pageID, ok := parsePathID(r, "id")
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
			writeErr(w, http.StatusInternalServerError, "创建状态页失败")
			return
		}
		page, err = s.store.GetStatusPage(id)
		if err != nil {
			writeErr(w, http.StatusInternalServerError, "读取状态页失败")
			return
		}
	}

	// 拉取该租户所有公开 monitor。
	mons, err := s.store.ListMonitorsByTenant(tenantID)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "查询 monitor 失败")
		return
	}

	// 先清空该页旧映射，再全量添加（幂等）。
	existing, err := s.store.ListPageMonitors(page.ID)
	if err == nil {
		for _, m := range existing {
			if err := s.store.RemoveMonitorFromPage(page.ID, m.ID); err != nil {
			}
		}
	}

	var added int
	for _, m := range mons {
		if m.IsPublic != 1 {
			continue
		}
		if err := s.store.AddMonitorToPage(page.ID, m.ID); err != nil {
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
		writeErr(w, http.StatusInternalServerError, "查询失败")
		return
	}

	items := make([]map[string]any, 0, len(mons))
	for _, m := range mons {
		up30, _, _, _, err := s.store.MonitorStats(m.ID, 30)
		if err != nil {
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
		"slug":         page.Slug,
		"title":        page.Title,
		"theme":        page.Theme,
		"accent_color": page.AccentColor,
		"updated_at":   time.Now().UTC().Format(time.RFC3339),
		"monitors":     items,
	})
}

// handleUpdateStatusPageTheme 更新状态页主题（需鉴权）。
func (s *Server) handleUpdateStatusPageTheme(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "无效的状态页 ID")
		return
	}
	var body struct {
		Theme       string `json:"theme"`
		AccentColor string `json:"accent_color"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体非法")
		return
	}
	if err := s.store.UpdateStatusPageTheme(id, body.Theme, body.AccentColor); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "状态页不存在")
			return
		}
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}
	sp, err := s.store.GetStatusPage(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取失败")
		return
	}
	writeJSON(w, http.StatusOK, sp)
}

// SetMailer 设置订阅邮件发送器（确认邮件与事件通知共用）。
func (s *Server) SetMailer(m notify.Mailer) {
	s.mailer = m
}

// SetPublicURL 设置对外基地址（用于邮件中的确认/退订链接）；为空则用相对路径。
func (s *Server) SetPublicURL(u string) {
	s.publicURL = strings.TrimRight(strings.TrimSpace(u), "/")
}

// SetQueueSender 设置 webhook 投递队列发送器，供 /api/metrics 导出熔断状态；可为 nil。
func (s *Server) SetQueueSender(q *notify.QueueSender) {
	s.queueSender = q
}

// handleSubscribe 处理公开订阅：创建待确认订阅并发送确认邮件。
func (s *Server) handleSubscribe(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	page, err := s.store.GetStatusPageBySlug(slug)
	if err != nil {
		writeErr(w, http.StatusNotFound, "状态页不存在")
		return
	}
	var body struct {
		Email string `json:"email"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeErr(w, http.StatusBadRequest, "请求体非法")
		return
	}
	email := store.NormalizeEmail(body.Email)
	if !store.ValidEmail(email) {
		writeErr(w, http.StatusBadRequest, "邮箱格式非法")
		return
	}
	if s.mailer == nil {
		writeErr(w, http.StatusInternalServerError, "邮件服务未配置")
		return
	}

	// 已有订阅：已确认直接返回；待确认重发确认邮件。
	if sub, err := s.store.GetSubscriptionByPageEmail(page.ID, email); err == nil {
		if sub.Confirmed == 1 {
			writeJSON(w, http.StatusOK, map[string]any{"status": "already"})
			return
		}
		if merr := s.sendConfirmMail(page, email, sub.Token); merr != nil {
			writeErr(w, http.StatusInternalServerError, "确认邮件发送失败")
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{"status": "pending"})
		return
	} else if !errors.Is(err, sql.ErrNoRows) {
		writeErr(w, http.StatusInternalServerError, "查询订阅失败")
		return
	}

	token, err := store.NewSubscriptionToken()
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "生成订阅令牌失败")
		return
	}
	if _, err := s.store.CreateSubscription(page.ID, email, token); err != nil {
		if errors.Is(err, store.ErrDuplicateSubscription) {
			writeJSON(w, http.StatusOK, map[string]any{"status": "pending"})
			return
		}
		writeErr(w, http.StatusInternalServerError, "创建订阅失败")
		return
	}
	if merr := s.sendConfirmMail(page, email, token); merr != nil {
		writeErr(w, http.StatusInternalServerError, "确认邮件发送失败")
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"status": "pending"})
}

// sendConfirmMail 发送订阅确认邮件。
func (s *Server) sendConfirmMail(page store.StatusPage, email, token string) error {
	link := "/api/status/" + page.Slug + "/confirm?token=" + token
	if s.publicURL != "" {
		link = s.publicURL + link
	}
	subject := "请确认订阅「" + page.Title + "」的状态通知"
	var b strings.Builder
	b.WriteString("您（" + email + "）申请订阅哨兵 Sentinel 状态页「" + page.Title + "」的服务状态通知。\r\n")
	b.WriteString("请点击以下链接完成确认：\r\n")
	b.WriteString(link + "\r\n")
	b.WriteString("若不是您本人操作，请忽略本邮件。\r\n")
	return s.mailer.SendMail([]string{email}, subject, b.String())
}

// writeSubscribeHTML 输出订阅相关的极简结果页（左对齐浅色卡片，无装饰）。
func writeSubscribeHTML(w http.ResponseWriter, title, message string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	var b strings.Builder
	b.WriteString(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">`)
	b.WriteString(`<meta name="viewport" content="width=device-width, initial-scale=1"><title>`)
	b.WriteString(html.EscapeString(title))
	b.WriteString(` · 哨兵 Sentinel</title><style>`)
	b.WriteString(`body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;`)
	b.WriteString(`background:#f6f7f9;color:#1f2937;margin:0;padding:48px 20px}`)
	b.WriteString(`.card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;`)
	b.WriteString(`border-radius:10px;padding:28px 26px}h1{font-size:18px;margin:0 0 10px}`)
	b.WriteString(`p{font-size:14px;line-height:1.7;color:#4b5563;margin:0}</style>`)
	b.WriteString(`</head><body><div class="card"><h1>`)
	b.WriteString(html.EscapeString(title))
	b.WriteString(`</h1><p>`)
	b.WriteString(html.EscapeString(message))
	b.WriteString(`</p></div></body></html>`)
	_, _ = w.Write([]byte(b.String()))
}

// handleConfirm 处理订阅确认（公开，邮件链接进入）。
func (s *Server) handleConfirm(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	token := strings.TrimSpace(r.URL.Query().Get("token"))
	if token == "" {
		writeSubscribeHTML(w, "链接无效", "订阅确认链接无效或已过期，请重新订阅。")
		return
	}
	sub, err := s.store.GetSubscriptionByToken(token)
	if err != nil {
		writeSubscribeHTML(w, "链接无效", "订阅确认链接无效或已过期，请重新订阅。")
		return
	}
	page, err := s.store.GetStatusPage(sub.PageID)
	if err != nil || page.Slug != slug {
		writeSubscribeHTML(w, "链接无效", "订阅确认链接与状态页不匹配。")
		return
	}
	if sub.Confirmed == 1 {
		writeSubscribeHTML(w, "已确认", "该邮箱已订阅「"+page.Title+"」的状态通知，无需重复确认。")
		return
	}
	if err := s.store.ConfirmSubscription(token); err != nil {
		writeSubscribeHTML(w, "确认失败", "订阅确认失败，请稍后重试。")
		return
	}
	writeSubscribeHTML(w, "订阅成功", "您已成功订阅「"+page.Title+"」的服务状态通知，服务异常与恢复时将收到邮件。")
}

// handleUnsubscribePage 展示退订确认页（公开）。
func (s *Server) handleUnsubscribePage(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	token := strings.TrimSpace(r.URL.Query().Get("token"))
	if token == "" {
		writeSubscribeHTML(w, "链接无效", "退订链接无效或已过期。")
		return
	}
	sub, err := s.store.GetSubscriptionByToken(token)
	if err != nil {
		writeSubscribeHTML(w, "链接无效", "退订链接无效或已过期。")
		return
	}
	page, err := s.store.GetStatusPage(sub.PageID)
	if err != nil || page.Slug != slug {
		writeSubscribeHTML(w, "链接无效", "退订链接与状态页不匹配。")
		return
	}

	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	var b strings.Builder
	b.WriteString(`<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">`)
	b.WriteString(`<meta name="viewport" content="width=device-width, initial-scale=1"><title>退订状态通知 · 哨兵 Sentinel</title><style>`)
	b.WriteString(`body{font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;`)
	b.WriteString(`background:#f6f7f9;color:#1f2937;margin:0;padding:48px 20px}`)
	b.WriteString(`.card{max-width:560px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;`)
	b.WriteString(`border-radius:10px;padding:28px 26px}h1{font-size:18px;margin:0 0 10px}`)
	b.WriteString(`p{font-size:14px;line-height:1.7;color:#4b5563;margin:0 0 18px}`)
	b.WriteString(`button{background:#dc2626;color:#fff;border:none;border-radius:8px;`)
	b.WriteString(`padding:10px 22px;font-size:14px;cursor:pointer}`)
	b.WriteString(`button:disabled{background:#9ca3af;cursor:default}</style></head>`)
	b.WriteString(`<body><div class="card"><h1>退订状态通知</h1><p>确定要退订「`)
	b.WriteString(html.EscapeString(page.Title))
	b.WriteString(`」的状态通知吗？<br>订阅邮箱：`)
	b.WriteString(html.EscapeString(sub.Email))
	b.WriteString(`</p><button id="btn">确认退订</button><p id="msg" style="margin-top:14px"></p>`)
	b.WriteString(`<script>(function(){var btn=document.getElementById('btn'),msg=document.getElementById('msg');`)
	b.WriteString(`btn.onclick=function(){btn.disabled=true;`)
	b.WriteString(`fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},`)
	b.WriteString(`body:JSON.stringify({token:`)
	b.WriteString(strconv.Quote(token))
	b.WriteString(`})}).then(function(r){return r.json()}).then(function(d){`)
	b.WriteString(`msg.textContent=(d.status==='unsubscribed')?'已退订，不再接收该状态页的通知。':'退订失败，请稍后重试。';`)
	b.WriteString(`}).catch(function(){msg.textContent='退订失败，请稍后重试。';btn.disabled=false;});};})();`)
	b.WriteString(`</script></div></body></html>`)
	_, _ = w.Write([]byte(b.String()))
}

// handleUnsubscribe 执行退订（公开）。
func (s *Server) handleUnsubscribe(w http.ResponseWriter, r *http.Request) {
	slug := r.PathValue("slug")
	var body struct {
		Token string `json:"token"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil || strings.TrimSpace(body.Token) == "" {
		writeErr(w, http.StatusBadRequest, "token 非法")
		return
	}
	sub, err := s.store.GetSubscriptionByToken(strings.TrimSpace(body.Token))
	if err != nil {
		writeErr(w, http.StatusNotFound, "订阅不存在或已退订")
		return
	}
	page, err := s.store.GetStatusPage(sub.PageID)
	if err != nil || page.Slug != slug {
		writeErr(w, http.StatusNotFound, "订阅不存在或已退订")
		return
	}
	if err := s.store.DeleteSubscriptionByToken(sub.Token); err != nil {
		writeErr(w, http.StatusInternalServerError, "退订失败")
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"status": "unsubscribed"})
}

// 确保 errors 被使用（供将来扩展）。
var _ = errors.Is
