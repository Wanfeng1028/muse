package api

import (
	"encoding/json"
	"net/http"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// maskKey 对密钥材料做脱敏处理，仅保留前 4 个字符。
// 空字符串返回空串；长度不超过 4 个 rune 时返回 "***"；否则返回前 4 个 rune + "***"。
func maskKey(s string) string {
	if s == "" {
		return ""
	}
	runes := []rune(s)
	if len(runes) <= 4 {
		return "***"
	}
	return string(runes[:4]) + "***"
}

// subscriptionView 是订阅的对外展示结构，密钥材料一律脱敏。
type subscriptionView struct {
	ID           int64  `json:"id"`
	Endpoint     string `json:"endpoint"`
	CreatedAt    string `json:"createdAt"`
	P256dhMasked string `json:"p256dhMasked"`
	AuthMasked   string `json:"authMasked"`
}

// toSubscriptionView 将存储层订阅转换为脱敏视图。
func toSubscriptionView(sub store.PushSubscription) subscriptionView {
	return subscriptionView{
		ID:           sub.ID,
		Endpoint:     sub.Endpoint,
		CreatedAt:    sub.CreatedAt,
		P256dhMasked: maskKey(sub.P256DH),
		AuthMasked:   maskKey(sub.Auth),
	}
}

// handlePostPushSubscription 处理新增或更新订阅。
func handlePostPushSubscription(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, r, http.StatusMethodNotAllowed, "方法不被允许")
			return
		}
		if !cfg.Push.VAPIDConfigured() {
			writeError(w, r, http.StatusServiceUnavailable, "浏览器推送未启用：服务器未配置 VAPID 密钥")
			return
		}
		var body struct {
			Endpoint string `json:"endpoint"`
			P256dh   string `json:"p256dh"`
			Auth     string `json:"auth"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			writeError(w, r, http.StatusBadRequest, "请求体不是合法 JSON")
			return
		}
		sub, err := st.UpsertSubscription(CurrentUser(r), body.Endpoint, body.P256dh, body.Auth)
		if err != nil {
			// UpsertSubscription 的参数校验失败与入库失败都经此返回，错误信息为中文可直接透传。
			writeError(w, r, http.StatusBadRequest, err.Error())
			return
		}
		writeJSON(w, http.StatusCreated, toSubscriptionView(sub))
	}
}

// handleDeletePushSubscription 处理删除订阅。
func handleDeletePushSubscription(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodDelete {
			writeError(w, r, http.StatusMethodNotAllowed, "方法不被允许")
			return
		}
		if !cfg.Push.VAPIDConfigured() {
			writeError(w, r, http.StatusServiceUnavailable, "浏览器推送未启用：服务器未配置 VAPID 密钥")
			return
		}
		endpoint := ""
		var body struct {
			Endpoint string `json:"endpoint"`
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err == nil {
			endpoint = body.Endpoint
		}
		if endpoint == "" {
			endpoint = r.URL.Query().Get("endpoint")
		}
		if endpoint == "" {
			writeError(w, r, http.StatusBadRequest, "缺少 endpoint 参数")
			return
		}
		deleted, err := st.DeleteSubscriptionForUser(CurrentUser(r), endpoint)
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, "删除订阅失败")
			return
		}
		writeJSON(w, http.StatusOK, map[string]bool{"deleted": deleted})
	}
}

// handleListPushSubscriptions 列出当前用户的全部订阅。
func handleListPushSubscriptions(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "方法不被允许")
			return
		}
		if !cfg.Push.VAPIDConfigured() {
			writeError(w, r, http.StatusServiceUnavailable, "浏览器推送未启用：服务器未配置 VAPID 密钥")
			return
		}
		subs, err := st.ListSubscriptionsForUser(CurrentUser(r))
		if err != nil {
			writeError(w, r, http.StatusInternalServerError, "读取订阅失败")
			return
		}
		views := make([]subscriptionView, 0, len(subs))
		for _, sub := range subs {
			views = append(views, toSubscriptionView(sub))
		}
		writeJSON(w, http.StatusOK, views)
	}
}

// handleGetVAPIDPublicKey 返回 VAPID 公钥，供前端订阅使用。
func handleGetVAPIDPublicKey(cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, r, http.StatusMethodNotAllowed, "方法不被允许")
			return
		}
		if !cfg.Push.VAPIDConfigured() {
			writeError(w, r, http.StatusServiceUnavailable, "浏览器推送未启用：服务器未配置 VAPID 密钥")
			return
		}
		writeJSON(w, http.StatusOK, map[string]string{"publicKey": cfg.Push.VAPIDPublicKey})
	}
}

// RegisterPushSubscriptionRoutes 注册订阅管理相关路由。
func RegisterPushSubscriptionRoutes(mux *http.ServeMux, st *store.Store, cfg config.Config) {
	mux.HandleFunc("POST /api/push/subscriptions", handlePostPushSubscription(st, cfg))
	mux.HandleFunc("DELETE /api/push/subscriptions", handleDeletePushSubscription(st, cfg))
	mux.HandleFunc("GET /api/push/subscriptions", handleListPushSubscriptions(st, cfg))
	mux.HandleFunc("GET /api/push/vapid-public-key", handleGetVAPIDPublicKey(cfg))
}
