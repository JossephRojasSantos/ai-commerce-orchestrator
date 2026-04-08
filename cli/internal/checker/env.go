package checker

import (
	"bufio"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"
)

func ReadEnvFile(path string) (map[string]string, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	values := make(map[string]string)
	s := bufio.NewScanner(file)
	for s.Scan() {
		line := strings.TrimSpace(s.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		eq := strings.Index(line, "=")
		if eq <= 0 {
			continue
		}
		key := strings.TrimSpace(line[:eq])
		val := strings.TrimSpace(line[eq+1:])
		values[key] = val
	}
	if err := s.Err(); err != nil {
		return nil, err
	}
	return values, nil
}

type EnvCompletenessChecker struct {
	ExamplePath string
	EnvPath     string
}

func (c EnvCompletenessChecker) Run() CheckResult {
	return CheckEnvCompleteness(c.ExamplePath, c.EnvPath)
}

func CheckEnvCompleteness(examplePath, envPath string) CheckResult {
	start := time.Now()
	required, err := ReadEnvFile(examplePath)
	if err != nil {
		return CheckResult{Name: ".env", Status: StatusFail, Message: fmt.Sprintf("no se pudo leer %s", examplePath), LatencyMS: time.Since(start).Milliseconds()}
	}
	current, err := ReadEnvFile(envPath)
	if err != nil {
		return CheckResult{Name: ".env", Status: StatusFail, Message: fmt.Sprintf("no se pudo leer %s", envPath), LatencyMS: time.Since(start).Milliseconds()}
	}

	missing := make([]string, 0)
	for k := range required {
		if _, ok := current[k]; !ok {
			missing = append(missing, k)
		}
	}
	sort.Strings(missing)

	latency := time.Since(start)
	if len(missing) > 0 {
		return CheckResult{Name: ".env", Status: StatusFail, Message: fmt.Sprintf("faltan %d variables: %s", len(missing), strings.Join(missing, ", ")), LatencyMS: latency.Milliseconds()}
	}
	return CheckResult{Name: ".env", Status: StatusOK, Message: "completo vs .env.example", LatencyMS: latency.Milliseconds()}
}
