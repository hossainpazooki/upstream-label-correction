package api

import (
	"net/http"
	"net/http/httptest"
	"testing"
)

// okHandler is the protected handler the Auth middleware wraps in these tests.
func okHandler() http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})
}

func TestAuth(t *testing.T) {
	const token = "s3cr3t-service-token"

	cases := []struct {
		name       string
		token      string // token the middleware is configured with
		method     string
		header     string // value sent in X-Service-Token ("" = header absent)
		setHeader  bool
		wantStatus int
	}{
		{name: "empty token disables auth (bypass)", token: "", method: http.MethodPost, setHeader: false, wantStatus: http.StatusOK},
		{name: "correct token passes", token: token, method: http.MethodPost, header: token, setHeader: true, wantStatus: http.StatusOK},
		{name: "missing header is rejected", token: token, method: http.MethodPost, setHeader: false, wantStatus: http.StatusUnauthorized},
		{name: "wrong token is rejected", token: token, method: http.MethodPost, header: "nope", setHeader: true, wantStatus: http.StatusUnauthorized},
		{name: "prefix of token is rejected", token: token, method: http.MethodPost, header: token[:5], setHeader: true, wantStatus: http.StatusUnauthorized},
		{name: "OPTIONS preflight always allowed", token: token, method: http.MethodOptions, setHeader: false, wantStatus: http.StatusOK},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			h := Auth(c.token)(okHandler())
			req := httptest.NewRequest(c.method, "/api/v1/intents", nil)
			if c.setHeader {
				req.Header.Set("X-Service-Token", c.header)
			}
			rec := httptest.NewRecorder()
			h.ServeHTTP(rec, req)
			if rec.Code != c.wantStatus {
				t.Errorf("status = %d, want %d", rec.Code, c.wantStatus)
			}
		})
	}
}
