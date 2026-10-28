// Package api 提供 HTTP API 服务。
package api

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io/fs"
	"math"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	logpkg "github.com/Wanfeng1028/muse/second-brain/internal/log"
	"github.com/Wanfeng1028/muse/second-brain/internal/markdown"
	"github.com/Wanfeng1028/muse/second-brain/internal/metrics"
	"github.com/Wanfeng1028/muse/second-brain/internal/ratelimit"
	"github.com/Wanfeng1028/muse/second-brain/internal/search"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
	"github.com/Wanfeng1028/muse/second-brain/internal/web"
)

// NewServer 创建并返回配置好全部路由的 HTTP handler。
func NewServer(st *store.Store, cfg config.Config) http.Handler {
	mux := http.NewServeMux()

	// 健康检查
	mux.HandleFunc("GET /api/health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	// /metrics 路由（v0.12+）：Prometheus 文本格式，支持 SB_METRICS_TOKEN 鉴权。
	reg := metrics.Default()
	mux.HandleFunc("GET /metrics", func(w http.ResponseWriter, r *http.Request) {
		if !cfg.Metrics.Enabled {
			writeError(w, r, http.StatusNotFound, "metrics disabled")
			return
		}
		if cfg.Metrics.Token != "" && subtle.ConstantTimeCompare([]byte(r.Header.Get("Authorization")), []byte("Bearer "+cfg.Metrics.Token)) != 1 {
			writeError(w, r, http.StatusUnauthorized, "unauthorized")
			return
		}
		reg.Handler().ServeHTTP(w, r)
	})

	// 笔记列表
	mux.HandleFunc("GET /api/notes", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		tag := q.Get("tag")
		limit := 50
		if ls := q.Get("limit"); ls != "" {
			v, err := strconv.Atoi(ls)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "limit 参数非法")
				return
			}
			limit = v
		}
		if limit < 0 {
			limit = 0
		}
		offset := 0
		if rawOffset := q.Get("offset"); rawOffset != "" {
			v, err := strconv.Atoi(rawOffset)
			if err != nil {
				writeError(w, r, http.StatusBadRequest, "offset 参数非法")
				return
			}
			offset = v
		}
		if offset < 0 {
			offset = 0
		}
		notes, err := st.ListNotes(tag, limit, offset)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		if notes == nil {
			notes = []store.Note{}
		}
		writeJSON(w, http.StatusOK, notes)
	})

	// 创建笔记
	mux.HandleFunc("POST /api/notes", func(w http.ResponseWriter, r *http.Request) {
		var n store.Note
		if err := json.NewDecoder(r.Body).Decode(&n); err != nil {
			writeError(w, r, http.StatusBadRequest, "invalid json body")
			return
		}
		if strings.TrimSpace(n.Title) == "" {
			writeError(w, r, http.StatusBadRequest, "title is required")
			return
		}
		created, err := st.CreateNoteFor(r.Context(), n, CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		logpkg.RequestLogger(r.Context()).Info("note.created",
			"note_id", created.ID, "user", CurrentUser(r))
		writeJSON(w, http.StatusCreated, created)
	})

	// 获取单条笔记
	mux.HandleFunc("GET /api/notes/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		n, err := st.GetNote(id)
		if err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, n)
	})

	// 更新笔记
	mux.HandleFunc("PUT /api/notes/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		var n store.Note
		if err := json.NewDecoder(r.Body).Decode(&n); err != nil {
			writeError(w, r, http.StatusBadRequest, "invalid json body")
			return
		}
		n.ID = id
		if strings.TrimSpace(n.Title) == "" {
			writeError(w, r, http.StatusBadRequest, "title is required")
			return
		}
		updated, err := st.UpdateNote(n)
		if err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, updated)
	})

	// 删除笔记
	mux.HandleFunc("DELETE /api/notes/{id}", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		if err := st.DeleteNote(id); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	// 笔记 Markdown 预览
	mux.HandleFunc("GET /api/notes/{id}/preview", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		n, err := st.GetNote(id)
		if err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"html": markdown.Render(n.Body)})
	})

	// 反向链接：哪些笔记引用了这篇
	mux.HandleFunc("GET /api/notes/{id}/backlinks", func(w http.ResponseWriter, r *http.Request) {
		id, ok := parseID(w, r)
		if !ok {
			return
		}
		if _, err := st.GetNote(id); err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, r, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		bl, err := st.Backlinks(id)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, bl)
	})

	// 搜索
	mux.HandleFunc("GET /api/search", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("q")
		format := r.URL.Query().Get("format")
		legacy := false
		switch format {
		case "", "object":
			legacy = false
		case "legacy":
			legacy = true
		default:
			writeError(w, r, http.StatusBadRequest, "无效的 format 参数")
			return
		}
		if strings.TrimSpace(q) == "" {
			if legacy {
				writeJSON(w, http.StatusOK, []store.Note{})
				return
			}
			writeJSON(w, http.StatusOK, map[string]any{
				"query": "",
				"terms": []string{},
				"notes": []store.Note{},
				"meta":  []any{},
			})
			return
		}
		notes, err := st.SearchNotes(q)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		ranked := search.RankDetailed(notes, q)
		terms := search.QueryTerms(q)
		if terms == nil {
			terms = []string{}
		}
		fallback := false
		if len(ranked) == 0 && len(terms) >= 2 {
			notesAny, err2 := st.SearchNotesAny(q)
			if err2 != nil {
				writeError(w, r, http.StatusInternalServerError, err2.Error())
				return
			}
			ranked = search.RankOr(notesAny, q, 0)
			fallback = len(ranked) > 0
		}
		outNotes := make([]store.Note, 0, len(ranked))
		meta := make([]map[string]any, 0, len(ranked))
		for _, rn := range ranked {
			outNotes = append(outNotes, rn.Note)
			fields := make([]string, 0, 3)
			hasTitle := false
			hasTag := false
			hasBody := false
			for _, m := range rn.Matches {
				switch m.Field {
				case search.FieldTitle:
					hasTitle = true
				case search.FieldTag:
					hasTag = true
				case search.FieldBody:
					hasBody = true
				}
			}
			if hasTitle {
				fields = append(fields, "标题")
			}
			if hasTag {
				fields = append(fields, "标签")
			}
			if hasBody {
				fields = append(fields, "正文")
			}
			meta = append(meta, map[string]any{
				"id":     rn.Note.ID,
				"score":  rn.Score,
				"fields": fields,
			})
		}
		if legacy {
			writeJSON(w, http.StatusOK, outNotes)
			return
		}
		writeJSON(w, http.StatusOK, map[string]any{
			"query":    q,
			"terms":    terms,
			"notes":    outNotes,
			"meta":     meta,
			"fallback": fallback,
		})
	})

	// 标签列表
	mux.HandleFunc("GET /api/tags", func(w http.ResponseWriter, r *http.Request) {
		tags, err := st.ListTags()
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		if tags == nil {
			tags = []store.TagCount{}
		}
		writeJSON(w, http.StatusOK, tags)
	})

	// 统计信息
	mux.HandleFunc("GET /api/stats", func(w http.ResponseWriter, r *http.Request) {
		s, err := st.Stats()
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, s)
	})

	// 图谱数据
	mux.HandleFunc("GET /api/graph", func(w http.ResponseWriter, r *http.Request) {
		g, err := st.Graph()
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		if g.Nodes == nil {
			g.Nodes = []store.GraphNode{}
		}
		if g.Edges == nil {
			g.Edges = []store.GraphEdge{}
		}
		writeJSON(w, http.StatusOK, g)
	})

	// 复习引擎路由（见 review.go）
	RegisterReviewRoutes(mux, st)

	// 附件路由（见 attachment.go）
	RegisterAttachmentRoutes(mux, st)

	// 导出路由（见 export.go）
	RegisterExportRoutes(mux, st)

	// 推送路由（见 push.go）
	RegisterPushRoutes(mux, st, cfg)

	// 静态文件子系统（embed.FS），PWA 路由与文件服务共用。
	staticFS, err := fs.Sub(web.StaticFS(), ".")
	if err != nil {
		staticFS = web.StaticFS()
	}

	// PWA：Service Worker 必须从站点根提供（scope 为 /），且带 Service-Worker-Allowed 头；
	// manifest 需要正确的 content type。
	mux.HandleFunc("GET /sw.js", func(w http.ResponseWriter, r *http.Request) {
		data, err := fs.ReadFile(staticFS, "sw.js")
		if err != nil {
			writeError(w, r, http.StatusNotFound, "not found")
			return
		}
		w.Header().Set("Content-Type", "application/javascript; charset=utf-8")
		w.Header().Set("Service-Worker-Allowed", "/")
		w.Header().Set("Cache-Control", "no-cache")
		_, _ = w.Write(data)
	})
	mux.HandleFunc("GET /manifest.webmanifest", func(w http.ResponseWriter, r *http.Request) {
		data, err := fs.ReadFile(staticFS, "manifest.webmanifest")
		if err != nil {
			writeError(w, r, http.StatusNotFound, "not found")
			return
		}
		w.Header().Set("Content-Type", "application/manifest+json; charset=utf-8")
		_, _ = w.Write(data)
	})

	// 静态文件服务，根路径返回 index.html
	fileServer := http.FileServerFS(staticFS)
	mux.Handle("GET /static/", http.StripPrefix("/static/", fileServer))
	mux.HandleFunc("GET /", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			// 尝试提供静态文件，找不到时回退 index.html
			if _, err := fs.Stat(staticFS, strings.TrimPrefix(r.URL.Path, "/")); err == nil {
				fileServer.ServeHTTP(w, r)
				return
			}
		}
		// 注意：不能用 fileServer serve "/index.html"——Go 的 FileServer 会把
		// 形如 /index.html 的路径 301 重定向到 ./，故直接读文件写入。
		data, err := fs.ReadFile(staticFS, "index.html")
		if err != nil {
			writeError(w, r, http.StatusNotFound, "not found")
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(data)
	})

	// v0.12 指标 gauge：采集时实时查库，失败记 NaN。
	reg.SetGaugeFunc("notes_total", func() float64 {
		s, err := st.Stats()
		if err != nil {
			return math.NaN()
		}
		return float64(s.Notes)
	})
	reg.SetGaugeFunc("reviews_due", func() float64 {
		rs, err := st.ReviewStats(time.Now(), store.DefaultUser)
		if err != nil {
			return math.NaN()
		}
		return float64(rs.DueToday)
	})

	reg.SetGaugeLabelsFunc("reviews_due_by_user", func() map[string]float64 {
		out := map[string]float64{}
		now := time.Now()
		users, err := st.ListUsersWithDueReviews(now)
		if err != nil {
			return out
		}
		seen := map[string]bool{}
		for _, u := range users {
			rs, err := st.ReviewStats(now, u)
			if err != nil {
				continue
			}
			out[u] = float64(rs.DueToday)
			seen[u] = true
		}
		if !seen[store.DefaultUser] {
			if rs, err := st.ReviewStats(now, store.DefaultUser); err == nil {
				out[store.DefaultUser] = float64(rs.DueToday)
			}
		}
		return out
	})

	// 中间件链（外层 -> 内层）：request_id -> metrics -> ratelimit -> mux。
	// metrics 在 ratelimit 外层，因此 429 拒绝也会被计数（route 走回退归一化）；
	// ratelimit 在最内层，拒绝时 context 里已有 request_id，429 body 能带上。
	var handler http.Handler = mux
	handler = ratelimit.New(ratelimit.Config{
		Enabled:    cfg.RateLimit.Enabled,
		RPS:        cfg.RateLimit.RPS,
		Burst:      cfg.RateLimit.Burst,
		WriteRPS:   cfg.RateLimit.WriteRPS,
		WriteBurst: cfg.RateLimit.WriteBurst,
	}).Middleware(CurrentUser, handler)
	handler = reg.Middleware(handler)
	return logpkg.Middleware(handler)
}

// writeJSON 序列化并写出 JSON 响应。
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError 以统一格式写出错误 JSON，响应体恒带 request_id，方便按 ID 查日志定位。
func writeError(w http.ResponseWriter, r *http.Request, status int, msg string) {
	body := map[string]string{"error": msg}
	if id := logpkg.FromContext(r.Context()); id != "" {
		body["request_id"] = id
	}
	writeJSON(w, status, body)
}

// parseID 从路径中解析 id，失败时写出 400 并返回 false。
func parseID(w http.ResponseWriter, r *http.Request) (int64, bool) {
	raw := r.PathValue("id")
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, r, http.StatusBadRequest, "invalid id")
		return 0, false
	}
	return id, true
}

// parseIntDefault 解析整数，失败返回默认值。
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
