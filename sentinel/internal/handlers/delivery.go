package handlers

import (
	"database/sql"
	"errors"
	"net/http"
	"strconv"
	"strings"

	"sentinel/internal/store"
)

func deliveryJSON(s *Server, d store.Delivery) map[string]interface{} {
	monitorName := "#" + strconv.FormatInt(d.MonitorID, 10)
	if m, err := s.store.GetMonitor(d.MonitorID); err == nil {
		if m.Name != "" {
			monitorName = m.Name
		}
	}
	var nextRetry interface{}
	if d.NextRetryAt.Valid {
		nextRetry = d.NextRetryAt.String
	} else {
		nextRetry = nil
	}
	return map[string]interface{}{
		"id":            d.ID,
		"monitor_id":    d.MonitorID,
		"monitor_name":  monitorName,
		"url":           d.URL,
		"event":         d.Event,
		"status":        d.Status,
		"attempt":       d.Attempt,
		"max_attempts":  d.MaxAttempts,
		"next_retry_at": nextRetry,
		"last_error":    d.LastError,
		"created_at":    d.CreatedAt,
		"updated_at":    d.UpdatedAt,
	}
}

func (s *Server) handleListDeliveries(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()

	status := strings.TrimSpace(q.Get("status"))
	if status != "" {
		switch status {
		case "pending", "retrying", "done", "failed", "dead":
		default:
			writeErr(w, http.StatusBadRequest, "status 参数非法，只支持 pending/retrying/done/failed/dead")
			return
		}
	}

	var monitorID int64
	if raw := strings.TrimSpace(q.Get("monitor_id")); raw != "" {
		id, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || id < 0 {
			writeErr(w, http.StatusBadRequest, "monitor_id 参数非法")
			return
		}
		monitorID = id
	}

	limit := 100
	if raw := strings.TrimSpace(q.Get("limit")); raw != "" {
		n, err := strconv.Atoi(raw)
		if err != nil {
			writeErr(w, http.StatusBadRequest, "limit 参数非法")
			return
		}
		limit = n
	}
	if limit < 1 {
		limit = 1
	}
	if limit > 1000 {
		limit = 1000
	}

	list, err := s.store.ListDeliveries(status, monitorID, limit)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "查询投递记录失败")
		return
	}

	items := make([]map[string]interface{}, 0, len(list))
	for _, d := range list {
		items = append(items, deliveryJSON(s, d))
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"items": items,
		"total": len(items),
	})
}

func (s *Server) handleRetryDelivery(w http.ResponseWriter, r *http.Request) {
	id, ok := parsePathID(r, "id")
	if !ok {
		writeErr(w, http.StatusBadRequest, "投递记录 ID 非法")
		return
	}

	if err := s.store.RetryDelivery(id); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			writeErr(w, http.StatusNotFound, "投递记录不存在")
			return
		}
		writeErr(w, http.StatusBadRequest, err.Error())
		return
	}

	d, err := s.store.GetDelivery(id)
	if err != nil {
		writeErr(w, http.StatusInternalServerError, "读取投递记录失败")
		return
	}
	writeJSON(w, http.StatusOK, deliveryJSON(s, d))
}
