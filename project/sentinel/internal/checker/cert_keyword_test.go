package checker

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/pem"
	"math/big"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"sentinel/internal/store"
)

func TestAssertKeyword_Modes(t *testing.T) {
	body := []byte("Hello Sentinel World")
	cases := []struct {
		name    string
		body    []byte
		keyword string
		mode    string
		wantErr bool
		errSub  string
	}{
		{"exact hit", body, "Hello", "exact", false, ""},
		{"exact miss case", body, "hello", "exact", true, ""},
		{"exact empty mode", body, "Sentinel", "", false, ""},
		{"ignorecase hit", body, "sentinel", "ignorecase", false, ""},
		{"regex hit", body, "H.llo", "regex", false, ""},
		{"empty keyword", body, "", "exact", false, ""},
		{"invalid mode", body, "Hello", "bogus", true, ""},
		{"invalid regex", body, "[", "regex", true, "关键字正则非法"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			err := AssertKeyword(c.body, c.keyword, c.mode)
			if c.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil")
				}
				if c.errSub != "" && !strings.Contains(err.Error(), c.errSub) {
					t.Fatalf("error %q does not contain %q", err.Error(), c.errSub)
				}
			} else if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
		})
	}
}

func TestParseTLSHostPort(t *testing.T) {
	cases := []struct {
		target  string
		want    string
		wantErr bool
	}{
		{"https://example.com", "example.com:443", false},
		{"https://example.com:8443/path", "example.com:8443", false},
		{"http://example.com", "", true},
		{"not-a-url", "", true},
	}
	for _, c := range cases {
		t.Run(c.target, func(t *testing.T) {
			got, err := ParseTLSHostPort(c.target)
			if c.wantErr {
				if err == nil {
					t.Fatalf("expected error, got nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("unexpected error: %v", err)
			}
			if got != c.want {
				t.Fatalf("got %q, want %q", got, c.want)
			}
		})
	}
}

func genCert(t *testing.T, notAfter time.Time) (certPEM, keyPEM []byte) {
	t.Helper()
	key, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("generate key: %v", err)
	}
	tmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(time.Now().UnixNano()),
		Subject:               pkix.Name{CommonName: "sentinel-test"},
		NotBefore:             time.Now().Add(-time.Hour),
		NotAfter:              notAfter,
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageCertSign,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
		DNSNames:              []string{"localhost"},
		IPAddresses:           []net.IP{net.ParseIP("127.0.0.1")},
	}
	der, err := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	if err != nil {
		t.Fatalf("create cert: %v", err)
	}
	certPEM = pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	keyDER, err := x509.MarshalECPrivateKey(key)
	if err != nil {
		t.Fatalf("marshal key: %v", err)
	}
	keyPEM = pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: keyDER})
	return certPEM, keyPEM
}

func startTLSServer(t *testing.T, certPEM, keyPEM []byte, handler http.Handler) (string, func()) {
	t.Helper()
	cert, err := tls.X509KeyPair(certPEM, keyPEM)
	if err != nil {
		t.Fatalf("key pair: %v", err)
	}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		t.Fatalf("listen: %v", err)
	}
	tlsLn := tls.NewListener(ln, &tls.Config{Certificates: []tls.Certificate{cert}})
	srv := &http.Server{Handler: handler}
	go srv.Serve(tlsLn)
	return ln.Addr().String(), func() { srv.Close() }
}

func TestCheckCertExpiry_Warn(t *testing.T) {
	certPEM, keyPEM := genCert(t, time.Now().Add(48*time.Hour))
	addr, stop := startTLSServer(t, certPEM, keyPEM, http.NotFoundHandler())
	defer stop()

	daysLeft, warn, err := CheckCertExpiry("https://"+addr, 7, 5*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !warn {
		t.Fatalf("expected warn=true, daysLeft=%d", daysLeft)
	}
	if daysLeft < 1 || daysLeft > 2 {
		t.Fatalf("daysLeft=%d, want 1..2", daysLeft)
	}
}

func TestCheckCertExpiry_NoWarn(t *testing.T) {
	certPEM, keyPEM := genCert(t, time.Now().Add(90*24*time.Hour))
	addr, stop := startTLSServer(t, certPEM, keyPEM, http.NotFoundHandler())
	defer stop()

	daysLeft, warn, err := CheckCertExpiry("https://"+addr, 7, 5*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if warn {
		t.Fatalf("expected warn=false, daysLeft=%d", daysLeft)
	}
	if daysLeft <= 80 {
		t.Fatalf("daysLeft=%d, want >80", daysLeft)
	}
}

func TestCheckCertExpiry_Expired(t *testing.T) {
	certPEM, keyPEM := genCert(t, time.Now().Add(-24*time.Hour))
	addr, stop := startTLSServer(t, certPEM, keyPEM, http.NotFoundHandler())
	defer stop()

	daysLeft, warn, err := CheckCertExpiry("https://"+addr, 7, 5*time.Second)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if daysLeft >= 0 {
		t.Fatalf("daysLeft=%d, want <0", daysLeft)
	}
	if !warn {
		t.Fatalf("expected warn=true")
	}
}

func TestCheckHTTP_KeywordIntegration(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Write([]byte("Hello Sentinel World"))
	}))
	defer ts.Close()

	base := store.Monitor{Kind: "http", Target: ts.URL, ExpectedStatus: 200, TimeoutSec: 5}

	m1 := base
	m1.Keyword = "sentinel"
	m1.KeywordMode = "ignorecase"
	if c := Check(m1); c.Ok != 1 {
		t.Fatalf("ignorecase: Ok=%d, Error=%q", c.Ok, c.Error)
	}

	m2 := base
	m2.Keyword = "sentinel"
	m2.KeywordMode = "exact"
	if c := Check(m2); c.Ok != 0 {
		t.Fatalf("exact: expected Ok=0, got %d", c.Ok)
	} else if !strings.Contains(c.Error, "关键字") {
		t.Fatalf("exact: Error=%q, want contains 关键字", c.Error)
	}

	m3 := base
	m3.Keyword = "["
	m3.KeywordMode = "regex"
	if c := Check(m3); c.Ok != 0 {
		t.Fatalf("regex invalid: expected Ok=0, got %d", c.Ok)
	}
}

func TestCheckHTTP_CertWarnIntegration(t *testing.T) {
	caCertPEM, caKeyPEM := genCert(t, time.Now().Add(10*365*24*time.Hour))
	caKey, err := tls.X509KeyPair(caCertPEM, caKeyPEM)
	if err != nil {
		t.Fatalf("ca key pair: %v", err)
	}
	_ = caKey

	caParsed, err := x509.ParseCertificate(mustDecodePEM(t, caCertPEM))
	if err != nil {
		t.Fatalf("parse ca: %v", err)
	}

	srvKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatalf("gen srv key: %v", err)
	}
	srvTmpl := &x509.Certificate{
		SerialNumber: big.NewInt(time.Now().UnixNano() + 1),
		Subject:      pkix.Name{CommonName: "127.0.0.1"},
		NotBefore:    time.Now().Add(-time.Hour),
		NotAfter:     time.Now().Add(5 * 24 * time.Hour),
		KeyUsage:     x509.KeyUsageDigitalSignature,
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1")},
	}
	srvDER, err := x509.CreateCertificate(rand.Reader, srvTmpl, caParsed, &srvKey.PublicKey, caKey.PrivateKey)
	if err != nil {
		t.Fatalf("sign srv cert: %v", err)
	}
	srvCertPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: srvDER})
	srvKeyDER, err := x509.MarshalECPrivateKey(srvKey)
	if err != nil {
		t.Fatalf("marshal srv key: %v", err)
	}
	srvKeyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: srvKeyDER})

	addr, stop := startTLSServer(t, srvCertPEM, srvKeyPEM, http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(200)
		w.Write([]byte("ok"))
	}))
	defer stop()

	dir := t.TempDir()
	caFile := filepath.Join(dir, "ca.pem")
	if err := os.WriteFile(caFile, caCertPEM, 0o644); err != nil {
		t.Fatalf("write ca: %v", err)
	}
	t.Setenv("SSL_CERT_FILE", caFile)

	m := store.Monitor{Kind: "http", Target: "https://" + addr, TimeoutSec: 5, CertWarnDays: 30}
	if c := Check(m); c.Ok != 0 {
		t.Fatalf("cert warn: expected Ok=0, got %d (Error=%q)", c.Ok, c.Error)
	} else if !strings.Contains(c.Error, "证书将于") {
		t.Fatalf("cert warn: Error=%q, want contains 证书将于", c.Error)
	}

	m2 := m
	m2.CertWarnDays = 0
	if c := Check(m2); c.Ok != 1 {
		t.Fatalf("no cert warn: expected Ok=1, got %d (Error=%q)", c.Ok, c.Error)
	}
}

func TestCheckHTTP_KeywordAfterStatusCode(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(500)
		w.Write([]byte("server error"))
	}))
	defer ts.Close()

	m := store.Monitor{
		Kind:           "http",
		Target:         ts.URL,
		ExpectedStatus: 200,
		TimeoutSec:     5,
		Keyword:        "xxx",
		KeywordMode:    "exact",
	}
	c := Check(m)
	if c.Ok != 0 {
		t.Fatalf("expected Ok=0, got %d", c.Ok)
	}
	if !strings.Contains(c.Error, "状态码不符") {
		t.Fatalf("Error=%q, want contains 状态码不符", c.Error)
	}
}

func mustDecodePEM(t *testing.T, data []byte) []byte {
	t.Helper()
	block, _ := pem.Decode(data)
	if block == nil {
		t.Fatalf("failed to decode PEM")
	}
	return block.Bytes
}
