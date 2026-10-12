package markdown

import (
	"strings"
	"testing"
)

const testFence = "`" + "`" + "`"

func TestRender(t *testing.T) {
	tests := []struct {
		name     string
		input    string
		contains []string
	}{
		{
			name:     "heading",
			input:    "# Title",
			contains: []string{"<h1>Title</h1>"},
		},
		{
			name:     "heading levels",
			input:    "### Sub",
			contains: []string{"<h3>Sub</h3>"},
		},
		{
			name:     "bold",
			input:    "hello **world**",
			contains: []string{"<strong>world</strong>"},
		},
		{
			name:     "italic",
			input:    "hello *world*",
			contains: []string{"<em>world</em>"},
		},
		{
			name:     "inline code",
			input:    "use `fmt.Println`",
			contains: []string{"<code>fmt.Println</code>"},
		},
		{
			name:     "code block",
			input:    testFence + "go\nfmt.Println(\"hi\")\n" + testFence,
			contains: []string{"<pre><code>", "fmt.Println(&#34;hi&#34;)"},
		},
		{
			name:     "unordered list",
			input:    "- one\n- two",
			contains: []string{"<ul>", "<li>one</li>", "<li>two</li>", "</ul>"},
		},
		{
			name:     "ordered list",
			input:    "1. one\n2. two",
			contains: []string{"<ol>", "<li>one</li>", "<li>two</li>", "</ol>"},
		},
		{
			name:     "blockquote",
			input:    "> quoted",
			contains: []string{"<blockquote>", "quoted", "</blockquote>"},
		},
		{
			name:     "link",
			input:    "[text](https://example.com)",
			contains: []string{`<a href="https://example.com"`, `>text</a>`},
		},
		{
			name:     "wiki link",
			input:    "see [[My Note]]",
			contains: []string{`<a href="#" data-wiki="My Note">My Note</a>`},
		},
		{
			name:     "html escape",
			input:    "<script>alert(1)</script>",
			contains: []string{"&lt;script&gt;", "&lt;/script&gt;"},
		},
		{
			name:     "horizontal rule",
			input:    "a\n\n---\n\nb",
			contains: []string{"<hr>"},
		},
		{
			name:     "paragraph",
			input:    "just text",
			contains: []string{"<p>just text</p>"},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := Render(tt.input)
			for _, want := range tt.contains {
				if !strings.Contains(got, want) {
					t.Errorf("Render(%q) = %q; want it to contain %q", tt.input, got, want)
				}
			}
		})
	}
}
