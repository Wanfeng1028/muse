package config

import (
	"testing"
)

func TestGetIntEnv(t *testing.T) {
	tests := []struct {
		name   string
		key    string
		value  string
		set    bool
		def    int
		wantN  int
		wantOk bool
	}{
		{
			name:   "unset",
			key:    "SB_TEST_GETINTENV_1",
			set:    false,
			def:    587,
			wantN:  587,
			wantOk: true,
		},
		{
			name:   "valid 587",
			key:    "SB_TEST_GETINTENV_2",
			value:  "587",
			set:    true,
			def:    587,
			wantN:  587,
			wantOk: true,
		},
		{
			name:   "whitespace 40",
			key:    "SB_TEST_GETINTENV_3",
			value:  " 40 ",
			set:    true,
			def:    40,
			wantN:  40,
			wantOk: true,
		},
		{
			name:   "non-numeric abc",
			key:    "SB_TEST_GETINTENV_4",
			value:  "abc",
			set:    true,
			def:    40,
			wantN:  0,
			wantOk: false,
		},
		{
			name:   "decimal 1.5",
			key:    "SB_TEST_GETINTENV_5",
			value:  "1.5",
			set:    true,
			def:    40,
			wantN:  0,
			wantOk: false,
		},
		{
			name:   "trailing x",
			key:    "SB_TEST_GETINTENV_6",
			value:  "1x",
			set:    true,
			def:    40,
			wantN:  0,
			wantOk: false,
		},
		{
			name:   "negative -5",
			key:    "SB_TEST_GETINTENV_7",
			value:  "-5",
			set:    true,
			def:    40,
			wantN:  -5,
			wantOk: true,
		},
		{
			name:   "empty string",
			key:    "SB_TEST_GETINTENV_8",
			value:  "",
			set:    true,
			def:    40,
			wantN:  40,
			wantOk: true,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if tt.set {
				t.Setenv(tt.key, tt.value)
			}
			gotN, gotOk := getIntEnv(tt.key, tt.def)
			if gotN != tt.wantN || gotOk != tt.wantOk {
				t.Errorf("getIntEnv(%q, %d) = (%d, %v), want (%d, %v)",
					tt.key, tt.def, gotN, gotOk, tt.wantN, tt.wantOk)
			}
		})
	}
}
