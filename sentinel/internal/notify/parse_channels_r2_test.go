package notify

import (
	"reflect"
	"testing"
)

func TestR2_ParseChannels(t *testing.T) {
	tests := []struct {
		name  string
		input string
		want  []string
	}{
		{"empty input returns empty slice", "", []string{}},
		{"single valid channel", "webhook", []string{"webhook"}},
		{"case insensitive with spaces", "WEBHOOK, Sms", []string{"webhook", "sms"}},
		{"dedupe preserves first occurrence order", "webhook,webhook,smtp", []string{"webhook", "smtp"}},
		{"invalid channel names are dropped", "webhook,carrier-pigeon,sms", []string{"webhook", "sms"}},
		{"all parts are empty", " , ,", []string{}},
		{"spaces around valid channels are tolerated", "wecom, smtp ,SMS", []string{"wecom", "smtp", "sms"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := ParseChannels(tt.input)
			if !reflect.DeepEqual([]string{}, got) && !reflect.DeepEqual(tt.want, got) {
				t.Fatalf("ParseChannels(%q) = %#v, want %#v", tt.input, got, tt.want)
			}
		})
	}
}
