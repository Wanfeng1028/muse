package middleware

import "testing"

func TestR2_ExtractBearer(t *testing.T) {
	tests := []struct {
		name string
		in   string
		want string
	}{
		{name: "empty", in: "", want: ""},
		{name: "normal bearer", in: "Bearer abc123", want: "abc123"},
		{name: "lowercase bearer", in: "bearer abc123", want: "abc123"},
		{name: "uppercase bearer", in: "BEARER abc123", want: "abc123"},
		{name: "surrounding spaces", in: "  Bearer   abc123  ", want: "abc123"},
		{name: "non bearer scheme", in: "Token abc123", want: ""},
		{name: "too short", in: "Bearer", want: ""},
		{name: "no token", in: "Bearer ", want: ""},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got := extractBearer(tc.in)
			if got != tc.want {
				t.Fatalf("extractBearer(%q) = %q, want %q", tc.in, got, tc.want)
			}
		})
	}
}
