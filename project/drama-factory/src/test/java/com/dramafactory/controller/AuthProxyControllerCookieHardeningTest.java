package com.dramafactory.controller;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthProxyControllerCookieHardeningTest {

    private HttpServer server;
    private String baseUrl;
    private final List<Recorded> recorded = new ArrayList<>();
    private volatile ResponseSpec nextResponse = new ResponseSpec(200, "{}");

    @BeforeEach
    void setUp() throws IOException {
        recorded.clear();
        server = HttpServer.create(new InetSocketAddress(InetAddress.getByName("::1"), 0), 0);
        server.createContext("/", this::handle);
        server.start();
        baseUrl = "http://[::1]:" + server.getAddress().getPort();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private void handle(HttpExchange exchange) throws IOException {
        String method = exchange.getRequestMethod();
        String path = exchange.getRequestURI().getPath();
        String authorization = exchange.getRequestHeaders().getFirst("Authorization");
        byte[] bodyBytes = readAll(exchange.getRequestBody());
        recorded.add(new Recorded(method, path, authorization, new String(bodyBytes, StandardCharsets.UTF_8)));

        ResponseSpec spec = nextResponse;
        byte[] respBody = spec.body == null ? new byte[0] : spec.body.getBytes(StandardCharsets.UTF_8);
        if (spec.contentType != null) {
            exchange.getResponseHeaders().set("Content-Type", spec.contentType);
        }
        exchange.sendResponseHeaders(spec.status, respBody.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(respBody);
        }
    }

    private static byte[] readAll(InputStream in) throws IOException {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        byte[] buf = new byte[4096];
        int n;
        while ((n = in.read(buf)) != -1) {
            bos.write(buf, 0, n);
        }
        return bos.toByteArray();
    }

    private AuthProxyController controller(boolean secure) {
        return new AuthProxyController(baseUrl, HttpClient.newHttpClient(), secure);
    }

    private AuthProxyController controllerDefault() {
        return new AuthProxyController(baseUrl, HttpClient.newHttpClient());
    }

    private static MockHttpServletRequest loginRequest(String origin, String host, String authorization) {
        MockHttpServletRequest req = new MockHttpServletRequest("POST", "/api/auth/login");
        req.setContentType("application/json");
        req.setContent("{\"username\":\"u\",\"password\":\"p\"}".getBytes(StandardCharsets.UTF_8));
        if (host != null) {
            req.addHeader("Host", host);
        }
        if (origin != null) {
            req.addHeader("Origin", origin);
        }
        if (authorization != null) {
            req.addHeader("Authorization", authorization);
        }
        return req;
    }

    private static List<String> setCookies(ResponseEntity<byte[]> entity) {
        List<String> cookies = entity.getHeaders().get(HttpHeaders.SET_COOKIE);
        return cookies == null ? List.of() : cookies;
    }

    @Test
    void loginSuccessWithSecureAddsSecureFlagToBothCookies() throws Exception {
        nextResponse = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}",
                "application/json");

        AuthProxyController controller = controller(true);
        MockHttpServletRequest req = loginRequest(null, null, null);
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals("{\"ok\":true}", new String(entity.getBody(), StandardCharsets.UTF_8));

        List<String> cookies = setCookies(entity);
        assertFalse(cookies.isEmpty(), "expected Set-Cookie headers");

        String dfAt = null;
        String dfRt = null;
        for (String c : cookies) {
            if (c.startsWith("df_at=")) {
                dfAt = c;
            } else if (c.startsWith("df_rt=")) {
                dfRt = c;
            }
        }
        assertNotNull(dfAt, "expected df_at cookie");
        assertNotNull(dfRt, "expected df_rt cookie");
        assertTrue(dfAt.contains("; Secure"), "df_at must contain ; Secure but was: " + dfAt);
        assertTrue(dfRt.contains("; Secure"), "df_rt must contain ; Secure but was: " + dfRt);

        int idxAt = dfAt.indexOf("; Secure");
        int idxMaxAt = dfAt.indexOf("Max-Age");
        assertTrue(idxMaxAt >= 0, "df_at must contain Max-Age");
        assertTrue(idxMaxAt < idxAt, "Secure must appear after Max-Age in df_at");
    }

    @Test
    void loginSuccessWithInsecureConstructorDoesNotAddSecureFlag() throws Exception {
        nextResponse = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}",
                "application/json");

        AuthProxyController controller = controllerDefault();
        MockHttpServletRequest req = loginRequest(null, null, null);
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals("{\"ok\":true}", new String(entity.getBody(), StandardCharsets.UTF_8));

        List<String> cookies = setCookies(entity);
        assertFalse(cookies.isEmpty(), "expected Set-Cookie headers");
        for (String c : cookies) {
            assertFalse(c.contains("; Secure"), "cookie must not contain Secure flag but was: " + c);
        }
    }

    @Test
    void postLoginWithoutAuthorizationAndCrossSiteOriginIsForbidden() throws Exception {
        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = loginRequest("https://evil.example", "localhost", null);
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(403, entity.getStatusCode().value());
        assertEquals("application/json", entity.getHeaders().getContentType().toString());
        String body = new String(entity.getBody(), StandardCharsets.UTF_8);
        assertTrue(body.contains("\"code\":\"FORBIDDEN\""), "body: " + body);
        assertTrue(body.contains("\"message\":\"跨站请求被拒绝\""), "body: " + body);
        assertTrue(recorded.isEmpty(), "upstream must not be called");
    }

    @Test
    void postLoginWithMatchingOriginIsAllowed() throws Exception {
        nextResponse = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}",
                "application/json");

        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = loginRequest("http://localhost", "localhost", null);
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals(1, recorded.size(), "upstream must receive exactly one request");
        assertEquals("POST", recorded.get(0).method);
        assertEquals("/api/auth/login", recorded.get(0).path);
    }

    @Test
    void postLoginWithoutOriginOrRefererIsAllowed() throws Exception {
        nextResponse = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}",
                "application/json");

        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = loginRequest(null, "localhost", null);
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals(1, recorded.size(), "upstream must receive exactly one request");
    }

    @Test
    void postWithAuthorizationHeaderAndSpoofedOriginIsAllowed() throws Exception {
        nextResponse = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}",
                "application/json");

        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = loginRequest("https://evil.example", "localhost", "Bearer token-123");
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals(1, recorded.size(), "upstream must receive exactly one request");
        assertEquals("Bearer token-123", recorded.get(0).authorization);
    }

    @Test
    void getMeWithSpoofedOriginIsAllowed() throws Exception {
        nextResponse = new ResponseSpec(200, "{\"user\":\"u\"}", "application/json");

        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = new MockHttpServletRequest("GET", "/api/auth/me");
        req.addHeader("Host", "localhost");
        req.addHeader("Origin", "https://evil.example");
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(200, entity.getStatusCode().value());
        assertEquals(1, recorded.size(), "upstream must receive exactly one request");
        assertEquals("GET", recorded.get(0).method);
        assertEquals("/api/auth/me", recorded.get(0).path);
    }

    @Test
    void postLoginWithSpoofedRefererIsForbidden() throws Exception {
        AuthProxyController controller = controller(false);
        MockHttpServletRequest req = loginRequest(null, "localhost", null);
        req.addHeader("Referer", "https://evil.example/t");
        ResponseEntity<byte[]> entity = controller.proxy(req);

        assertEquals(403, entity.getStatusCode().value());
        assertEquals("application/json", entity.getHeaders().getContentType().toString());
        String body = new String(entity.getBody(), StandardCharsets.UTF_8);
        assertTrue(body.contains("\"code\":\"FORBIDDEN\""), "body: " + body);
        assertTrue(recorded.isEmpty(), "upstream must not be called");
    }

    @Test
    void postLoginWithMalformedOriginIsForbidden() throws Exception {
        nextResponse = new ResponseSpec(200, "{\"accessToken\":\"a1\"}", "application/json");
        MockHttpServletRequest req = loginRequest("http://[::1", "localhost", null);
        ResponseEntity<byte[]> entity = controller(false).proxy(req);
        assertEquals(403, entity.getStatusCode().value());
        assertTrue(new String(entity.getBody(), StandardCharsets.UTF_8).contains("\"code\":\"FORBIDDEN\""));
        assertTrue(recorded.isEmpty());
    }

    @Test
    void postLoginWithNullHostOriginIsForbidden() throws Exception {
        nextResponse = new ResponseSpec(200, "{\"accessToken\":\"a1\"}", "application/json");
        MockHttpServletRequest req = loginRequest("mailto:someone@example.com", "localhost", null);
        ResponseEntity<byte[]> entity = controller(false).proxy(req);
        assertEquals(403, entity.getStatusCode().value());
        assertTrue(new String(entity.getBody(), StandardCharsets.UTF_8).contains("\"code\":\"FORBIDDEN\""));
        assertTrue(recorded.isEmpty());
    }

    @Test
    void postLoginWithOriginButNoHostHeaderIsForbidden() throws Exception {
        nextResponse = new ResponseSpec(200, "{\"accessToken\":\"a1\"}", "application/json");
        MockHttpServletRequest req = loginRequest("http://localhost", null, null);
        ResponseEntity<byte[]> entity = controller(false).proxy(req);
        assertEquals(403, entity.getStatusCode().value());
        assertTrue(new String(entity.getBody(), StandardCharsets.UTF_8).contains("\"code\":\"FORBIDDEN\""));
        assertTrue(recorded.isEmpty());
    }

    @Test
    void postLoginWithPortInHostHeaderIsAllowed() throws Exception {
        nextResponse = new ResponseSpec(200, "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":3600,\"tokenType\":\"Bearer\"}", "application/json");
        MockHttpServletRequest req = loginRequest("http://localhost:9000", "localhost:8080", null);
        ResponseEntity<byte[]> entity = controller(false).proxy(req);
        assertEquals(200, entity.getStatusCode().value());
        assertEquals(1, recorded.size());
    }

    static final class Recorded {
        final String method;
        final String path;
        final String authorization;
        final String body;

        Recorded(String method, String path, String authorization, String body) {
            this.method = method;
            this.path = path;
            this.authorization = authorization;
            this.body = body;
        }
    }

    static final class ResponseSpec {
        final int status;
        final String body;
        final String contentType;

        ResponseSpec(int status, String body) {
            this(status, body, null);
        }

        ResponseSpec(int status, String body, String contentType) {
            this.status = status;
            this.body = body;
            this.contentType = contentType;
        }
    }
}