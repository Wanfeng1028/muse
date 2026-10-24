package api

import (
	"net/http"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// 注册打卡连续路由
func registerReviewStreakRoutes(mux *http.ServeMux, st *store.Store) {
	mux.HandleFunc("GET /api/review/streak", func(w http.ResponseWriter, r *http.Request) {
		// 仅允许 GET
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
			return
		}

		// 获取打卡连续数据
		streak, err := st.ReviewStreak(time.Now(), CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, err.Error())
			return
		}

		// 返回成功结果
		writeJSON(w, http.StatusOK, streak)
	})

	// POST 字面量路由优先于 POST /api/review/{id} 通配，保证非 GET 方法返回 405。
	mux.HandleFunc("POST /api/review/streak", func(w http.ResponseWriter, r *http.Request) {
		writeError(w, r, http.StatusMethodNotAllowed, "method not allowed")
	})
}
