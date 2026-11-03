package config

import (
	"os"
	"testing"
	"time"
)

func TestGetenvDurationStrict(t *testing.T) {
	tests := []struct {
		name   string
		def    time.Duration
		val    string
		unset  bool
		want   time.Duration
		wantOk bool
	}{
		{"unset", 5 * time.Minute, "", true, 5 * time.Minute, true},
		{"empty", 7 * time.Minute, "", false, 7 * time.Minute, true},
		{"90m", 0, "90m", false, 90 * time.Minute, true},
		{"0s", 0, "0s", false, 0, true},
		{"not-a-duration", 3 * time.Minute, "not-a-duration", false, 0, false},
	}
	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			key := "LINKSHORT_TEST_STRICT_DURATION"
			if tt.unset {
				os.Unsetenv(key)
			} else {
				t.Setenv(key, tt.val)
			}
			got, ok := getenvDuration(key, tt.def)
			if got != tt.want || ok != tt.wantOk {
				t.Fatalf("got %v %v, want %v %v", got, ok, tt.want, tt.wantOk)
			}
		})
	}
}
