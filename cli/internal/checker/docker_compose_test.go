package checker

import (
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestDockerAndComposeChecksWithFakeBinary(t *testing.T) {
	if runtime.GOOS == "windows" {
		t.Skip("shell script test")
	}

	dir := t.TempDir()
	dockerPath := filepath.Join(dir, "docker")
	script := `#!/usr/bin/env bash
if [ "$1" = "--version" ]; then
  echo "Docker version 28.5.2, build test"
  exit 0
fi
if [ "$1" = "compose" ] && [ "$2" = "version" ]; then
  echo "Docker Compose version v2.35.1"
  exit 0
fi
echo "unsupported" >&2
exit 1
`
	if err := os.WriteFile(dockerPath, []byte(script), 0o755); err != nil {
		t.Fatal(err)
	}

	oldPath := os.Getenv("PATH")
	t.Cleanup(func() { _ = os.Setenv("PATH", oldPath) })
	if err := os.Setenv("PATH", dir+string(os.PathListSeparator)+oldPath); err != nil {
		t.Fatal(err)
	}

	dockerResult := CheckDockerVersion(24, 0)
	if dockerResult.Status != StatusOK {
		t.Fatalf("expected docker pass, got %s (%s)", dockerResult.Status, dockerResult.Message)
	}

	composeResult := CheckComposeVersion(2, 20)
	if composeResult.Status != StatusOK {
		t.Fatalf("expected compose pass, got %s (%s)", composeResult.Status, composeResult.Message)
	}
}

func TestDockerAndComposeChecksWhenMissing(t *testing.T) {
	oldPath := os.Getenv("PATH")
	t.Cleanup(func() { _ = os.Setenv("PATH", oldPath) })
	if err := os.Setenv("PATH", ""); err != nil {
		t.Fatal(err)
	}

	if got := CheckDockerVersion(24, 0).Status; got != StatusFail {
		t.Fatalf("expected docker fail, got %s", got)
	}
	if got := CheckComposeVersion(2, 20).Status; got != StatusFail {
		t.Fatalf("expected compose fail, got %s", got)
	}
}
