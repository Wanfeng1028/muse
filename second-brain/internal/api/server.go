// Package api 提供 HTTP API 服务。
package api

import (
	"encoding/json"
	"errors"
	"io/fs"
	"net/http"
	"strconv"
	"strings"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/markdown"
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

	// 笔记列表
	mux.HandleFunc("GET /api/notes", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query()
		tag := q.Get("tag")
		limit := parseIntDefault(q.Get("limit"), 50)
		offset := parseIntDefault(q.Get("offset"), 0)
		if limit < 0 {
			limit = 0
		}
		if offset < 0 {
			offset = 0
		}
		notes, err := st.ListNotes(tag, limit, offset)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
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
			writeError(w, http.StatusBadRequest, "invalid json body")
			return
		}
		if strings.TrimSpace(n.Title) == "" {
			writeError(w, http.StatusBadRequest, "title is required")
			return
		}
		created, err := st.CreateNote(n)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
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
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
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
			writeError(w, http.StatusBadRequest, "invalid json body")
			return
		}
		n.ID = id
		if strings.TrimSpace(n.Title) == "" {
			writeError(w, http.StatusBadRequest, "title is required")
			return
		}
		updated, err := st.UpdateNote(n)
		if err != nil {
			if errors.Is(err, store.ErrNotFound) {
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
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
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
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
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
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
				writeError(w, http.StatusNotFound, "note not found")
				return
			}
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		bl, err := st.Backlinks(id)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, bl)
	})

	// 搜索
	mux.HandleFunc("GET /api/search", func(w http.ResponseWriter, r *http.Request) {
		q := r.URL.Query().Get("q")
		if strings.TrimSpace(q) == "" {
			writeJSON(w, http.StatusOK, []store.Note{})
			return
		}
		notes, err := st.SearchNotes(q)
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		ranked := search.Rank(notes, q)
		if ranked == nil {
			ranked = []store.Note{}
		}
		writeJSON(w, http.StatusOK, ranked)
	})

	// 标签列表
	mux.HandleFunc("GET /api/tags", func(w http.ResponseWriter, r *http.Request) {
		tags, err := st.ListTags()
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
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
			writeError(w, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, s)
	})

	// 图谱数据
	mux.HandleFunc("GET /api/graph", func(w http.ResponseWriter, r *http.Request) {
		g, err := st.Graph()
		if err != nil {
			writeError(w, http.StatusInternalServerError, err.Error())
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

	// 静态文件服务，根路径返回 index.html
	staticFS, err := fs.Sub(web.StaticFS(), ".")
	if err != nil {
		staticFS = web.StaticFS()
	}
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
			writeError(w, http.StatusNotFound, "not found")
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = w.Write(data)
	})

	return mux
}

// writeJSON 序列化并写出 JSON 响应。
func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

// writeError 以统一格式写出错误 JSON。
func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}

// parseID 从路径中解析 id，失败时写出 400 并返回 false。
func parseID(w http.ResponseWriter, r *http.Request) (int64, bool) {
	raw := r.PathValue("id")
	id, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || id <= 0 {
		writeError(w, http.StatusBadRequest, "invalid id")
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
