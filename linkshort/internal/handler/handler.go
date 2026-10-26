// Package handler 提供 linkshort 的 HTTP 层：路由、鉴权、API、Web UI 托管与短链跳转。
package handler

import (
	"bufio"
	"crypto/sha256"
	"embed"
	"encoding/csv"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"log"
	"net"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"

	"github.com/Wanfeng1028/muse/linkshort/internal/auth"
	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/geo"
	"github.com/Wanfeng1028/muse/linkshort/internal/metrics"
	"github.com/Wanfeng1028/muse/linkshort/internal/passalert"

	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/qr"
	"github.com/Wanfeng1028/muse/linkshort/internal/ratelimit"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

//go:embed web
var webFS embed.FS

// NewRouter 组装中间件、API 分组、Web UI 静态托管与短链跳转路由。
func NewRouter(st *store.Store, cfg *config.Config) http.Handler {
	r := chi.NewRouter()

	// 兼容直接构造 Config 的调用方：只填了 AlertWebhookURL 时自动解析出 AlertWebhookURLs。
	if len(cfg.AlertWebhookURLs) == 0 && cfg.AlertWebhookURL != "" {
		cfg.AlertWebhookURLs = config.SplitWebhookURLs(cfg.AlertWebhookURL)
	}
	// 密码失败告警计数器按配置初始化。
	passalert.ConfigureWithIP(cfg.PasswordFailAlertThreshold, cfg.PasswordFailAlertWindow, cfg.PasswordFailAlertIPThreshold)

	r.Use(middleware.RequestID)
	// 注意：刻意不用 chi 的 middleware.RealIP——它无条件用 X-Forwarded-For 改写
	// RemoteAddr，公网攻击者伪造 XFF 即可绕过限流/污染统计；IP 判定统一走 clientIP
	//（仅 LINKSHORT_TRUSTED_PROXIES 名单内的直连对端才信任代理头）。
	r.Use(middleware.Logger)

	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))
	// metrics 放在最外层，以便统计到包括 429 在内的所有请求。
	r.Use(metrics.Default.Middleware)
	// 限流：按 IP+API Key 双维度令牌桶；/metrics 与健康检查免限流。
	// IP 口径与 clientIP 一致（仅信任名单内的代理头），防 XFF 伪造绕过限流。
	rl := ratelimit.New(cfg.RateLimitRPS, cfg.RateLimitBurst, cfg.RateLimitEnabled)
	rl.IPFunc = func(r *http.Request) string { return clientIP(r, cfg) }
	r.Use(rl.Middleware)

	exportLimiter := ratelimit.New(float64(cfg.ExportRateLimitPerMinute)/60.0, cfg.ExportRateLimitPerMinute, cfg.RateLimitEnabled && cfg.ExportRateLimitPerMinute > 0)
	exportLimiter.IPFunc = func(r *http.Request) string { return clientIP(r, cfg) }
	exportLimit := func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			if !exportLimiter.AllowRequest(r) {
				metrics.Default.IncRateLimitRejected()
				retryAfter := 1
				if cfg.ExportRateLimitPerMinute > 0 {
					retryAfter = 60 / cfg.ExportRateLimitPerMinute
					if retryAfter < 1 {
						retryAfter = 1
					}
				}
				w.Header().Set("Retry-After", strconv.Itoa(retryAfter))
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusTooManyRequests)
				_ = json.NewEncoder(w).Encode(map[string]string{"error": "rate limit exceeded"})
				return
			}
			next.ServeHTTP(w, r)
		})
	}

	// 根路径跳转到 UI。
	r.Get("/", func(w http.ResponseWriter, req *http.Request) {
		http.Redirect(w, req, "/ui/", http.StatusFound)
	})

	// Prometheus 指标：仅计数器，无敏感信息，不走鉴权。
	r.Get("/metrics", metrics.Default.Handler())

	// Web UI：embed 前缀为 web/，用 fs.Sub 裁掉。
	sub, err := fs.Sub(webFS, "web")
	if err != nil {
		log.Fatalf("handler: 裁剪 embed 文件系统失败: %v", err)
	}
	fileServer := http.FileServer(http.FS(sub))
	r.Handle("/ui/*", http.StripPrefix("/ui/", fileServer))

	// API 分组。
	r.Route("/api", func(api chi.Router) {
		api.Use(authMiddleware(cfg))
		// 存活探针：进程活着即 200，不依赖 DB。
		api.Get("/health", func(w http.ResponseWriter, req *http.Request) {
			writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		})
		// 就绪探针：DB 连通才 200，否则 503。
		api.Get("/readyz", func(w http.ResponseWriter, req *http.Request) { handleReadyz(w, req, st) })
		api.Get("/meta", func(w http.ResponseWriter, req *http.Request) {
			writeJSON(w, http.StatusOK, map[string]any{
				"base_url":                     shortBaseURL(req, cfg),
				"burn_purge_after_destroy":     cfg.BurnPurgeAfterDestroy,
				"purge_interval":               cfg.PurgeInterval.String(),
				"purge_retention_days":         cfg.PurgeRetentionDays,
				"export_rate_limit_per_minute": cfg.ExportRateLimitPerMinute,
			})
		})
		api.Get("/backup/health", func(w http.ResponseWriter, req *http.Request) { handleBackupHealth(w, req, cfg) })

		api.Post("/links", func(w http.ResponseWriter, req *http.Request) { handleCreateLink(w, req, st, cfg) })
		api.Post("/links/batch", func(w http.ResponseWriter, req *http.Request) { handleBatchCreateLink(w, req, st, cfg) })
		api.Get("/links", func(w http.ResponseWriter, req *http.Request) { handleListLinks(w, req, st, cfg) })
		api.Get("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handleGetLink(w, req, st, cfg) })
		api.Patch("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handlePatchLink(w, req, st, cfg) })
		api.Delete("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handleDeleteLink(w, req, st) })
		api.Get("/links/{id}/qrcode.png", func(w http.ResponseWriter, req *http.Request) { handleQRCode(w, req, st, cfg) })

		api.Get("/links/{id}/daily", func(w http.ResponseWriter, req *http.Request) { handleLinkDaily(w, req, st) })
		api.Get("/links/{id}/referers", func(w http.ResponseWriter, req *http.Request) { handleLinkReferers(w, req, st) })

		api.Get("/links/{id}/ua", func(w http.ResponseWriter, req *http.Request) { handleLinkUA(w, req, st) })

		api.Get("/stats/overview", func(w http.ResponseWriter, req *http.Request) { handleStatsOverview(w, req, st) })
		api.Get("/stats/daily", func(w http.ResponseWriter, req *http.Request) { handleStatsDaily(w, req, st) })
		api.Get("/stats/top-links", func(w http.ResponseWriter, req *http.Request) { handleTopLinks(w, req, st) })
		api.Get("/stats/top-referers", func(w http.ResponseWriter, req *http.Request) { handleTopReferers(w, req, st) })
		api.Get("/stats/geo", func(w http.ResponseWriter, req *http.Request) { handleStatsGeo(w, req, st) })
		api.Get("/stats/hourly", func(w http.ResponseWriter, req *http.Request) { handleStatsHourly(w, req, st) })

		api.Post("/import", func(w http.ResponseWriter, req *http.Request) { handleImport(w, req, st) })
		api.Group(func(g chi.Router) {
			g.Use(exportLimit)
			g.Get("/export.csv", func(w http.ResponseWriter, req *http.Request) { handleExport(w, req, st) })
			g.Get("/stats/geo.csv", func(w http.ResponseWriter, req *http.Request) { handleExportGeoCSV(w, req, st) })
		})
	})

	// API 文档页：公开，无需鉴权。
	r.Get("/docs", func(w http.ResponseWriter, req *http.Request) { handleDocs(w, req) })

	// 短链跳转（放最后，避免覆盖已注册前缀）。
	r.Get("/{slug}", func(w http.ResponseWriter, req *http.Request) { handleRedirect(w, req, st, cfg) })
	r.Post("/{slug}", func(w http.ResponseWriter, req *http.Request) { handlePasswordUnlock(w, req, st, cfg) })

	return r
}

// ---------- 鉴权 ----------

func authMiddleware(cfg *config.Config) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			// AdminKey 为空时直接放行，方便本地开发。
			if cfg.AdminKey == "" {
				next.ServeHTTP(w, req)
				return
			}
			key := req.Header.Get("X-API-Key")
			if key == "" {
				key = req.URL.Query().Get("key")
			}
			if key != cfg.AdminKey {
				writeError(w, http.StatusUnauthorized, "unauthorized")
				return
			}
			next.ServeHTTP(w, req)
		})
	}
}

// ---------- JSON 辅助 ----------

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(v); err != nil {
		log.Printf("handler: 写 JSON 失败: %v", err)
	}
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// linkJSON 是返回给前端的链接结构，ExpiresAt 为 nil 时序列化成 null。
type linkJSON struct {
	ID          int64   `json:"id"`
	Slug        string  `json:"slug"`
	URL         string  `json:"url"`
	Title       string  `json:"title"`
	Clicks      int64   `json:"clicks"`
	Enabled     bool    `json:"enabled"`
	ExpiresAt   *string `json:"expires_at"`
	CreatedAt   string  `json:"created_at"`
	UpdatedAt   string  `json:"updated_at"`
	ShortURL    string  `json:"short_url"`
	MaxVisits   *int64  `json:"max_visits"`
	Burn        bool    `json:"burn"`
	Remaining   *int64  `json:"remaining"`
	HasPassword bool    `json:"has_password"`

	PurgeAfterBurn bool `json:"purge_after_burn"`
}

func toLinkJSON(l *model.Link, base string) linkJSON {
	var exp *string
	if l.ExpiresAt != nil {
		s := l.ExpiresAt.UTC().Format(time.RFC3339)
		exp = &s
	}
	var remaining *int64
	if l.MaxVisits != nil {
		r := *l.MaxVisits - l.Clicks
		if r < 0 {
			r = 0
		}
		remaining = &r
	} else if l.Burn {
		r := int64(0)
		if l.Enabled {
			r = 1
		}
		remaining = &r
	}
	return linkJSON{
		ID:          l.ID,
		Slug:        l.Slug,
		URL:         l.URL,
		Title:       l.Title,
		Clicks:      l.Clicks,
		Enabled:     l.Enabled,
		ExpiresAt:   exp,
		CreatedAt:   l.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt:   l.UpdatedAt.UTC().Format(time.RFC3339),
		ShortURL:    base + "/" + l.Slug,
		MaxVisits:   l.MaxVisits,
		Burn:        l.Burn,
		Remaining:   remaining,
		HasPassword: l.PasswordHash != nil,

		PurgeAfterBurn: l.PurgeAfterBurn,
	}

}

// shortBaseURL 优先使用配置的 BaseURL，否则根据请求 Host 拼。
func shortBaseURL(r *http.Request, cfg *config.Config) string {
	if cfg.BaseURL != "" {
		return strings.TrimRight(cfg.BaseURL, "/")
	}
	return "http://" + r.Host
}

// parseID 从路由里取 id，非法返回 false。
func parseID(r *http.Request) (int64, bool) {
	idStr := chi.URLParam(r, "id")
	id, err := strconv.ParseInt(idStr, 10, 64)
	if err != nil || id <= 0 {
		return 0, false
	}
	return id, true
}

// ---------- 短链跳转 ----------

// loadActiveLink 按 slug 取出可用短链。
// 不存在/已销毁/禁用/过期时直接写错误响应并返回 false，调用方无需再处理。
func loadActiveLink(w http.ResponseWriter, r *http.Request, st *store.Store, slug string) (*model.Link, bool) {
	link, err := st.GetLinkBySlug(slug)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			metrics.Default.IncRedirect("not_found")
			http.Error(w, "短链不存在", http.StatusNotFound)
			return nil, false
		}
		metrics.Default.IncRedirect("error")
		http.Error(w, "服务器错误", http.StatusInternalServerError)
		return nil, false
	}
	if link.Burn && !link.Enabled {
		metrics.Default.IncRedirect("gone")
		http.Error(w, "链接已阅销毁", http.StatusGone)
		return nil, false
	}
	if !link.Enabled {
		metrics.Default.IncRedirect("not_found")
		http.Error(w, "短链不存在", http.StatusNotFound)
		return nil, false
	}
	if link.ExpiresAt != nil && time.Now().After(*link.ExpiresAt) {
		metrics.Default.IncRedirect("gone")
		http.Error(w, "链接已过期", http.StatusGone)
		return nil, false
	}
	return link, true
}

// handleRedirect 处理短链跳转（GET /{slug}）。
// 带密码的短链先渲染密码输入页，密码校验走 POST /{slug}。
// 并发安全：限次/burn 名额由 store 层单条条件 UPDATE 原子抢占，保证精确语义。
func handleRedirect(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {

	slug := chi.URLParam(r, "slug")
	link, ok := loadActiveLink(w, r, st, slug)
	if !ok {
		return
	}
	if link.PasswordHash != nil {
		renderPasswordPage(w, slug, "", http.StatusOK)
		return
	}
	finishRedirect(w, r, link, st, cfg)
}

// handlePasswordUnlock 校验访问密码（POST /{slug}），通过后走正常跳转流程。
// 未设密码的短链收到 POST 也直接跳转（兼容直接 POST 的客户端）。
// 密码错误不计点击、不触发阅后即焚。
func handlePasswordUnlock(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	slug := chi.URLParam(r, "slug")
	link, ok := loadActiveLink(w, r, st, slug)
	if !ok {
		return
	}
	if link.PasswordHash == nil {
		finishRedirect(w, r, link, st, cfg)
		return
	}
	if err := r.ParseForm(); err != nil {
		renderPasswordPage(w, slug, "请求解析失败，请重试", http.StatusBadRequest)
		return
	}
	if !auth.CheckPassword(*link.PasswordHash, r.FormValue("password")) {
		metrics.Default.IncPasswordAttempt(false)
		if passalert.Default.RecordFail(slug, time.Now()) {
			failCount := passalert.Default.FailCount(slug, time.Now())
			metrics.Default.IncPasswordFailAlert()
			log.Printf("[passalert] 短链 %s 密码失败高告警：窗口内失败 %d 次（阈值 %d）", slug, failCount, cfg.PasswordFailAlertThreshold)
			for _, u := range cfg.AlertWebhookURLs {
				go passalert.NotifyPasswordFailAlert(u, r.Host, slug, failCount, cfg.PasswordFailAlertWindow, cfg.PasswordFailAlertThreshold)
			}
		}
		ip := clientIP(r, cfg)

		if passalert.Default.RecordIPFail(ip, time.Now()) {
			ipFailCount := passalert.Default.IPFailCount(ip, time.Now())
			metrics.Default.IncPasswordFailAlert()
			log.Printf("[passalert] IP %s 密码失败高告警：窗口内失败 %d 次（阈值 %d）", passalert.HashIP(ip), ipFailCount, cfg.PasswordFailAlertIPThreshold)
			for _, u := range cfg.AlertWebhookURLs {
				go passalert.NotifyPasswordFailAlertIP(u, r.Host, ip, ipFailCount, cfg.PasswordFailAlertWindow, cfg.PasswordFailAlertIPThreshold)
			}
		}
		renderPasswordPage(w, slug, "密码错误，请重试", http.StatusUnauthorized)
		return
	}
	metrics.Default.IncPasswordAttempt(true)
	finishRedirect(w, r, link, st, cfg)
}

// clientIP 取客户端 IP。X-Forwarded-For / X-Real-IP 只在直连接入方（RemoteAddr）
// 落在 cfg.TrustedProxies（LINKSHORT_TRUSTED_PROXIES）内时才被信任；
// 未配置可信代理（默认）或直连方不在名单中时一律回退到 RemoteAddr，
// 防止公网攻击者伪造 XFF 稀释 IP 维度的密码失败告警计数。
// X-Forwarded-For 可能含多个 IP（客户端, 代理1, 代理2），信任时取第一段；非法值则继续回退。
func clientIP(r *http.Request, cfg *config.Config) string {
	if trustedPeer(r.RemoteAddr, cfg) {
		if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
			if first := strings.TrimSpace(strings.Split(xff, ",")[0]); net.ParseIP(first) != nil {
				return first
			}
		}
		if xrip := strings.TrimSpace(r.Header.Get("X-Real-IP")); net.ParseIP(xrip) != nil {
			return xrip
		}
	}
	return clientHost(r.RemoteAddr)
}

// trustedPeer 判定直连接入方是否为已配置的可信代理；cfg 为 nil 时视为不可信。
func trustedPeer(remoteAddr string, cfg *config.Config) bool {
	if cfg == nil {
		return false
	}
	return cfg.IsTrustedProxy(net.ParseIP(clientHost(remoteAddr)))
}

// finishRedirect 执行跳转前的最终检查（限次访问）并完成跳转。
// 只有成功解锁（密码正确或无密码）才会走到这里：记访问、处理阅后即焚、302。
func finishRedirect(w http.ResponseWriter, r *http.Request, link *model.Link, st *store.Store, cfg *config.Config) {
	// 统一准备访问上下文。失败只记日志不阻断跳转。
	// clientIP 只在可信代理后才取 XFF/X-Real-IP，直连时退化为 RemoteAddr。
	cip := clientIP(r, cfg)

	ipHash := hashIP(cip)
	ua := truncate(r.UserAgent(), 256)
	referer := truncate(r.Referer(), 512)
	loc := geo.LookupRequest(cip, r.Header.Get)

	// burn 优先：API 层面若同时设置 burn 与 max_visits，burn 语义胜出。
	if link.Burn {
		burned, err := st.TryBurn(link.ID)
		if err != nil {
			metrics.Default.IncRedirect("error")
			http.Error(w, "服务器错误", http.StatusInternalServerError)
			return
		}
		if !burned {
			metrics.Default.IncRedirect("gone")
			http.Error(w, "链接已阅销毁", http.StatusGone)
			return
		}
		if err := st.RecordVisitGeo(link.ID, ipHash, ua, referer, loc.CountryCode, loc.CountryName, loc.Province, loc.City); err != nil {
			log.Printf("handler: 记录访问失败 link=%d: %v", link.ID, err)
		}
		metrics.Default.IncBurned()
		purgeCause := ""
		if link.PurgeAfterBurn {
			purgeCause = "per-link"
		} else if cfg.BurnPurgeAfterDestroy {
			purgeCause = "env"
		}
		if purgeCause != "" {
			if perr := st.PurgeLink(link.ID); perr != nil {
				log.Printf("handler: 彻底删除已销毁链接失败 link=%d: %v", link.ID, perr)
			} else {
				log.Printf("handler: 彻底删除已销毁链接 link=%d slug=%s cause=%s", link.ID, link.Slug, purgeCause)
				metrics.Default.IncBurnPurged()
			}
		}
		metrics.Default.IncRedirect("ok")
		http.Redirect(w, r, link.URL, http.StatusFound)
		return
	}

	// max_visits 限次分支：单条条件 UPDATE 原子消费额度并计数。
	if link.MaxVisits != nil {
		ok, err := st.TryConsumeVisit(link.ID)
		if err != nil {
			metrics.Default.IncRedirect("error")
			http.Error(w, "服务器错误", http.StatusInternalServerError)
			return
		}
		if !ok {
			metrics.Default.IncRedirect("gone")
			http.Error(w, "链接已达访问上限", http.StatusGone)
			return
		}
		if err := st.RecordVisitNoCount(link.ID, ipHash, ua, referer, loc.CountryCode, loc.CountryName, loc.Province, loc.City); err != nil {
			log.Printf("handler: 记录访问失败 link=%d: %v", link.ID, err)
		}
		metrics.Default.IncRedirect("ok")
		http.Redirect(w, r, link.URL, http.StatusFound)
		return
	}

	// 普通分支：原样记录访问（visits 行 + clicks+1）后跳转。
	if err := st.RecordVisitGeo(link.ID, ipHash, ua, referer, loc.CountryCode, loc.CountryName, loc.Province, loc.City); err != nil {
		log.Printf("handler: 记录访问失败 link=%d: %v", link.ID, err)
	}
	metrics.Default.IncRedirect("ok")
	http.Redirect(w, r, link.URL, http.StatusFound)
}

// clientHost 从 RemoteAddr 去掉端口。
func clientHost(remoteAddr string) string {
	if h, _, err := net.SplitHostPort(remoteAddr); err == nil {
		return h
	}
	return remoteAddr
}

// hashIP 把 RemoteAddr 去掉端口后做 sha256，取前 16 个 hex 字符。
func hashIP(remoteAddr string) string {
	host := remoteAddr
	if h, _, err := net.SplitHostPort(remoteAddr); err == nil {
		host = h
	}
	sum := sha256.Sum256([]byte(host))
	return hex.EncodeToString(sum[:])[:16]
}

// truncate 按 rune 截断字符串。
func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n])
}

// ---------- /api/links ----------

type createLinkReq struct {
	URL       string  `json:"url"`
	Slug      string  `json:"slug"`
	Title     string  `json:"title"`
	ExpiresAt *string `json:"expires_at"`
	MaxVisits *int64  `json:"max_visits"`
	Burn      bool    `json:"burn"`
	Purge     *bool   `json:"purge"`
	Password  string  `json:"password"`
}

func handleCreateLink(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	var req createLinkReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "请求体解析失败")
		return
	}
	req.URL = strings.TrimSpace(req.URL)
	if req.URL == "" {
		writeError(w, http.StatusBadRequest, "url 不能为空")
		return
	}
	if len(req.URL) > 2048 {
		writeError(w, http.StatusBadRequest, "url 过长")
		return
	}
	if !strings.HasPrefix(req.URL, "http://") && !strings.HasPrefix(req.URL, "https://") {
		writeError(w, http.StatusBadRequest, "url 必须以 http:// 或 https:// 开头")
		return
	}
	if req.Slug != "" && !util.IsValidSlug(req.Slug) {
		writeError(w, http.StatusBadRequest, "slug 不合规")
		return
	}

	var expiresAt *time.Time
	if req.ExpiresAt != nil && *req.ExpiresAt != "" {
		t, err := time.Parse(time.RFC3339, *req.ExpiresAt)
		if err != nil {
			writeError(w, http.StatusBadRequest, "expires_at 格式错误，应为 RFC3339")
			return
		}
		expiresAt = &t
	}

	if req.MaxVisits != nil && *req.MaxVisits < 1 {
		writeError(w, http.StatusBadRequest, "max_visits 必须为正整数")
		return
	}
	if req.MaxVisits != nil && *req.MaxVisits > 1000000 {
		writeError(w, http.StatusBadRequest, "max_visits 过大")
		return
	}
	if req.Burn && req.MaxVisits != nil && *req.MaxVisits != 1 {
		writeError(w, http.StatusBadRequest, "阅后即焚不能与限次访问同时设置")
		return
	}
	if req.Purge != nil && *req.Purge && !req.Burn {
		writeError(w, http.StatusBadRequest, "只有阅后即焚链接才能设置销毁后彻底删除")
		return
	}

	var pwHash *string

	if req.Password != "" {
		if err := auth.ValidPasswordPolicy(req.Password); err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}
		h, err := auth.HashPassword(req.Password)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "密码处理失败")
			return
		}
		pwHash = &h
	}

	purge := req.Purge != nil && *req.Purge
	id, err := st.CreateLinkEx(req.Slug, req.URL, req.Title, expiresAt, req.MaxVisits, req.Burn, purge)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
	}

	if pwHash != nil {
		if err := st.SetLinkPassword(id, *pwHash); err != nil {
			// 密码落库失败时回滚整条短链，避免"建了链但密码没设上"的半吊子状态。
			if derr := st.DeleteLink(id); derr != nil {
				log.Printf("handler: 设置密码失败且回滚删除失败 id=%d: %v / %v", id, err, derr)
			}
			writeError(w, http.StatusInternalServerError, "密码设置失败")
			return
		}
	}

	link, err := st.GetLink(id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "读取新建链接失败")
		return
	}
	writeJSON(w, http.StatusCreated, toLinkJSON(link, shortBaseURL(r, cfg)))
}

func handleListLinks(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	q := r.URL.Query()
	search := q.Get("search")
	page := 1
	if s := q.Get("page"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil || v < 1 {
			writeError(w, http.StatusBadRequest, "page 非法")
			return
		}
		page = v
	}
	perPage := 20
	if s := q.Get("per_page"); s != "" {
		v, err := strconv.Atoi(s)
		if err != nil || v < 1 || v > 200 {
			writeError(w, http.StatusBadRequest, "per_page 非法")
			return
		}
		perPage = v
	}
	sort := q.Get("sort")
	if sort == "" {
		sort = "created_at"
	} else if sort != "clicks" && sort != "created_at" && sort != "expires_at" {
		writeError(w, http.StatusBadRequest, "sort 非法")
		return
	}

	var enabledPtr *bool
	enabledStr := q.Get("enabled")
	switch enabledStr {
	case "":
		enabledPtr = nil
	case "true":
		v := true
		enabledPtr = &v
	case "false":
		v := false
		enabledPtr = &v
	default:
		writeError(w, http.StatusBadRequest, "enabled 非法")
		return
	}

	var burnPtr *bool
	burnStr := q.Get("burn")
	switch burnStr {
	case "":
		burnPtr = nil
	case "true":
		v := true
		burnPtr = &v
	case "false":
		v := false
		burnPtr = &v
	default:
		writeError(w, http.StatusBadRequest, "burn 非法")
		return
	}

	var expiredPtr *bool
	expiredStr := q.Get("expired")
	switch expiredStr {
	case "":
		expiredPtr = nil
	case "true":
		v := true
		expiredPtr = &v
	case "false":
		v := false
		expiredPtr = &v
	default:
		writeError(w, http.StatusBadRequest, "expired 非法")
		return
	}

	var hasPasswordPtr *bool
	hasPasswordStr := q.Get("has_password")
	switch hasPasswordStr {
	case "":
		hasPasswordPtr = nil
	case "true":
		v := true
		hasPasswordPtr = &v
	case "false":
		v := false
		hasPasswordPtr = &v
	default:
		writeError(w, http.StatusBadRequest, "has_password 非法")
		return
	}

	links, total, err := st.ListLinksFilteredEx3(search, page, perPage, sort, enabledPtr, burnPtr, expiredPtr, hasPasswordPtr)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	base := shortBaseURL(r, cfg)
	items := make([]linkJSON, 0, len(links))
	for _, l := range links {
		items = append(items, toLinkJSON(l, base))
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":    items,
		"total":    total,
		"page":     page,
		"per_page": perPage,
	})
}

func handleGetLink(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	link, err := st.GetLink(id)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, http.StatusNotFound, "链接不存在")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, toLinkJSON(link, shortBaseURL(r, cfg)))
}

type patchLinkReq struct {
	Title     *string         `json:"title"`
	Enabled   *bool           `json:"enabled"`
	ExpiresAt json.RawMessage `json:"expires_at"`
	MaxVisits json.RawMessage `json:"max_visits"`
	Burn      *bool           `json:"burn"`
	Purge     *bool           `json:"purge"`
	Password  *string         `json:"password"`
}

func handlePatchLink(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	existing, err := st.GetLink(id)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, http.StatusNotFound, "链接不存在")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	var req patchLinkReq
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "请求体解析失败")
		return
	}

	title := existing.Title
	if req.Title != nil {
		title = *req.Title
	}
	enabled := existing.Enabled
	if req.Enabled != nil {
		enabled = *req.Enabled
	}
	expiresAt := existing.ExpiresAt
	// 传入 null 则清除；传入字符串则解析。
	if len(req.ExpiresAt) > 0 {
		if string(req.ExpiresAt) == "null" {
			expiresAt = nil
		} else {
			var s string
			if err := json.Unmarshal(req.ExpiresAt, &s); err != nil {
				writeError(w, http.StatusBadRequest, "expires_at 格式错误")
				return
			}
			if s == "" {
				expiresAt = nil
			} else {
				t, err := time.Parse(time.RFC3339, s)
				if err != nil {
					writeError(w, http.StatusBadRequest, "expires_at 格式错误，应为 RFC3339")
					return
				}
				expiresAt = &t
			}
		}
	}

	maxVisits := existing.MaxVisits
	if len(req.MaxVisits) > 0 {
		if string(req.MaxVisits) == "null" {
			maxVisits = nil
		} else {
			var mv int64
			if err := json.Unmarshal(req.MaxVisits, &mv); err != nil {
				writeError(w, http.StatusBadRequest, "max_visits 格式错误")
				return
			}
			if mv < 1 || mv > 1000000 {
				writeError(w, http.StatusBadRequest, "max_visits 必须为正整数且不超过 1000000")
				return
			}
			maxVisits = &mv
		}
	}
	burn := existing.Burn
	if req.Burn != nil {
		burn = *req.Burn
	}
	purge := existing.PurgeAfterBurn
	if req.Purge != nil {
		purge = *req.Purge
	}
	if burn && maxVisits != nil && *maxVisits != 1 {
		writeError(w, http.StatusBadRequest, "阅后即焚不能与限次访问同时设置")
		return
	}
	if purge && !burn {
		writeError(w, http.StatusBadRequest, "只有阅后即焚链接才能设置销毁后彻底删除")
		return
	}

	if req.Password != nil {
		if *req.Password == "" {
			if err := st.ClearLinkPassword(id); err != nil {
				writeError(w, http.StatusInternalServerError, "清除密码失败")
				return
			}
		} else {
			if err := auth.ValidPasswordPolicy(*req.Password); err != nil {
				writeError(w, http.StatusBadRequest, err.Error())
				return
			}
			h, err := auth.HashPassword(*req.Password)
			if err != nil {
				writeError(w, http.StatusInternalServerError, "密码处理失败")
				return
			}
			if err := st.SetLinkPassword(id, h); err != nil {
				writeError(w, http.StatusInternalServerError, "密码设置失败")
				return
			}
		}
	}

	if err := st.UpdateLinkEx(id, title, enabled, expiresAt, maxVisits, burn, purge); err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	updated, err := st.GetLink(id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, "读取更新结果失败")
		return
	}
	writeJSON(w, http.StatusOK, toLinkJSON(updated, shortBaseURL(r, cfg)))
}

func handleDeleteLink(w http.ResponseWriter, r *http.Request, st *store.Store) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	if err := st.DeleteLink(id); err != nil {
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, http.StatusNotFound, "链接不存在")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func handleQRCode(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	link, err := st.GetLink(id)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			writeError(w, http.StatusNotFound, "链接不存在")
			return
		}
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	sizeRaw := r.URL.Query().Get("size")
	size := 256
	if sizeRaw != "" {
		v, err := strconv.Atoi(sizeRaw)
		if err != nil {
			writeError(w, http.StatusBadRequest, "size 非法")
			return
		}
		size = v
	}
	if size <= 0 {
		writeError(w, http.StatusBadRequest, "size 非法")
		return
	}

	content := shortBaseURL(r, cfg) + "/" + link.Slug
	w.Header().Set("Content-Type", "image/png")
	if err := qr.PNG(w, content, size); err != nil {
		// 若已经写了头，只能记日志。
		log.Printf("handler: 生成二维码失败: %v", err)
	}
}

func handleLinkDaily(w http.ResponseWriter, r *http.Request, st *store.Store) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	daysStr := r.URL.Query().Get("days")
	days := 30
	if daysStr != "" {
		d, err := strconv.Atoi(daysStr)
		if err != nil {
			writeError(w, http.StatusBadRequest, "days 非法")
			return
		}
		days = d
	}
	if days <= 0 || days > 365 {
		days = 30
	}
	stats, err := st.LinkDailyClicks(id, days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	items := make([]map[string]any, 0, len(stats))
	for _, s := range stats {
		items = append(items, map[string]any{"date": s.Date, "clicks": s.Clicks})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

// handleLinkReferers 返回单条链接的来源 Top N。
func handleLinkReferers(w http.ResponseWriter, r *http.Request, st *store.Store) {
	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	nStr := r.URL.Query().Get("n")
	n := 8
	if nStr != "" {
		var err error
		n, err = strconv.Atoi(nStr)
		if err != nil {
			writeError(w, http.StatusBadRequest, "n 非法")
			return
		}
	}
	if n <= 0 || n > 100 {
		n = 8
	}
	stats, err := st.LinkTopReferers(id, n)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": namedStats(stats)})
}

func handleLinkUA(w http.ResponseWriter, r *http.Request, st *store.Store) {

	id, ok := parseID(r)
	if !ok {
		writeError(w, http.StatusBadRequest, "id 非法")
		return
	}
	ov, err := st.UAStats(id)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	devs := make([]map[string]any, 0, len(ov.Devices))
	for _, s := range ov.Devices {
		devs = append(devs, map[string]any{"name": s.Name, "clicks": s.Clicks})
	}
	brows := make([]map[string]any, 0, len(ov.Browsers))
	for _, s := range ov.Browsers {
		brows = append(brows, map[string]any{"name": s.Name, "clicks": s.Clicks})
	}
	oss := make([]map[string]any, 0, len(ov.OSList))
	for _, s := range ov.OSList {
		oss = append(oss, map[string]any{"name": s.Name, "clicks": s.Clicks})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"link_id":  ov.LinkID,
		"total":    ov.Total,
		"bots":     ov.Bots,
		"devices":  devs,
		"browsers": brows,
		"os":       oss,
	})
}

// ---------- /api/stats ----------

func handleStatsOverview(w http.ResponseWriter, r *http.Request, st *store.Store) {
	links, enabled, total, today, err := st.StatsOverview()
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"links":         links,
		"enabled_links": enabled,
		"total_clicks":  total,
		"today_clicks":  today,
	})
}

func handleStatsDaily(w http.ResponseWriter, r *http.Request, st *store.Store) {
	days := parseIntDefault(r.URL.Query().Get("days"), 30)
	if days <= 0 || days > 365 {
		days = 30
	}
	stats, err := st.DailyClicks(days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	items := make([]map[string]any, 0, len(stats))
	for _, s := range stats {
		items = append(items, map[string]any{"date": s.Date, "clicks": s.Clicks})
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": items})
}

func handleTopLinks(w http.ResponseWriter, r *http.Request, st *store.Store) {
	n := parseIntDefault(r.URL.Query().Get("n"), 8)
	if n <= 0 || n > 100 {
		n = 8
	}
	stats, err := st.TopLinks(n)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": namedStats(stats)})
}

func handleTopReferers(w http.ResponseWriter, r *http.Request, st *store.Store) {
	n := parseIntDefault(r.URL.Query().Get("n"), 8)
	if n <= 0 || n > 100 {
		n = 8
	}
	stats, err := st.TopReferers(n)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"items": namedStats(stats)})
}

// handleStatsGeo 返回地域概览：按国家/省份/城市聚合的 TopN、总点击数、总 UV、unknown 占比。
// link_id=0（默认）为全局；days 仅接受 7/30，否则按 30；country 可选；n 默认 8，范围 1~100。
func handleStatsGeo(w http.ResponseWriter, r *http.Request, st *store.Store) {
	linkID := parseIntDefault(r.URL.Query().Get("link_id"), 0)
	if linkID < 0 {
		linkID = 0
	}
	days := parseIntDefault(r.URL.Query().Get("days"), 30)
	if days != 7 && days != 30 {
		days = 30
	}
	country := strings.TrimSpace(r.URL.Query().Get("country"))
	n := parseIntDefault(r.URL.Query().Get("n"), 8)
	if n <= 0 || n > 100 {
		n = 8
	}
	ov, err := st.GeoStats(int64(linkID), days, country, n)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	out := make([]map[string]any, 0, len(ov.Items))
	for _, s := range ov.Items {
		out = append(out, map[string]any{
			"country_code": s.CountryCode,
			"country_name": s.CountryName,
			"province":     s.Province,
			"city":         s.City,
			"clicks":       s.Clicks,
			"uv":           s.UV,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"items":        out,
		"unknown_pct":  ov.UnknownPct,
		"total_clicks": ov.TotalClicks,
		"total_uv":     ov.TotalUV,
		"days":         ov.Days,
	})
}

func handleStatsHourly(w http.ResponseWriter, req *http.Request, st *store.Store) {
	linkID := int64(parseIntDefault(req.URL.Query().Get("link_id"), 0))
	if linkID < 0 {
		linkID = 0
	}
	days := parseIntDefault(req.URL.Query().Get("days"), 30)
	if days != 1 && days != 7 && days != 30 {
		days = 30
	}
	hs, err := st.HourlyStats(linkID, days)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"hours":        hs.Hours,
		"weekdays":     hs.Weekdays,
		"total_clicks": hs.Total,
		"days":         hs.Days,
		"link_id":      hs.LinkID,
	})
}

func namedStats(stats []model.NamedStat) []map[string]any {
	items := make([]map[string]any, 0, len(stats))
	for _, s := range stats {
		items = append(items, map[string]any{"name": s.Name, "clicks": s.Clicks})
	}
	return items
}

// ---------- 导入导出 ----------

func handleImport(w http.ResponseWriter, r *http.Request, st *store.Store) {
	if err := r.ParseMultipartForm(16 << 20); err != nil {
		writeError(w, http.StatusBadRequest, "表单解析失败")
		return
	}
	file, _, err := r.FormFile("file")
	if err != nil {
		writeError(w, http.StatusBadRequest, "缺少 file 字段")
		return
	}
	defer file.Close()

	imported, skipped, errs := st.ImportCSV(file)
	if errs == nil {
		errs = []string{}
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"imported": imported,
		"skipped":  skipped,
		"errors":   errs,
	})
}

func handleExport(w http.ResponseWriter, r *http.Request, st *store.Store) {
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="linkshort-export.csv"`)
	if err := st.ExportCSV(w); err != nil {
		log.Printf("handler: 导出 CSV 失败: %v", err)
	}
}

// handleExportGeoCSV 导出地域分布 CSV：国家代码,国家,省份,城市,点击,独立访客。
func handleExportGeoCSV(w http.ResponseWriter, r *http.Request, st *store.Store) {
	linkID := parseIntDefault(r.URL.Query().Get("link_id"), 0)
	if linkID < 0 {
		linkID = 0
	}
	days := parseIntDefault(r.URL.Query().Get("days"), 30)
	if days != 7 && days != 30 {
		days = 30
	}
	ov, err := st.GeoStats(int64(linkID), days, "", 100)
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	w.Header().Set("Content-Type", "text/csv; charset=utf-8")
	w.Header().Set("Content-Disposition", `attachment; filename="linkshort-geo-`+strconv.Itoa(days)+`d.csv"`)
	bw := bufio.NewWriter(w)
	bw.WriteString("\xEF\xBB\xBF") // BOM，Excel 直接打开不乱码
	cw := csv.NewWriter(bw)
	cw.Write([]string{"国家代码", "国家", "省份", "城市", "点击", "独立访客"})
	for _, s := range ov.Items {
		cw.Write([]string{
			s.CountryCode, s.CountryName, s.Province, s.City,
			strconv.FormatInt(s.Clicks, 10), strconv.FormatInt(s.UV, 10),
		})
	}
	cw.Flush()
	bw.Flush()
}

// ---------- 小工具 ----------

func parseIntDefault(s string, def int) int {
	if s == "" {
		return def
	}
	v, err := strconv.Atoi(s)
	if err != nil {
		return def
	}
	return v
}

// handleReadyz 就绪探针：数据库 ping 通返回 200，否则 503。
func handleReadyz(w http.ResponseWriter, req *http.Request, st *store.Store) {
	if err := st.Ping(); err != nil {
		log.Printf("handler: readyz 检查失败: %v", err)
		writeJSON(w, http.StatusServiceUnavailable, map[string]any{"ok": false, "error": "db unreachable"})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

// 保证 io 引用（ImportCSV 需要 io.Reader，此处仅作编译期防呆）。
var _ = io.EOF
var _ = fmt.Sprintf
