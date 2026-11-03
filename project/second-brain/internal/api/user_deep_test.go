package api

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Wanfeng1028/muse/second-brain/internal/store"
)

func newUserRequest(target string, headers map[string]string) *http.Request {
	if target == "" {
		target = "/"
	}
	req := httptest.NewRequest(http.MethodGet, target, nil)
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	return req
}

func TestCurrentUserPriority(t *testing.T) {
	cases := []struct {
		name       string
		target     string
		headers    map[string]string
		want       string
		wantHeader bool
	}{
		{
			name:       "header wins over query",
			target:     "/api/notes?user=fromquery",
			headers:    map[string]string{"X-User": "fromheader"},
			want:       "fromheader",
			wantHeader: true,
		},
		{
			name:       "query used when header empty",
			target:     "/api/notes?user=fromquery",
			headers:    map[string]string{},
			want:       "fromquery",
			wantHeader: false,
		},
		{
			name:       "default when nothing given",
			target:     "/api/notes",
			headers:    map[string]string{},
			want:       store.DefaultUser,
			wantHeader: false,
		},
		{
			name:       "header whitespace only normalizes to default",
			target:     "/api/notes?user=fromquery",
			headers:    map[string]string{"X-User": "   "},
			want:       store.DefaultUser, // 产品先判空再归一化，空白 header 直接归一化为默认用户
			wantHeader: false,
		},
		{
			name:       "query empty value falls through to default",
			target:     "/api/notes?user=",
			headers:    map[string]string{},
			want:       store.DefaultUser,
			wantHeader: false,
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			req := newUserRequest(c.target, c.headers)
			got := CurrentUser(req)
			if got != c.want {
				t.Fatalf("CurrentUser() = %q, want %q", got, c.want)
			}
			if c.wantHeader {
				if req.Header.Get("X-User") != "fromheader" {
					t.Fatalf("header was not preserved, got %q", req.Header.Get("X-User"))
				}
			} else {
				if req.Header.Get("X-User") == "" {
					if got == "" {
						t.Fatalf("empty user should never be returned")
					}
				}
			}
		})
	}
}

func TestCurrentUserNormalization(t *testing.T) {
	cases := []struct {
		name   string
		target string
		header string
		want   string
	}{
		{
			name:   "uppercase header normalized to lower",
			header: "ALICE",
			want:   "alice",
		},
		{
			name:   "leading and trailing spaces trimmed",
			header: "  bob  ",
			want:   "bob",
		},
		{
			name:   "inner spaces preserved (only trim+lower)",
			header: "carol   dave",
			want:   "carol   dave",
		},
		{
			name:   "underscore preserved (only trim+lower)",
			header: "erin_frank",
			want:   "erin_frank",
		},
		{
			name:   "query uppercase normalized",
			target: "/api/notes?user=GRACE",
			want:   "grace",
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			headers := map[string]string{}
			if c.header != "" {
				headers["X-User"] = c.header
			}
			req := newUserRequest(c.target, headers)
			got := CurrentUser(req)
			if got != c.want {
				t.Fatalf("CurrentUser() = %q, want %q", got, c.want)
			}
			if got != store.NormalizeUser(got) {
				t.Fatalf("CurrentUser() returned unnormalized value %q", got)
			}
		})
	}
}

func TestCurrentUserIsolatesUsers(t *testing.T) {
	reqA := newUserRequest("/api/notes", map[string]string{"X-User": "alice"})
	reqB := newUserRequest("/api/notes", map[string]string{"X-User": "bob"})
	userA := CurrentUser(reqA)
	userB := CurrentUser(reqB)
	if userA == userB {
		t.Fatalf("different headers produced same user %q", userA)
	}
	if userA != "alice" || userB != "bob" {
		t.Fatalf("unexpected users: %q, %q", userA, userB)
	}
}

func TestCurrentUserDefaultUserConstant(t *testing.T) {
	req := newUserRequest("/api/notes", map[string]string{})
	got := CurrentUser(req)
	if got != store.DefaultUser {
		t.Fatalf("CurrentUser() = %q, want DefaultUser %q", got, store.DefaultUser)
	}
	if store.DefaultUser == "" {
		t.Fatalf("DefaultUser must not be empty")
	}
}

func TestCurrentUserDoesNotMutateRequest(t *testing.T) {
	req := newUserRequest("/api/notes?user=ZOE", map[string]string{"X-User": "YAN"})
	beforeURL := req.URL.String()
	beforeHeader := req.Header.Get("X-User")
	got := CurrentUser(req)
	if got != "yan" {
		t.Fatalf("CurrentUser() = %q, want %q", got, "yan")
	}
	if req.URL.String() != beforeURL {
		t.Fatalf("request URL mutated: %q -> %q", beforeURL, req.URL.String())
	}
	if req.Header.Get("X-User") != beforeHeader {
		t.Fatalf("request header mutated: %q -> %q", beforeHeader, req.Header.Get("X-User"))
	}
}

func TestCurrentUserRepeatedCallsStable(t *testing.T) {
	req := newUserRequest("/api/notes?user=HANA", map[string]string{})
	first := CurrentUser(req)
	second := CurrentUser(req)
	if first != second {
		t.Fatalf("repeated calls differ: %q vs %q", first, second)
	}
	if first != "hana" {
		t.Fatalf("CurrentUser() = %q, want %q", first, "hana")
	}
}

func TestCurrentUserEmptyHeaderFallsToQuery(t *testing.T) {
	req := newUserRequest("/api/notes?user=ivan", map[string]string{"X-User": ""})
	got := CurrentUser(req)
	if got != "ivan" {
		t.Fatalf("CurrentUser() = %q, want %q", got, "ivan")
	}
	if got == store.DefaultUser {
		t.Fatalf("should not fall back to default when query present")
	}
}

func TestCurrentUserUnknownButValidIdentity(t *testing.T) {
	req := newUserRequest("/api/notes", map[string]string{"X-User": "never-seen-user-42"})
	got := CurrentUser(req)
	if got != "never-seen-user-42" {
		t.Fatalf("CurrentUser() = %q, want %q", got, "never-seen-user-42")
	}
	if got == store.DefaultUser {
		t.Fatalf("explicit identity should not become default")
	}
}

func TestCurrentUserMultiUserSeparationAcrossRequests(t *testing.T) {
	users := []string{"u1", "u2", "u3", "u1"}
	seen := map[string]int{}
	for _, u := range users {
		req := newUserRequest("/api/notes", map[string]string{"X-User": u})
		got := CurrentUser(req)
		if got != u {
			t.Fatalf("CurrentUser() = %q, want %q", got, u)
		}
		seen[got]++
	}
	if seen["u1"] != 2 {
		t.Fatalf("u1 should be seen twice, got %d", seen["u1"])
	}
	if len(seen) != 3 {
		t.Fatalf("expected 3 distinct users, got %d", len(seen))
	}
}
