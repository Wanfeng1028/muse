package handler

import (
	"net/http"
)

// handleDocs 输出内嵌的 API 文档页（公开，无需鉴权）。
func handleDocs(w http.ResponseWriter, r *http.Request) {
	data, err := webFS.ReadFile("web/docs.html")
	if err != nil {
		writeError(w, http.StatusInternalServerError, "docs not available")
		return
	}
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write(data)
}
