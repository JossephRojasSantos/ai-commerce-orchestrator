package checker

import (
	"fmt"
	"net/http"
	"strings"
	"time"
)

type OpenAIKeyChecker struct {
	APIKey   string
	Endpoint string
	Timeout  time.Duration
}

func (c OpenAIKeyChecker) Run() CheckResult {
	return CheckOpenAIKey(c.APIKey, c.Endpoint, c.Timeout)
}

func CheckOpenAIKey(apiKey, endpoint string, timeout time.Duration) CheckResult {
	start := time.Now()
	if strings.TrimSpace(apiKey) == "" {
		return CheckResult{Name: "OpenAI API", Status: StatusFail, Message: "LLM_API_KEY no configurada", LatencyMS: time.Since(start).Milliseconds()}
	}

	client := &http.Client{Timeout: timeout}
	req, err := http.NewRequest(http.MethodGet, endpoint, nil)
	if err != nil {
		return CheckResult{Name: "OpenAI API", Status: StatusFail, Message: "endpoint invalido", LatencyMS: time.Since(start).Milliseconds()}
	}
	req.Header.Set("Authorization", "Bearer "+apiKey)

	resp, err := client.Do(req)
	latency := time.Since(start)
	if err != nil {
		return CheckResult{Name: "OpenAI API", Status: StatusFail, Message: fmt.Sprintf("request error: %v", err), LatencyMS: latency.Milliseconds()}
	}
	defer resp.Body.Close()

	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return CheckResult{Name: "OpenAI API", Status: StatusFail, Message: fmt.Sprintf("HTTP %d", resp.StatusCode), LatencyMS: latency.Milliseconds()}
	}
	return CheckResult{Name: "OpenAI API", Status: StatusOK, Message: fmt.Sprintf("HTTP %d", resp.StatusCode), LatencyMS: latency.Milliseconds()}
}
