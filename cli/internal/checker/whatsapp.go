package checker

import "time"

type WhatsAppTokenChecker struct {
	Token string
}

func (c WhatsAppTokenChecker) Run() CheckResult {
	return CheckWhatsAppVerifyToken(c.Token)
}

func CheckWhatsAppVerifyToken(token string) CheckResult {
	start := time.Now()
	if token == "" {
		return CheckResult{Name: "WhatsApp Verify Token", Status: StatusFail, Message: "WHATSAPP_VERIFY_TOKEN no configurada", LatencyMS: time.Since(start).Milliseconds()}
	}
	return CheckResult{Name: "WhatsApp Verify Token", Status: StatusOK, Message: "configurada", LatencyMS: time.Since(start).Milliseconds()}
}
