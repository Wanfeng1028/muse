package api

import (
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// registerReviewHealthRoutes 注册记忆健康诊断路由。
func registerReviewHealthRoutes(mux *http.ServeMux, st *store.Store) {
	// 记忆健康诊断
	mux.HandleFunc("GET /api/review/health", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}
		health, err := st.ReviewHealth(time.Now(), CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}
		writeJSON(w, http.StatusOK, health)
	})
}
