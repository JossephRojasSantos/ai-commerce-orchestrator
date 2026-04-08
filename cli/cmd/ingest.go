package cmd

import (
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/josrojas/ai-commerce-cli/internal/checker"
	"github.com/josrojas/ai-commerce-cli/internal/printer"
	"github.com/spf13/cobra"
)

var (
	ingestURL     string
	ingestTimeout time.Duration
)

var ingestCmd = &cobra.Command{
	Use:   "ingest",
	Short: "Dispara re-indexacion RAG en /admin/reindex",
	RunE: func(cmd *cobra.Command, args []string) error {
		adminKey := strings.TrimSpace(os.Getenv("ADMIN_API_KEY"))
		if adminKey == "" {
			return fmt.Errorf("ADMIN_API_KEY requerida")
		}

		start := time.Now()
		req, err := http.NewRequest(http.MethodPost, strings.TrimRight(ingestURL, "/")+"/admin/reindex", nil)
		if err != nil {
			return err
		}
		req.Header.Set("X-Admin-Key", adminKey)

		client := &http.Client{Timeout: ingestTimeout}
		resp, err := client.Do(req)
		latency := time.Since(start)
		if err != nil {
			printer.PrintResults("ai-commerce-cli ingest", []checker.CheckResult{{
				Name:      "RAG Reindex",
				Status:    checker.StatusFail,
				Message:   fmt.Sprintf("error: %v", err),
				LatencyMS: latency.Milliseconds(),
			}})
			return fmt.Errorf("ingest failed")
		}
		defer resp.Body.Close()

		status := checker.StatusOK
		message := fmt.Sprintf("HTTP %d", resp.StatusCode)
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			status = checker.StatusFail
		}

		result := checker.CheckResult{
			Name:      "RAG Reindex",
			Status:    status,
			Message:   message,
			LatencyMS: latency.Milliseconds(),
		}
		printer.PrintResults("ai-commerce-cli ingest", []checker.CheckResult{result})

		if status == checker.StatusFail {
			return fmt.Errorf("ingest failed")
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(ingestCmd)
	ingestCmd.Flags().StringVar(&ingestURL, "url", "http://localhost:8000", "URL base del backend")
	ingestCmd.Flags().DurationVar(&ingestTimeout, "timeout", 10*time.Second, "Timeout de reindex request")
}
