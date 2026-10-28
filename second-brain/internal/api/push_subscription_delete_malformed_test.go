package api

import (
	"encoding/json"
	"net/http"
	"testing"
)

func TestPushSubscriptionDeleteMalformed(t *testing.T) {
	t.Run("malformed-syntax", func(t *testing.T) {
		st := newDeepTestStore(t)
		cfg := deepTestConfig(true)
		user := "u1"
		endpoint := "https://push.example.com/del1/晚风-1"
		rec := deepPostJSON(t, handlePostPushSubscription(st, cfg), user, `{"endpoint":"`+endpoint+`","p256dh":"BEl6abcdefghij","auth":"auth5678"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201, got %d", rec.Code)
		}
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, endpoint, user, `{"endpoint":`)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", rec.Code)
		}
		var errBody map[string]string
		if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
			t.Fatalf("failed to unmarshal error body: %v", err)
		}
		if errBody["error"] != "请求体不是合法 JSON" {
			t.Fatalf("expected error message, got %q", errBody["error"])
		}
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, endpoint, user, `{"endpoint":"`+endpoint+`"}`)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		var okBody map[string]bool
		if err := json.Unmarshal(rec.Body.Bytes(), &okBody); err != nil {
			t.Fatalf("failed to unmarshal success body: %v", err)
		}
		if !okBody["deleted"] {
			t.Fatalf("expected deleted true, got %v", okBody["deleted"])
		}
	})

	t.Run("malformed-type", func(t *testing.T) {
		st := newDeepTestStore(t)
		cfg := deepTestConfig(true)
		user := "u2"
		endpoint := "https://push.example.com/del2/晚风-2"
		rec := deepPostJSON(t, handlePostPushSubscription(st, cfg), user, `{"endpoint":"`+endpoint+`","p256dh":"BEl6abcdefghij","auth":"auth5678"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201, got %d", rec.Code)
		}
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, endpoint, user, `{"endpoint":123}`)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", rec.Code)
		}
		var errBody map[string]string
		if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
			t.Fatalf("failed to unmarshal error body: %v", err)
		}
		if errBody["error"] != "请求体不是合法 JSON" {
			t.Fatalf("expected error message, got %q", errBody["error"])
		}
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, endpoint, user, `{"endpoint":"`+endpoint+`"}`)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		var okBody map[string]bool
		if err := json.Unmarshal(rec.Body.Bytes(), &okBody); err != nil {
			t.Fatalf("failed to unmarshal success body: %v", err)
		}
		if !okBody["deleted"] {
			t.Fatalf("expected deleted true, got %v", okBody["deleted"])
		}
	})

	t.Run("malformed-with-query", func(t *testing.T) {
		st := newDeepTestStore(t)
		cfg := deepTestConfig(true)
		user := "u3"
		endpoint := "https://push.example.com/del3/晚风-3"
		rec := deepPostJSON(t, handlePostPushSubscription(st, cfg), user, `{"endpoint":"`+endpoint+`","p256dh":"BEl6abcdefghij","auth":"auth5678"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201, got %d", rec.Code)
		}
		target := "/api/push/subscriptions?endpoint=" + "https%3A%2F%2Fpush.example.com%2Fdel3%2F%E6%99%9A%E9%A3%8E-3"
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, target, user, `{"endpoint":`)
		if rec.Code != http.StatusBadRequest {
			t.Fatalf("expected 400, got %d", rec.Code)
		}
		var errBody map[string]string
		if err := json.Unmarshal(rec.Body.Bytes(), &errBody); err != nil {
			t.Fatalf("failed to unmarshal error body: %v", err)
		}
		if errBody["error"] != "请求体不是合法 JSON" {
			t.Fatalf("expected error message, got %q", errBody["error"])
		}
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, endpoint, user, `{"endpoint":"`+endpoint+`"}`)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		var okBody map[string]bool
		if err := json.Unmarshal(rec.Body.Bytes(), &okBody); err != nil {
			t.Fatalf("failed to unmarshal success body: %v", err)
		}
		if !okBody["deleted"] {
			t.Fatalf("expected deleted true, got %v", okBody["deleted"])
		}
	})

	t.Run("empty-with-query", func(t *testing.T) {
		st := newDeepTestStore(t)
		cfg := deepTestConfig(true)
		user := "u4"
		endpoint := "https://push.example.com/del4/晚风-4"
		rec := deepPostJSON(t, handlePostPushSubscription(st, cfg), user, `{"endpoint":"`+endpoint+`","p256dh":"BEl6abcdefghij","auth":"auth5678"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201, got %d", rec.Code)
		}
		target := "/api/push/subscriptions?endpoint=" + "https%3A%2F%2Fpush.example.com%2Fdel4%2F%E6%99%9A%E9%A3%8E-4"
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, target, user, "")
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		var okBody map[string]bool
		if err := json.Unmarshal(rec.Body.Bytes(), &okBody); err != nil {
			t.Fatalf("failed to unmarshal success body: %v", err)
		}
		if !okBody["deleted"] {
			t.Fatalf("expected deleted true, got %v", okBody["deleted"])
		}
	})

	t.Run("empty-object-with-query", func(t *testing.T) {
		st := newDeepTestStore(t)
		cfg := deepTestConfig(true)
		user := "u5"
		endpoint := "https://push.example.com/del5/晚风-5"
		rec := deepPostJSON(t, handlePostPushSubscription(st, cfg), user, `{"endpoint":"`+endpoint+`","p256dh":"BEl6abcdefghij","auth":"auth5678"}`)
		if rec.Code != http.StatusCreated {
			t.Fatalf("expected 201, got %d", rec.Code)
		}
		target := "/api/push/subscriptions?endpoint=" + "https%3A%2F%2Fpush.example.com%2Fdel5%2F%E6%99%9A%E9%A3%8E-5"
		rec = deepDo(t, handleDeletePushSubscription(st, cfg), http.MethodDelete, target, user, `{}`)
		if rec.Code != http.StatusOK {
			t.Fatalf("expected 200, got %d", rec.Code)
		}
		var okBody map[string]bool
		if err := json.Unmarshal(rec.Body.Bytes(), &okBody); err != nil {
			t.Fatalf("failed to unmarshal success body: %v", err)
		}
		if !okBody["deleted"] {
			t.Fatalf("expected deleted true, got %v", okBody["deleted"])
		}
	})
}
