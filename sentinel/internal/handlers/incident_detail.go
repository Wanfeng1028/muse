// internal/handlers/incident_detail.go
// 路由注册（放在 handleListIncidents 注册行之后）：
//
//	mux.HandleFunc("GET /api/incidents/{id}", s.handleGetIncident)
package handlers

import (
	"database/sql"
	"net/http"
)

func (s *Server) handleGetIncident(w http.ResponseWriter, r *http.Request) {
	id, ok := parseID(r)
	if !ok {
		writeErr(w, http.StatusBadRequest, "ID 非法")
		return
	}

	inc, err := s.store.GetIncidentByID(id)
	if err != nil {
		if err == sql.ErrNoRows {
			writeErr(w, http.StatusNotFound, "事件不存在")
			return
		}
		logErr(r, "handleGetIncident", err)
		writeErr(w, http.StatusInternalServerError, "读取事件详情失败")
		return
	}

	rc, err := s.store.FirstRecoveryCheck(inc)
	if err != nil {
		logErr(r, "handleGetIncident", err)
		writeErr(w, http.StatusInternalServerError, "读取事件详情失败")
		return
	}

	deliveries, err := s.store.ListIncidentDeliveries(inc)
	if err != nil {
		logErr(r, "handleGetIncident", err)
		writeErr(w, http.StatusInternalServerError, "读取事件详情失败")
		return
	}

	var endedAt interface{}
	if inc.EndedAt.Valid {
		endedAt = inc.EndedAt.String
	}
	var downtime interface{}
	if inc.DowntimeSec.Valid {
		downtime = inc.DowntimeSec.Int64
	}
	incident := map[string]interface{}{
		"id":           inc.ID,
		"monitor_id":   inc.MonitorID,
		"monitor_name": inc.MonitorName,
		"started_at":   inc.StartedAt,
		"ended_at":     endedAt,
		"downtime_sec": downtime,
		"start_error":  inc.StartError,
	}

	var recoveryCheck interface{}
	if rc != nil {
		var statusCode interface{}
		if rc.StatusCode.Valid {
			statusCode = rc.StatusCode.Int64
		}
		recoveryCheck = map[string]interface{}{
			"checked_at":  rc.CheckedAt,
			"ok":          rc.Ok,
			"status_code": statusCode,
			"latency_ms":  rc.LatencyMs,
			"error":       rc.Error,
		}
	}

	deliveryItems := make([]map[string]interface{}, 0, len(deliveries))
	for _, d := range deliveries {
		deliveryItems = append(deliveryItems, map[string]interface{}{
			"id":           d.ID,
			"url":          d.URL,
			"event":        d.Event,
			"status":       d.Status,
			"attempt":      d.Attempt,
			"max_attempts": d.MaxAttempts,
			"last_error":   d.LastError,
			"created_at":   d.CreatedAt,
		})
	}

	writeJSON(w, http.StatusOK, map[string]interface{}{
		"incident":       incident,
		"recovery_check": recoveryCheck,
		"deliveries":     deliveryItems,
	})
}
