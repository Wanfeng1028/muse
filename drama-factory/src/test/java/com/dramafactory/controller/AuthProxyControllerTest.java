package com.dramafactory.controller;

import com.sun.net.httpserver.HttpServer;
import jakarta.servlet.http.Cookie;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.http.ResponseEntity;
import org.springframework.mock.web.MockHttpServletRequest;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import jakarta.servlet.http.HttpServletRequest;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import org.springframework.http.HttpHeaders;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class AuthProxyControllerTest {

    private HttpServer server;
    private int port;
    private AuthProxyController controller;

    private final AtomicInteger requestCount = new AtomicInteger(0);
    private final List<RecordedRequest> recorded = new ArrayList<>();
    private volatile ResponseSpec responseSpec;

    private static final class RecordedRequest {
        String method;
        String path;
        String query;
        Map<String, List<String>> headers;
        byte[] body;
    }

    private static final class ResponseSpec {
        int status;
        byte[] body;
        Map<String, List<String>> headers;

        ResponseSpec(int status, String body) {
            this.status = status;
            this.body = body.getBytes(StandardCharsets.UTF_8);
            this.headers = Map.of();
        }
    }

    @BeforeEach
    void setUp() throws IOException {
        requestCount.set(0);
        recorded.clear();
        responseSpec = new ResponseSpec(200, "");
        server = HttpServer.create(new InetSocketAddress("::1", 0), 0);
        server.createContext("/", exchange -> {
            requestCount.incrementAndGet();
            RecordedRequest rr = new RecordedRequest();
            rr.method = exchange.getRequestMethod();
            rr.path = exchange.getRequestURI().getPath();
            rr.query = exchange.getRequestURI().getQuery();
            rr.headers = exchange.getRequestHeaders();
            byte[] body;
            try (InputStream in = exchange.getRequestBody()) {
                body = in.readAllBytes();
            }
            rr.body = body;
            recorded.add(rr);

            ResponseSpec spec = responseSpec;
            for (Map.Entry<String, List<String>> e : spec.headers.entrySet()) {
                for (String v : e.getValue()) {
                    exchange.getResponseHeaders().add(e.getKey(), v);
                }
            }
            if (spec.body.length > 0) {
                exchange.sendResponseHeaders(spec.status, spec.body.length);
                try (OutputStream os = exchange.getResponseBody()) {
                    os.write(spec.body);
                }
            } else {
                exchange.sendResponseHeaders(spec.status, -1);
                exchange.close();
            }
        });
        server.start();
        port = server.getAddress().getPort();
    }

    @AfterEach
    void tearDown() {
        if (server != null) {
            server.stop(0);
        }
    }

    private AuthProxyController newController() {
        return new AuthProxyController("http://[::1]:" + port, HttpClient.newHttpClient());
    }

    private MockHttpServletRequest request(String method, String uri) {
        return new MockHttpServletRequest(method, uri);
    }

    private RecordedRequest last() {
        return recorded.get(recorded.size() - 1);
    }

    private static String headerValue(Map<String, List<String>> headers, String name) {
        if (headers == null) {
            return null;
        }
        for (Map.Entry<String, List<String>> e : headers.entrySet()) {
            if (e.getKey().equalsIgnoreCase(name)) {
                return e.getValue().isEmpty() ? null : e.getValue().get(0);
            }
        }
        return null;
    }

    private static boolean hasHeader(Map<String, List<String>> headers, String name) {
        return headerValue(headers, name) != null;
    }

    private static String bodyString(ResponseEntity<byte[]> resp) {
        return resp.getBody() == null ? "" : new String(resp.getBody(), StandardCharsets.UTF_8);
    }

    @Test
    void T1_透传基本链路() {
        responseSpec = new ResponseSpec(200, "resp-ok");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/me");
        req.setContent("{\"a\":1}".getBytes(StandardCharsets.UTF_8));
        req.addHeader("Authorization", "Bearer abc");
        req.addHeader("X-Foo", "bar");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals("resp-ok", bodyString(resp));
        assertEquals(1, recorded.size());
        RecordedRequest rr = last();
        assertEquals("POST", rr.method);
        assertEquals("/api/auth/me", rr.path);
        assertArrayEquals("{\"a\":1}".getBytes(StandardCharsets.UTF_8), rr.body);
        assertEquals("Bearer abc", headerValue(rr.headers, "Authorization"));
        assertEquals("bar", headerValue(rr.headers, "X-Foo"));
    }

    @Test
    void T2_query拼进目标URL() {
        controller = newController();
        MockHttpServletRequest req = request("GET", "/api/auth/users");
        req.setQueryString("a=1&b=2");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals(1, recorded.size());
        assertEquals("a=1&b=2", last().query);
        assertEquals("/api/auth/users", last().path);
    }

    @Test
    void T3_hopByHop请求头被过滤() {
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/me");
        req.addHeader("Host", "evil");
        req.addHeader("Connection", "keep-alive");
        req.addHeader("Cookie", "x=1");
        req.addHeader("Content-Length", "5");
        req.addHeader("X-Keep", "yes");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        RecordedRequest rr = last();
        // 注意：java.net.http.HttpClient 会自动补 Host/Content-Length，
        // 这里断言的是"客户端伪造的值没有被透传"，而非头完全不存在
        assertNotEquals("evil", headerValue(rr.headers, "Host"), "伪造的 Host 不许透传");
        // 注意：java.net.http.HttpClient 默认会发 h2c 升级用的 Connection: Upgrade, HTTP2-Settings，
        // 这里断言的是"客户端伪造的 keep-alive 值没有被透传"，而非头完全不存在
        assertNotEquals("keep-alive", headerValue(rr.headers, "Connection"), "伪造的 Connection 不许透传");
        assertFalse(hasHeader(rr.headers, "Cookie"), "Cookie 请求头不许透传（走 df_at/df_rt 语义）");
        assertNotEquals("5", headerValue(rr.headers, "Content-Length"), "伪造的 Content-Length 不许透传");
        assertEquals("yes", headerValue(rr.headers, "X-Keep"));
    }

    @Test
    void T4_无Authorization头时用df_at_cookie() {
        controller = newController();
        MockHttpServletRequest req = request("GET", "/api/auth/me");
        req.setCookies(new Cookie("df_at", "tok123"));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals("Bearer tok123", headerValue(last().headers, "Authorization"));
    }

    @Test
    void T5_Authorization头优先于cookie() {
        controller = newController();
        MockHttpServletRequest req = request("GET", "/api/auth/me");
        req.addHeader("Authorization", "Bearer head-token");
        req.setCookies(new Cookie("df_at", "cookie-token"));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals("Bearer head-token", headerValue(last().headers, "Authorization"));
    }

    @Test
    void T6_refresh无cookie返回401() {
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/refresh");
        req.setContent("{\"x\":1}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(401, resp.getStatusCode().value());
        String body = bodyString(resp);
        assertTrue(body.contains("UNAUTHORIZED"), "body should contain UNAUTHORIZED: " + body);
        assertTrue(body.contains("未登录"), "body should contain 未登录: " + body);
        assertEquals(0, requestCount.get(), "upstream must not be called");
    }

    @Test
    void T7_refresh有cookie则body被替换() {
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/refresh");
        req.setContent("{\"x\":9}".getBytes(StandardCharsets.UTF_8));
        req.setCookies(new Cookie("df_rt", "rt-abc"));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals(1, recorded.size());
        assertEquals("{\"refreshToken\":\"rt-abc\"}", new String(last().body, StandardCharsets.UTF_8));
    }

    @Test
    void T8_GET无body走noBody() {
        controller = newController();
        MockHttpServletRequest req = request("GET", "/api/auth/me");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals(1, recorded.size());
        assertEquals(0, last().body.length);
    }

    @Test
    void T9_上游500原样透传() {
        responseSpec = new ResponseSpec(500, "boom");
        controller = newController();
        MockHttpServletRequest req = request("GET", "/api/auth/me");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(500, resp.getStatusCode().value());
        assertEquals("boom", bodyString(resp));
    }

    @Test
    void T10_构造器去掉尾部斜杠() {
        controller = new AuthProxyController("http://[::1]:" + port + "/", HttpClient.newHttpClient());
        MockHttpServletRequest req = request("GET", "/api/auth/me");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals(1, recorded.size());
        assertEquals("/api/auth/me", last().path);
        assertFalse(last().path.startsWith("//"), "path must not start with //: " + last().path);
    }

    @Test
    void T11_login成功剥离token写cookie() {
        responseSpec = new ResponseSpec(200,
                "{\"accessToken\":\"a1\",\"refreshToken\":\"r1\",\"expiresIn\":7200}");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/login");
        req.setContent("{\"u\":\"x\"}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        String body = bodyString(resp);
        assertEquals("{\"ok\":true}", body);
        assertFalse(body.contains("a1"), "body must not contain access token");
        assertFalse(body.contains("r1"), "body must not contain refresh token");

        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertTrue(setCookies != null && !setCookies.isEmpty(), "Set-Cookie must be present");
        String at = null;
        String rt = null;
        for (String c : setCookies) {
            if (c.contains("df_at=a1")) {
                at = c;
            }
            if (c.contains("df_rt=r1")) {
                rt = c;
            }
        }
        assertTrue(at != null, "df_at cookie missing: " + setCookies);
        assertTrue(at.contains("Path=/"), "df_at Path=/ : " + at);
        assertTrue(at.contains("Max-Age=7200"), "df_at Max-Age=7200 : " + at);
        assertTrue(at.contains("HttpOnly"), "df_at HttpOnly : " + at);
        assertTrue(rt != null, "df_rt cookie missing: " + setCookies);
        assertTrue(rt.contains("Path=/api/auth"), "df_rt Path=/api/auth : " + rt);
        assertTrue(rt.contains("Max-Age=604800"), "df_rt Max-Age=604800 : " + rt);
    }

    @Test
    void T12_login无expiresIn默认3600() {
        responseSpec = new ResponseSpec(200,
                "{\"accessToken\":\"a2\",\"refreshToken\":\"r2\"}");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/login");
        req.setContent("{}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertTrue(setCookies != null && !setCookies.isEmpty(), "Set-Cookie must be present");
        String at = null;
        for (String c : setCookies) {
            if (c.contains("df_at=a2")) {
                at = c;
            }
        }
        assertTrue(at != null, "df_at cookie missing: " + setCookies);
        assertTrue(at.contains("Max-Age=3600"), "df_at Max-Age=3600 : " + at);
    }

    @Test
    void T13_login上游体非JSON转502() {
        responseSpec = new ResponseSpec(200, "not-json{{{");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/login");
        req.setContent("{}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(502, resp.getStatusCode().value());
        assertTrue(bodyString(resp).contains("AUTH_UPSTREAM_UNAVAILABLE"),
                "body should contain AUTH_UPSTREAM_UNAVAILABLE: " + bodyString(resp));
    }

    @Test
    void T14_login上游400原样透传() {
        responseSpec = new ResponseSpec(400, "{\"code\":\"BAD\"}");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/login");
        req.setContent("{}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(400, resp.getStatusCode().value());
        assertEquals("{\"code\":\"BAD\"}", bodyString(resp));
        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertTrue(setCookies == null || setCookies.isEmpty(), "Set-Cookie should be empty: " + setCookies);
    }

    @Test
    void T15_oauth回调同样剥离() {
        responseSpec = new ResponseSpec(200,
                "{\"accessToken\":\"oa\",\"refreshToken\":\"or\",\"expiresIn\":600}");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/oauth/github/callback");
        req.setContent("{\"code\":\"c\"}".getBytes(StandardCharsets.UTF_8));

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals("{\"ok\":true}", bodyString(resp));
        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertTrue(setCookies != null && !setCookies.isEmpty(), "Set-Cookie must be present");
        boolean at = false;
        boolean rt = false;
        for (String c : setCookies) {
            if (c.contains("df_at=oa")) {
                at = true;
            }
            if (c.contains("df_rt=or")) {
                rt = true;
            }
        }
        assertTrue(at, "df_at=oa cookie missing: " + setCookies);
        assertTrue(rt, "df_rt=or cookie missing: " + setCookies);
    }

    @Test
    void T16_logout成功清cookie() {
        responseSpec = new ResponseSpec(200, "{}");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/logout");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(200, resp.getStatusCode().value());
        assertEquals("{\"ok\":true}", bodyString(resp));
        List<String> setCookies = resp.getHeaders().get(HttpHeaders.SET_COOKIE);
        assertTrue(setCookies != null && !setCookies.isEmpty(), "Set-Cookie must be present");
        boolean at = false;
        boolean rt = false;
        for (String c : setCookies) {
            if (c.contains("df_at=") && c.contains("Max-Age=0")) {
                at = true;
            }
            if (c.contains("df_rt=") && c.contains("Max-Age=0")) {
                rt = true;
            }
        }
        assertTrue(at, "df_at clear cookie missing: " + setCookies);
        assertTrue(rt, "df_rt clear cookie missing: " + setCookies);
    }

    @Test
    void T17_logout上游500原样透传() {
        responseSpec = new ResponseSpec(500, "err");
        controller = newController();
        MockHttpServletRequest req = request("POST", "/api/auth/logout");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(500, resp.getStatusCode().value());
        assertEquals("err", bodyString(resp));
    }

    @Test
    void T18_send抛IOException转502() throws Exception {
        HttpClient mockClient = mock(HttpClient.class);
        when(mockClient.send(ArgumentMatchers.<HttpRequest>any(),
                ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenThrow(new IOException("boom"));
        controller = new AuthProxyController("http://[::1]:" + port, mockClient);
        MockHttpServletRequest req = request("GET", "/api/auth/me");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(502, resp.getStatusCode().value());
        assertTrue(bodyString(resp).contains("AUTH_UPSTREAM_UNAVAILABLE"),
                "body should contain AUTH_UPSTREAM_UNAVAILABLE: " + bodyString(resp));
    }

    @Test
    void T19_send抛InterruptedException转502并置中断标记() throws Exception {
        HttpClient mockClient = mock(HttpClient.class);
        when(mockClient.send(ArgumentMatchers.<HttpRequest>any(),
                ArgumentMatchers.<HttpResponse.BodyHandler<byte[]>>any()))
                .thenThrow(new InterruptedException("interrupted"));
        controller = new AuthProxyController("http://[::1]:" + port, mockClient);
        MockHttpServletRequest req = request("GET", "/api/auth/me");

        ResponseEntity<byte[]> resp = controller.proxy(req);

        assertEquals(502, resp.getStatusCode().value());
        assertTrue(Thread.currentThread().isInterrupted(), "interrupt flag should be set");
        Thread.interrupted();
    }

    @Test
    void T20_读请求体抛IOException转502() throws Exception {
        HttpServletRequest mockReq = mock(HttpServletRequest.class);
        when(mockReq.getMethod()).thenReturn("GET");
        when(mockReq.getRequestURI()).thenReturn("/api/auth/me");
        when(mockReq.getContextPath()).thenReturn("");
        when(mockReq.getInputStream()).thenThrow(new IOException("read-fail"));
        controller = newController();

        ResponseEntity<byte[]> resp = controller.proxy(mockReq);

        assertEquals(502, resp.getStatusCode().value());
    }
}
