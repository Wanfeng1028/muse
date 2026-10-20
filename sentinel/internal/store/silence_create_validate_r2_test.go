package store

import (
	"strings"
	"testing"
)

func TestR2_CreateSilenceValid(t *testing.T) {
	st := newTestStore(t)

	id, err := st.CreateSilence(Silence{
		MonitorID: 1,
		NameMatch: "api",
		StartsAt:  "2026-01-01T00:00:00Z",
		EndsAt:    "2026-01-02T00:00:00Z",
		Reason:    "维护窗口",
	})
	if err != nil {
		t.Fatalf("CreateSilence returned error: %v", err)
	}
	if id <= 0 {
		t.Fatalf("CreateSilence returned invalid id: %d", id)
	}

	got, err := st.GetSilence(id)
	if err != nil {
		t.Fatalf("GetSilence returned error: %v", err)
	}
	if got.ID != id {
		t.Fatalf("GetSilence id = %d, want %d", got.ID, id)
	}
	if got.Reason != "维护窗口" {
		t.Fatalf("GetSilence reason = %q, want %q", got.Reason, "维护窗口")
	}
	if got.CreatedAt == "" {
		t.Fatal("GetSilence created_at is empty, want auto-filled value")
	}
}

func TestR2_CreateSilenceInvalid(t *testing.T) {
	cases := []struct {
		name   string
		silence Silence
	}{
		{
			name: "starts_at invalid",
			silence: Silence{
				StartsAt: "not-a-time",
				EndsAt:   "2026-01-02T00:00:00Z",
				Reason:   "维护窗口",
			},
		},
		{
			name: "ends_at invalid",
			silence: Silence{
				StartsAt: "2026-01-01T00:00:00Z",
				EndsAt:   "not-a-time",
				Reason:   "维护窗口",
			},
		},
		{
			name: "starts_at equals ends_at",
			silence: Silence{
				StartsAt: "2026-01-01T00:00:00Z",
				EndsAt:   "2026-01-01T00:00:00Z",
				Reason:   "维护窗口",
			},
		},
		{
			name: "starts_at after ends_at",
			silence: Silence{
				StartsAt: "2026-01-02T00:00:00Z",
				EndsAt:   "2026-01-01T00:00:00Z",
				Reason:   "维护窗口",
			},
		},
		{
			name: "reason empty",
			silence: Silence{
				StartsAt: "2026-01-01T00:00:00Z",
				EndsAt:   "2026-01-02T00:00:00Z",
				Reason:   "",
			},
		},
		{
			name: "reason only spaces",
			silence: Silence{
				StartsAt: "2026-01-01T00:00:00Z",
				EndsAt:   "2026-01-02T00:00:00Z",
				Reason:   "   ",
			},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			st := newTestStore(t)

			id, err := st.CreateSilence(tc.silence)
			if err == nil {
				t.Fatalf("CreateSilence succeeded, want error")
			}
			if id != 0 {
				t.Fatalf("CreateSilence id = %d, want 0 on error", id)
			}
		})
	}
}

func TestR2_CreateSilenceErrorText(t *testing.T) {
	st := newTestStore(t)

	_, err := st.CreateSilence(Silence{
		StartsAt: "2026-01-02T00:00:00Z",
		EndsAt:   "2026-01-01T00:00:00Z",
		Reason:   "维护窗口",
	})
	if err == nil {
		t.Fatal("CreateSilence succeeded, want error")
	}
	if !strings.Contains(err.Error(), "starts_at 必须早于 ends_at") {
		t.Fatalf("CreateSilence error = %q, want contains %q", err.Error(), "starts_at 必须早于 ends_at")
	}

	_, err = st.CreateSilence(Silence{
		StartsAt: "2026-01-01T00:00:00Z",
		EndsAt:   "2026-01-02T00:00:00Z",
		Reason:   "",
	})
	if err == nil {
		t.Fatal("CreateSilence succeeded, want error")
	}
	if !strings.Contains(err.Error(), "reason 不能为空") {
		t.Fatalf("CreateSilence error = %q, want contains %q", err.Error(), "reason 不能为空")
	}

	_, err = st.CreateSilence(Silence{
		StartsAt: "not-a-time",
		EndsAt:   "2026-01-02T00:00:00Z",
		Reason:   "维护窗口",
	})
	if err == nil {
		t.Fatal("CreateSilence succeeded, want error")
	}
	if !strings.Contains(err.Error(), "RFC3339") {
		t.Fatalf("CreateSilence error = %q, want contains %q", err.Error(), "RFC3339")
	}
}
