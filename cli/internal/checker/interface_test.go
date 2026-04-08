package checker

import "time"

var (
	_ Checker = DockerVersionChecker{}
	_ Checker = ComposeVersionChecker{}
	_ Checker = EnvCompletenessChecker{}
	_ Checker = PortsAvailabilityChecker{}
	_ Checker = OpenAIKeyChecker{}
	_ Checker = WhatsAppTokenChecker{}
	_ Checker = OpenAIKeyChecker{Timeout: 1 * time.Second}
)
