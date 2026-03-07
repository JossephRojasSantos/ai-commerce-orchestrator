package checker

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCheckEnvCompleteness(t *testing.T) {
	dir := t.TempDir()
	examplePath := filepath.Join(dir, ".env.example")
	envPath := filepath.Join(dir, ".env")

	err := os.WriteFile(examplePath, []byte("A=1\nB=2\nC=3\n"), 0o644)
	if err != nil {
		t.Fatal(err)
	}
	err = os.WriteFile(envPath, []byte("A=1\nC=3\n"), 0o644)
	if err != nil {
		t.Fatal(err)
	}

	result := CheckEnvCompleteness(examplePath, envPath)
	if result.Status != StatusFail {
		t.Fatalf("expected fail, got %s", result.Status)
	}

	err = os.WriteFile(envPath, []byte("A=1\nB=2\nC=3\n"), 0o644)
	if err != nil {
		t.Fatal(err)
	}
	result = CheckEnvCompleteness(examplePath, envPath)
	if result.Status != StatusOK {
		t.Fatalf("expected pass, got %s", result.Status)
	}
}
