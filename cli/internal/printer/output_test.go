package printer

import (
	"testing"

	"github.com/josrojas/ai-commerce-cli/internal/checker"
)

func TestColorizeStatusNoColor(t *testing.T) {
	t.Setenv("NO_COLOR", "1")
	if got := colorizeStatus(checker.StatusOK); got != "+ OK" {
		t.Fatalf("unexpected status: %q", got)
	}
}

func TestColorizeStatusFallbackOnNonTTY(t *testing.T) {
	t.Setenv("NO_COLOR", "")
	if got := colorizeStatus(checker.StatusFail); got != "x FAIL" {
		t.Fatalf("unexpected status: %q", got)
	}
}
