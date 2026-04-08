package cmd

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/josrojas/ai-commerce-cli/internal/checker"
	"github.com/josrojas/ai-commerce-cli/internal/printer"
	"github.com/spf13/cobra"
)

var (
	setupEnvFile     string
	setupExampleFile string
	setupPorts       string
	setupOpenAIURL   string
	setupTimeout     time.Duration
)

var setupCmd = &cobra.Command{
	Use:   "setup",
	Short: "Valida entorno local antes de levantar Docker",
	RunE: func(cmd *cobra.Command, args []string) error {
		envValues, _ := checker.ReadEnvFile(setupEnvFile)
		apiKey := resolveEnvValue("LLM_API_KEY", envValues)

		ports, err := parsePortsCSV(setupPorts)
		if err != nil {
			return fmt.Errorf("puertos invalidos en --ports: %w", err)
		}

		checks := []checker.Checker{
			checker.DockerVersionChecker{MinMajor: 24, MinMinor: 0},
			checker.ComposeVersionChecker{MinMajor: 2, MinMinor: 20},
			checker.EnvCompletenessChecker{ExamplePath: setupExampleFile, EnvPath: setupEnvFile},
			checker.PortsAvailabilityChecker{Ports: ports},
			checker.OpenAIKeyChecker{APIKey: apiKey, Endpoint: setupOpenAIURL, Timeout: setupTimeout},
		}

		results := make([]checker.CheckResult, 0, len(checks))
		for _, c := range checks {
			results = append(results, c.Run())
		}

		printer.PrintResults("ai-commerce-cli setup", results)
		if checker.HasFailures(results) {
			return fmt.Errorf("setup incomplete")
		}
		return nil
	},
}

func init() {
	rootCmd.AddCommand(setupCmd)
	setupCmd.Flags().StringVar(&setupEnvFile, "env-file", ".env", "Ruta al archivo .env")
	setupCmd.Flags().StringVar(&setupExampleFile, "example-file", ".env.example", "Ruta al archivo .env.example")
	setupCmd.Flags().StringVar(&setupPorts, "ports", "5432,6379,8000,6432", "Lista de puertos separados por coma")
	setupCmd.Flags().StringVar(&setupOpenAIURL, "openai-url", "https://api.openai.com/v1/models", "Endpoint para validar API key de OpenAI")
	setupCmd.Flags().DurationVar(&setupTimeout, "timeout", 5*time.Second, "Timeout para checks de red")
}

func parsePortsCSV(raw string) ([]int, error) {
	parts := strings.Split(raw, ",")
	ports := make([]int, 0, len(parts))
	for _, p := range parts {
		trimmed := strings.TrimSpace(p)
		if trimmed == "" {
			continue
		}
		port, err := strconv.Atoi(trimmed)
		if err != nil {
			return nil, err
		}
		ports = append(ports, port)
	}
	if len(ports) == 0 {
		return nil, fmt.Errorf("sin puertos")
	}
	return ports, nil
}

func resolveEnvValue(key string, fileValues map[string]string) string {
	if v := os.Getenv(key); strings.TrimSpace(v) != "" {
		return strings.TrimSpace(v)
	}
	if v, ok := fileValues[key]; ok {
		return strings.TrimSpace(v)
	}
	return ""
}
