package store

import (
	"math"
	"testing"
)

func TestR2_PercentileLinear(t *testing.T) {
	tests := []struct {
		name   string
		sorted []float64
		p      float64
		want   float64
	}{
		{
			name:   "empty slice returns zero",
			sorted: []float64{},
			p:      50,
			want:   0,
		},
		{
			name:   "single element returns only value",
			sorted: []float64{7},
			p:      50,
			want:   7,
		},
		{
			name:   "zero percentile returns first",
			sorted: []float64{1, 2, 3, 4},
			p:      0,
			want:   1,
		},
		{
			name:   "full percentile returns last",
			sorted: []float64{1, 2, 3, 4},
			p:      100,
			want:   4,
		},
		{
			name:   "median interpolates between elements",
			sorted: []float64{1, 2, 3, 4},
			p:      50,
			want:   2.5,
		},
		{
			name:   "quarter interpolates between elements",
			sorted: []float64{0, 100},
			p:      25,
			want:   25,
		},
		{
			name:   "negative percentile returns first",
			sorted: []float64{1, 2, 3},
			p:      -5,
			want:   1,
		},
		{
			name:   "percentile above range returns last",
			sorted: []float64{1, 2, 3},
			p:      200,
			want:   3,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := percentileLinear(tt.sorted, tt.p)
			if math.Abs(got-tt.want) >= 1e-9 {
				t.Fatalf("percentileLinear(%v, %v) = %v, want %v", tt.sorted, tt.p, got, tt.want)
			}
		})
	}
}
