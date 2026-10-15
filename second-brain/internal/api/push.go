package api

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/second-brain/internal/config"
	"github.com/Wanfeng1028/muse/second-brain/internal/notify"
	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

// pushSettingsView 是对外暴露的推送设置视图（脱敏，绝不含密码/secret）。
type pushSettingsView struct {
	Enabled    bool   `json:"enabled"`
	Time       string `json:"time"`
	Timezone   string `json:"timezone"`
	MailTo     string `json:"mail_to"`
	WebhookURL string `json:"webhook_url"`
	SMTPHost   string `json:"smtp_host"`
	SMTPFrom   string `json:"smtp_from"`
}

// settingOr 读取设置项，不存在或出错时返回默认值。
func settingOr(st *store.Store, key, def string) string {
	v, ok := st.GetPushSetting(key)
	if !ok {
		return def
	}
	return v
}

// settingBoolOr 读取布尔设置项，"1" 为 true，"0" 为 false，其余走默认值。
func settingBoolOr(st *store.Store, key string, def bool) bool {
	v, ok := st.GetPushSetting(key)
	if !ok {
		return def
	}
	switch v {
	case "1":
		return true
	case "0":
		return false
	default:
		return def
	}
}

// buildPushSettingsView 从存储构建脱敏的设置视图，缺省值取自 cfg.Push。
func buildPushSettingsView(st *store.Store, cfg config.Config) pushSettingsView {
	return pushSettingsView{
		Enabled:    settingBoolOr(st, "enabled", cfg.Push.Enabled),
		Time:       settingOr(st, "time", cfg.Push.Time),
		Timezone:   settingOr(st, "timezone", cfg.Push.Timezone),
		MailTo:     settingOr(st, "mail_to", cfg.Push.MailTo),
		WebhookURL: settingOr(st, "webhook_url", cfg.Push.WebhookURL),
		SMTPHost:   settingOr(st, "smtp_host", cfg.Push.SMTPHost),
		SMTPFrom:   settingOr(st, "smtp_from", cfg.Push.SMTPFrom),
	}
}

// handleGetPushSettings 返回当前推送设置（脱敏）。
func handleGetPushSettings(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "方法不允许")
			return
		}
		writeJSON(w, http.StatusOK, buildPushSettingsView(st, cfg))
	}
}

// sensitiveKey 判断字段名是否包含敏感子串（大小写不敏感）。
func sensitiveKey(key string) bool {
	k := strings.ToLower(key)
	for _, s := range []string{"password", "secret", "passwd", "pass", "token"} {
		if strings.Contains(k, s) {
			return true
		}
	}
	return false
}

// validHHMM 校验 HH:MM 格式且范围 00:00–23:59。
func validHHMM(s string) bool {
	if len(s) != 5 || s[2] != ':' {
		return false
	}
	for i, c := range s {
		if i == 2 {
			continue
		}
		if c < '0' || c > '9' {
			return false
		}
	}
	hh := int(s[0]-'0')*10 + int(s[1]-'0')
	mm := int(s[3]-'0')*10 + int(s[4]-'0')
	return hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59
}

// handlePutPushSettings 更新推送设置，白名单字段、严格校验、脱敏返回。
func handlePutPushSettings(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPut {
			writeError(w, http.StatusMethodNotAllowed, "方法不允许")
			return
		}

		var body map[string]json.RawMessage
		dec := json.NewDecoder(r.Body)
		if err := dec.Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "请求体不是合法 JSON")
			return
		}

		// 敏感字段一律拒绝
		for k := range body {
			if sensitiveKey(k) {
				writeError(w, http.StatusBadRequest, "密钥请通过环境变量配置")
				return
			}
		}

		// 白名单之外的字段一律拒绝
		allowed := map[string]bool{
			"enabled":     true,
			"time":        true,
			"timezone":    true,
			"mail_to":     true,
			"webhook_url": true,
			"smtp_host":   true,
			"smtp_from":   true,
		}
		for k := range body {
			if !allowed[k] {
				writeError(w, http.StatusBadRequest, "未知字段: "+k)
				return
			}
		}

		updates := make(map[string]string)

		if raw, ok := body["enabled"]; ok {
			var b bool
			if err := json.Unmarshal(raw, &b); err != nil {
				writeError(w, http.StatusBadRequest, "enabled 必须为布尔值")
				return
			}
			if b {
				updates["enabled"] = "1"
			} else {
				updates["enabled"] = "0"
			}
		}

		if raw, ok := body["time"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "time 必须为字符串")
				return
			}
			if s != "" && !validHHMM(s) {
				writeError(w, http.StatusBadRequest, "time 必须为 HH:MM 格式且在 00:00–23:59 之间")
				return
			}
			updates["time"] = s
		}

		if raw, ok := body["timezone"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "timezone 必须为字符串")
				return
			}
			if s != "" {
				if _, err := time.LoadLocation(s); err != nil {
					writeError(w, http.StatusBadRequest, "timezone 非法")
					return
				}
			}
			updates["timezone"] = s
		}

		if raw, ok := body["mail_to"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "mail_to 必须为字符串")
				return
			}
			updates["mail_to"] = s
		}

		if raw, ok := body["webhook_url"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "webhook_url 必须为字符串")
				return
			}
			if s != "" && !strings.HasPrefix(s, "http://") && !strings.HasPrefix(s, "https://") {
				writeError(w, http.StatusBadRequest, "webhook_url 必须以 http:// 或 https:// 开头")
				return
			}
			updates["webhook_url"] = s
		}

		if raw, ok := body["smtp_host"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "smtp_host 必须为字符串")
				return
			}
			updates["smtp_host"] = s
		}

		if raw, ok := body["smtp_from"]; ok {
			var s string
			if err := json.Unmarshal(raw, &s); err != nil {
				writeError(w, http.StatusBadRequest, "smtp_from 必须为字符串")
				return
			}
			updates["smtp_from"] = s
		}

		for k, v := range updates {
			if err := st.SetPushSetting(k, v); err != nil {
				writeError(w, http.StatusInternalServerError, "写入设置失败")
				return
			}
		}

		writeJSON(w, http.StatusOK, buildPushSettingsView(st, cfg))
	}
}

// testDigestItems 返回用于通道测试的假数据（含 HTML 特殊字符，验证转义）。
func testDigestItems() []notify.DigestItem {
	now := time.Now().Format("2006-01-02")
	return []notify.DigestItem{
		{
			Title:       "红楼梦 第五回 笔记",
			Snippet:     "游幻境指迷十二钗，饮仙醪曲演红楼梦。",
			Tags:        []string{"阅读"},
			DueDate:     now,
			OverdueDays: 0,
		},
		{
			Title:       "Go 并发模式 <select> 踩坑",
			Snippet:     "select 的随机性与 default 分支 & 空 channel 的阻塞行为。",
			Tags:        []string{"技术", "Go"},
			DueDate:     now,
			OverdueDays: 2,
		},
		{
			Title:       "SM-2 算法推导 & 复习",
			Snippet:     "易度因子 EF 与间隔因子 <I(n)> 的递推推导。",
			Tags:        []string{"算法"},
			DueDate:     now,
			OverdueDays: 5,
		},
	}
}

// buildTestSender 依据 channel 与配置构建 sender，缺配置时报错。
func buildTestSender(channel string, cfg config.Config) (notify.Sender, error) {
	switch channel {
	case "smtp":
		if strings.TrimSpace(cfg.Push.SMTPHost) == "" {
			return nil, errors.New("SMTP 通道未配置")
		}
		return notify.NewSMTPSender(
			cfg.Push.SMTPHost,
			cfg.Push.SMTPPort,
			cfg.Push.SMTPUser,
			cfg.Push.SMTPPass,
			cfg.Push.SMTPFrom,
			cfg.Push.SMTPTLS,
		), nil
	case "webhook":
		if strings.TrimSpace(cfg.Push.WebhookURL) == "" {
			return nil, errors.New("Webhook 通道未配置")
		}
		return notify.NewWebhookSender(cfg.Push.WebhookURL, cfg.Push.WebhookSecret, 30*time.Second), nil
	default:
		return nil, errors.New("未知通道")
	}
}

// truncateDetail 截断错误信息至最多 200 字符。
func truncateDetail(s string) string {
	const maxLen = 200
	if len(s) <= maxLen {
		return s
	}
	return s[:maxLen]
}

// handlePushTest 使用假数据真实发送一次测试消息，不写 push_log。
func handlePushTest(st *store.Store, cfg config.Config) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			writeError(w, http.StatusMethodNotAllowed, "方法不允许")
			return
		}

		var body struct {
			Channel string `json:"channel"`
		}
		dec := json.NewDecoder(r.Body)
		if err := dec.Decode(&body); err != nil {
			writeError(w, http.StatusBadRequest, "请求体不是合法 JSON")
			return
		}

		if body.Channel != "smtp" && body.Channel != "webhook" {
			writeError(w, http.StatusBadRequest, "channel 必须为 smtp 或 webhook")
			return
		}

		sender, err := buildTestSender(body.Channel, cfg)
		if err != nil {
			writeError(w, http.StatusBadRequest, err.Error())
			return
		}

		to := cfg.Push.MailTo
		items := testDigestItems()
		stats := notify.DigestStats{DueCount: 3, OverdueDays: 2, Streak: 7}
		msg := notify.BuildDigestMessage(time.Now(), items, stats, to)

		ctx, cancel := context.WithTimeout(r.Context(), 30*time.Second)
		defer cancel()

		if sendErr := sender.Send(ctx, msg); sendErr != nil {
			writeJSON(w, http.StatusOK, map[string]any{
				"channel": body.Channel,
				"ok":      false,
				"detail":  truncateDetail(sendErr.Error()),
			})
			return
		}

		writeJSON(w, http.StatusOK, map[string]any{
			"channel": body.Channel,
			"ok":      true,
			"detail":  "",
		})
	}
}

// handlePushHistory 返回最近的推送历史记录。
func handlePushHistory(st *store.Store) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			writeError(w, http.StatusMethodNotAllowed, "方法不允许")
			return
		}

		limit := parseIntDefault(r.URL.Query().Get("limit"), 50)
		records, err := st.ListPushLog(limit)
		if err != nil {
			writeError(w, http.StatusInternalServerError, "读取推送历史失败")
			return
		}
		if records == nil {
			records = []store.PushRecord{}
		}
		writeJSON(w, http.StatusOK, records)
	}
}

// RegisterPushRoutes 注册推送相关路由。
func RegisterPushRoutes(mux *http.ServeMux, st *store.Store, cfg config.Config) {
	mux.HandleFunc("GET /api/push/settings", handleGetPushSettings(st, cfg))
	mux.HandleFunc("PUT /api/push/settings", handlePutPushSettings(st, cfg))
	mux.HandleFunc("POST /api/push/test", handlePushTest(st, cfg))
	mux.HandleFunc("GET /api/push/history", handlePushHistory(st))
}
