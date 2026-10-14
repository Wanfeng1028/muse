// Package handler 提供 linkshort 的 HTTP 层：路由、鉴权、API、Web UI 托管与短链跳转。
package handler

import (
	"crypto/sha256"
	"embed"
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

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/model"
	"github.com/Wanfeng1028/muse/linkshort/internal/qr"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

//go:embed web
var webFS embed.FS

// NewRouter 组装中间件、API 分组、Web UI 静态托管与短链跳转路由。
func NewRouter(st *store.Store, cfg *config.Config) http.Handler {
	r := chi.NewRouter()

	r.Use(middleware.RequestID)
	r.Use(middleware.RealIP)
	r.Use(middleware.Logger)
	r.Use(middleware.Recoverer)
	r.Use(middleware.Timeout(30 * time.Second))

	// 根路径跳转到 UI。
	r.Get("/", func(w http.ResponseWriter, req *http.Request) {
		http.Redirect(w, req, "/ui/", http.StatusFound)
	})

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
		api.Get("/health", func(w http.ResponseWriter, req *http.Request) {
			writeJSON(w, http.StatusOK, map[string]any{"ok": true})
		})
		api.Get("/meta", func(w http.ResponseWriter, req *http.Request) {
			writeJSON(w, http.StatusOK, map[string]any{"base_url": shortBaseURL(req, cfg)})
		})

		api.Post("/links", func(w http.ResponseWriter, req *http.Request) { handleCreateLink(w, req, st, cfg) })
		api.Get("/links", func(w http.ResponseWriter, req *http.Request) { handleListLinks(w, req, st, cfg) })
		api.Get("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handleGetLink(w, req, st, cfg) })
		api.Patch("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handlePatchLink(w, req, st, cfg) })
		api.Delete("/links/{id}", func(w http.ResponseWriter, req *http.Request) { handleDeleteLink(w, req, st) })
		api.Get("/links/{id}/qrcode.png", func(w http.ResponseWriter, req *http.Request) { handleQRCode(w, req, st, cfg) })
		api.Get("/links/{id}/daily", func(w http.ResponseWriter, req *http.Request) { handleLinkDaily(w, req, st) })

		api.Get("/stats/overview", func(w http.ResponseWriter, req *http.Request) { handleStatsOverview(w, req, st) })
		api.Get("/stats/daily", func(w http.ResponseWriter, req *http.Request) { handleStatsDaily(w, req, st) })
		api.Get("/stats/top-links", func(w http.ResponseWriter, req *http.Request) { handleTopLinks(w, req, st) })
		api.Get("/stats/top-referers", func(w http.ResponseWriter, req *http.Request) { handleTopReferers(w, req, st) })

		api.Post("/import", func(w http.ResponseWriter, req *http.Request) { handleImport(w, req, st) })
		api.Get("/export.csv", func(w http.ResponseWriter, req *http.Request) { handleExport(w, req, st) })
	})

	// 短链跳转（放最后，避免覆盖已注册前缀）。
	r.Get("/{slug}", func(w http.ResponseWriter, req *http.Request) { handleRedirect(w, req, st) })

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
	ID        int64   `json:"id"`
	Slug      string  `json:"slug"`
	URL       string  `json:"url"`
	Title     string  `json:"title"`
	Clicks    int64   `json:"clicks"`
	Enabled   bool    `json:"enabled"`
	ExpiresAt *string `json:"expires_at"`
	CreatedAt string  `json:"created_at"`
	UpdatedAt string  `json:"updated_at"`
	ShortURL  string  `json:"short_url"`
	MaxVisits *int64  `json:"max_visits"`
	Burn      bool    `json:"burn"`
	Remaining *int64  `json:"remaining"`
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
		ID:        l.ID,
		Slug:      l.Slug,
		URL:       l.URL,
		Title:     l.Title,
		Clicks:    l.Clicks,
		Enabled:   l.Enabled,
		ExpiresAt: exp,
		CreatedAt: l.CreatedAt.UTC().Format(time.RFC3339),
		UpdatedAt: l.UpdatedAt.UTC().Format(time.RFC3339),
		ShortURL:  base + "/" + l.Slug,
		MaxVisits: l.MaxVisits,
		Burn:      l.Burn,
		Remaining: remaining,
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

// handleRedirect 处理短链跳转。
// 并发说明：两次并发访问可能都通过 clicks 检查（单连接串行写入缓解，
// 未做分布式锁，文档已注明）。
func handleRedirect(w http.ResponseWriter, r *http.Request, st *store.Store) {
	slug := chi.URLParam(r, "slug")
	link, err := st.GetLinkBySlug(slug)
	if err != nil {
		if errors.Is(err, store.ErrNotFound) {
			http.Error(w, "短链不存在", http.StatusNotFound)
			return
		}
		http.Error(w, "服务器错误", http.StatusInternalServerError)
		return
	}
	if link.Burn && !link.Enabled {
		http.Error(w, "链接已阅销毁", http.StatusGone)
		return
	}
	if !link.Enabled {
		http.Error(w, "短链不存在", http.StatusNotFound)
		return
	}
	if link.ExpiresAt != nil && time.Now().After(*link.ExpiresAt) {
		http.Error(w, "链接已过期", http.StatusGone)
		return
	}
	if link.MaxVisits != nil && link.Clicks >= *link.MaxVisits {
		http.Error(w, "链接已达访问上限", http.StatusGone)
		return
	}

	// 记录访问，失败只记日志不阻断跳转。
	ipHash := hashIP(r.RemoteAddr)
	ua := truncate(r.UserAgent(), 256)
	referer := truncate(r.Referer(), 512)
	if err := st.RecordVisit(link.ID, ipHash, ua, referer); err != nil {
		log.Printf("handler: 记录访问失败 link=%d: %v", link.ID, err)
	}

	if link.Burn {
		if err := st.MarkBurned(link.ID); err != nil {
			log.Printf("handler: 标记阅后销毁失败 link=%d: %v", link.ID, err)
		}
	}

	http.Redirect(w, r, link.URL, http.StatusFound)
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

	id, err := st.CreateLinkEx(req.Slug, req.URL, req.Title, expiresAt, req.MaxVisits, req.Burn)
	if err != nil {
		writeError(w, http.StatusBadRequest, err.Error())
		return
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
	page := parseIntDefault(q.Get("page"), 1)
	if page < 1 {
		page = 1
	}
	perPage := parseIntDefault(q.Get("per_page"), 20)
	if perPage < 1 {
		perPage = 20
	}
	if perPage > 200 {
		perPage = 200
	}
	sort := q.Get("sort")
	if sort != "clicks" && sort != "created_at" {
		sort = "created_at"
	}

	links, total, err := st.ListLinks(search, page, perPage, sort)
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
	if burn && maxVisits != nil && *maxVisits != 1 {
		writeError(w, http.StatusBadRequest, "阅后即焚不能与限次访问同时设置")
		return
	}

	if err := st.UpdateLinkEx(id, title, enabled, expiresAt, maxVisits, burn); err != nil {
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

	size := parseIntDefault(r.URL.Query().Get("size"), 256)
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
	days := parseIntDefault(r.URL.Query().Get("days"), 30)
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

// 保证 io 引用（ImportCSV 需要 io.Reader，此处仅作编译期防呆）。
var _ = io.EOF
var _ = fmt.Sprintf
