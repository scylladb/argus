package main

import (
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

const sessionFile = "argus-session"

func getCFToken(appURL string) (string, error) {
	out, err := exec.Command("cloudflared", "access", "login", appURL).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("cloudflared login failed: %w\n%s", err, out)
	}

	tokenOut, err := exec.Command("cloudflared", "access", "token", "-app="+appURL).CombinedOutput()
	if err != nil {
		return "", fmt.Errorf("cloudflared token failed: %w\n%s", err, tokenOut)
	}

	return strings.TrimSpace(string(tokenOut)), nil
}

func sessionPath() (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	return filepath.Join(home, ".cloudflared", sessionFile), nil
}

func loadSession() string {
	path, err := sessionPath()
	if err != nil {
		return ""
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ""
	}
	return strings.TrimSpace(string(data))
}

func saveSession(session string) error {
	path, err := sessionPath()
	if err != nil {
		return err
	}
	return os.WriteFile(path, []byte(session), 0600)
}

func login(appURL, cfToken string) (string, error) {
	req, err := http.NewRequest("POST", appURL+"/auth/login/cf", nil)
	if err != nil {
		return "", err
	}
	req.AddCookie(&http.Cookie{Name: "CF_Authorization", Value: cfToken})

	client := &http.Client{
		CheckRedirect: func(req *http.Request, via []*http.Request) error {
			return http.ErrUseLastResponse
		},
	}
	resp, err := client.Do(req)
	if err != nil {
		return "", fmt.Errorf("login request failed: %w", err)
	}
	resp.Body.Close()

	for _, c := range resp.Cookies() {
		if c.Name == "session" {
			return c.Value, nil
		}
	}
	return "", fmt.Errorf("no session cookie in login response (status %d)", resp.StatusCode)
}

// ArgusClient holds auth state for making requests to Argus.
type ArgusClient struct {
	BaseURL string
	cfToken string
	session string
}

func NewArgusClient(baseURL string) (*ArgusClient, error) {
	cfToken, err := getCFToken(baseURL)
	if err != nil {
		return nil, err
	}

	c := &ArgusClient{BaseURL: baseURL, cfToken: cfToken}

	// Try existing session first
	if session := loadSession(); session != "" {
		c.session = session
	}

	return c, nil
}

func (c *ArgusClient) Do(req *http.Request) (*http.Response, error) {
	req.AddCookie(&http.Cookie{Name: "CF_Authorization", Value: c.cfToken})
	if c.session != "" {
		req.AddCookie(&http.Cookie{Name: "session", Value: c.session})
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}

	// If 401/403, try re-login and retry once
	if resp.StatusCode == 401 || resp.StatusCode == 403 {
		resp.Body.Close()

		session, err := login(c.BaseURL, c.cfToken)
		if err != nil {
			return nil, fmt.Errorf("re-login failed: %w", err)
		}
		c.session = session
		saveSession(session)

		// Retry the request with new session
		req.Header.Del("Cookie")
		req.AddCookie(&http.Cookie{Name: "CF_Authorization", Value: c.cfToken})
		req.AddCookie(&http.Cookie{Name: "session", Value: c.session})
		return http.DefaultClient.Do(req)
	}

	return resp, nil
}
