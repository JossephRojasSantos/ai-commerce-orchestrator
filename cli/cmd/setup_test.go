package cmd

import "testing"

func TestParsePortsCSV(t *testing.T) {
	ports, err := parsePortsCSV("5432,6379, 8000")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(ports) != 3 || ports[0] != 5432 || ports[2] != 8000 {
		t.Fatalf("unexpected ports: %#v", ports)
	}

	if _, err := parsePortsCSV("abc"); err == nil {
		t.Fatal("expected error")
	}
}

func TestResolveEnvValue(t *testing.T) {
	env := map[string]string{"X": "from-file"}
	if got := resolveEnvValue("X", env); got != "from-file" {
		t.Fatalf("unexpected value: %s", got)
	}
}
