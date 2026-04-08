package checker

import (
	"fmt"
	"os/exec"
	"strings"
	"time"
)

type ComposeVersionChecker struct {
	MinMajor int
	MinMinor int
}

func (c ComposeVersionChecker) Run() CheckResult {
	return CheckComposeVersion(c.MinMajor, c.MinMinor)
}

func CheckComposeVersion(minMajor, minMinor int) CheckResult {
	start := time.Now()
	path, err := exec.LookPath("docker")
	if err != nil {
		return CheckResult{Name: "Docker Compose", Status: StatusFail, Message: "docker no instalado", LatencyMS: time.Since(start).Milliseconds()}
	}

	out, err := exec.Command(path, "compose", "version").CombinedOutput()
	latency := time.Since(start)
	if err != nil {
		return CheckResult{Name: "Docker Compose", Status: StatusFail, Message: strings.TrimSpace(string(out)), LatencyMS: latency.Milliseconds()}
	}

	major, minor, err := parseVersion(string(out))
	if err != nil {
		return CheckResult{Name: "Docker Compose", Status: StatusFail, Message: "no se pudo parsear version", LatencyMS: latency.Milliseconds()}
	}
	if !versionAtLeast(major, minor, minMajor, minMinor) {
		return CheckResult{Name: "Docker Compose", Status: StatusFail, Message: fmt.Sprintf("version %d.%d (< %d.%d)", major, minor, minMajor, minMinor), LatencyMS: latency.Milliseconds()}
	}
	return CheckResult{Name: "Docker Compose", Status: StatusOK, Message: fmt.Sprintf("version %d.%d", major, minor), LatencyMS: latency.Milliseconds()}
}
