package cmd

import (
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/josrojas/ai-commerce-cli/internal/checker"
	"github.com/josrojas/ai-commerce-cli/internal/printer"
	"github.com/spf13/cobra"
)

var (
	healthURL     string
	healthTimeout time.Duration
)

var healthCmd = &cobra.Command{
	Use:   "health",
	Short: "Chequea salud y latencia de servicios backend",
	RunE: func(cmd *cobra.Command, args []string) error {
		baseURL := strings.TrimRight(healthURL, "/")
		client := &http.Client{Timeout: healthTimeout}

		services := []struct {
			name     string
			endpoint string
		}{
			{name: "FastAPI Backend", endpoint: "/health"},
			{name: "PostgreSQL", endpoint: "/health/postgres"},
			{name: "Redis", endpoint: "/health/redis"},
			{name: "OpenAI API", endpoint: "/health/openai"},
		}

		results := make([]checker.CheckResult, 0, len(services))
		for _, service := range services {
			start := time.Now()
			resp, err := client.Get(baseURL + service.endpoint)
			latency := time.Since(start)
			if err != nil {
				results = append(results, checker.CheckResult{
					Name:      service.name,
					Status:    checker.StatusFail,
					Message:   fmt.Sprintf("error: %v", err),
					LatencyMS: latency.Milliseconds(),
				})
				continue
			}
			resp.Body.Close()

			status := checker.StatusOK
			message := fmt.Sprintf("HTTP %d", resp.StatusCode)
			if resp.StatusCode >= 400 {
				status = checker.StatusFail
			}
			results = append(results, checker.CheckResult{
				Name:      service.name,
				Status:    status,
				Message:   message,
				LatencyMS: latency.Milliseconds(),
			})
		}

		printer.PrintResults("ai-commerce-cli health", results)
		if checker.HasFailures(results) {
			return fmt.Errorf("health checks failed")
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(healthCmd)
	healthCmd.Flags().StringVar(&healthURL, "url", "http://localhost:8000", "URL base del backend")
	healthCmd.Flags().DurationVar(&healthTimeout, "timeout", 5*time.Second, "Timeout por request")
}
