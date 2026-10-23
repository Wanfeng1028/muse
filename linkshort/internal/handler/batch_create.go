package handler

import (
	"encoding/json"
	"net/http"
	"strings"
	"time"

	"github.com/Wanfeng1028/muse/linkshort/internal/config"
	"github.com/Wanfeng1028/muse/linkshort/internal/store"
	"github.com/Wanfeng1028/muse/linkshort/internal/util"
)

type batchItemResp struct {
	Index    int    `json:"index"`
	OK       bool   `json:"ok"`
	ID       int64  `json:"id,omitempty"`
	Slug     string `json:"slug,omitempty"`
	ShortURL string `json:"short_url,omitempty"`
	Error    string `json:"error,omitempty"`
}

type batchResp struct {
	Items   []batchItemResp `json:"items"`
	OKCount int             `json:"ok_count"`
	Total   int             `json:"total"`
}

func handleBatchCreateLink(w http.ResponseWriter, r *http.Request, st *store.Store, cfg *config.Config) {
	var reqs []createLinkReq
	if err := json.NewDecoder(r.Body).Decode(&reqs); err != nil {
		writeError(w, http.StatusBadRequest, "请求格式不正确")
		return
	}

	if len(reqs) == 0 {
		writeError(w, http.StatusBadRequest, "批量不能为空")
		return
	}
	if len(reqs) > 100 {
		writeError(w, http.StatusBadRequest, "批量最多 100 条")
		return
	}

	base := shortBaseURL(r, cfg)
	items := make([]batchItemResp, 0, len(reqs))
	okCount := 0
	seenSlugs := make(map[string]bool)

	for i, req := range reqs {
		item := batchItemResp{Index: i}

		if req.Password != "" {
			item.Error = "批量暂不支持密码"
			items = append(items, item)
			continue
		}

		if req.URL == "" {
			item.Error = "url 不能为空"
			items = append(items, item)
			continue
		}
		if len(req.URL) > 2048 {
			item.Error = "url 长度不能超过 2048"
			items = append(items, item)
			continue
		}
		if !strings.HasPrefix(req.URL, "http://") && !strings.HasPrefix(req.URL, "https://") {
			item.Error = "url 必须以 http:// 或 https:// 开头"
			items = append(items, item)
			continue
		}

		if req.Slug != "" {
			if !util.IsValidSlug(req.Slug) {
				item.Error = "slug 格式不正确"
				items = append(items, item)
				continue
			}
			if seenSlugs[req.Slug] {
				item.Error = "批次内 slug 重复"
				items = append(items, item)
				continue
			}
			seenSlugs[req.Slug] = true
		}

		if req.MaxVisits != nil {
			if *req.MaxVisits < 1 || *req.MaxVisits > 1000000 {
				item.Error = "max_visits 必须在 1~1000000 之间"
				items = append(items, item)
				continue
			}
		}

		if req.Burn && req.MaxVisits != nil && *req.MaxVisits != 1 {
			item.Error = "burn 时 max_visits 必须为 nil 或 1"
			items = append(items, item)
			continue
		}

		if req.Purge != nil && *req.Purge && !req.Burn {
			item.Error = "purge 为 true 时 burn 必须为 true"
			items = append(items, item)
			continue
		}

		var expiresAt *time.Time
		if req.ExpiresAt != nil {
			t, err := time.Parse(time.RFC3339, *req.ExpiresAt)
			if err != nil {
				item.Error = "expires_at 格式不正确"
				items = append(items, item)
				continue
			}
			expiresAt = &t
		}

		purge := false
		if req.Purge != nil {
			purge = *req.Purge
		}

		id, err := st.CreateLinkEx(req.Slug, req.URL, req.Title, expiresAt, req.MaxVisits, req.Burn, purge)
		if err != nil {
			item.Error = err.Error()
			items = append(items, item)
			continue
		}

		created, gerr := st.GetLink(id)
		if gerr != nil {
			item.Error = gerr.Error()
			items = append(items, item)
			continue
		}
		item.OK = true
		item.ID = id
		item.Slug = created.Slug
		item.ShortURL = base + "/" + created.Slug
		okCount++
		items = append(items, item)
	}

	resp := batchResp{
		Items:   items,
		OKCount: okCount,
		Total:   len(reqs),
	}

	status := http.StatusMultiStatus
	if okCount == len(reqs) {
		status = http.StatusCreated
	} else if okCount == 0 {
		status = http.StatusBadRequest
	}

	writeJSON(w, status, resp)
}
