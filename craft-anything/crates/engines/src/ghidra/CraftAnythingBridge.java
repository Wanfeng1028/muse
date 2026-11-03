// Craft Anything headless bridge for Ghidra (our own clean-room implementation).
//
// Run as a Ghidra post-script: analyzeHeadless ... -postScript CraftAnythingBridge.java <descriptor>
//
// It opens a loopback TCP socket, writes {"host","port"} to the endpoint file named in the
// descriptor, accepts exactly one client, and answers newline-delimited JSON requests. Every
// request must carry the run token from the descriptor; the token is compared in constant time.
// The saved analysis is opened -readOnly: a function made on demand (code the analysis never made a
// function, e.g. reached only through tables of pointers) lives in memory for this run and is never
// saved. This file names no third-party product and copies no code.
//
// Protocol:
//   request:  {"id":<int>,"token":"<hex>","method":"<name>","params":{...}}
//   response: {"id":<int>,"ok":true,"result":<json>} | {"id":<int>,"ok":false,"error":{"code","message"}}
//
// Methods: ping, shutdown, native_functions_list, native_function_address, native_function_pseudocode.
//
//@category CraftAnything

import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.cmd.function.CreateFunctionCmd;
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import ghidra.program.model.address.Address;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.util.task.TimeoutTaskMonitor;

import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.concurrent.TimeUnit;

public class CraftAnythingBridge extends GhidraScript {

    /** How long making a function on demand may take before the bridge gives up. */
    private static final long CREATE_SECONDS = 60;

    private String token = "";
    /** Entry points of the functions this run made on demand. */
    private final Set<Address> made = new HashSet<>();
    private DecompInterface decompiler;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length < 1) {
            println("CraftAnythingBridge: missing descriptor path");
            return;
        }
        String descriptorText = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        this.token = jsonString(descriptorText, "token");
        String endpointPath = jsonString(descriptorText, "endpoint_path");

        decompiler = new DecompInterface();
        decompiler.openProgram(currentProgram);

        // Loopback only; port chosen by the OS.
        ServerSocket server = new ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"));
        try {
            int port = server.getLocalPort();
            writeEndpoint(endpointPath, port);
            server.setSoTimeout(300000); // never block forever waiting for the one client
            Socket client = server.accept();
            serve(client);
        } finally {
            server.close();
            if (decompiler != null) {
                decompiler.dispose();
            }
        }
    }

    private void serve(Socket client) throws Exception {
        BufferedReader in = new BufferedReader(new InputStreamReader(client.getInputStream(), StandardCharsets.UTF_8));
        BufferedWriter out = new BufferedWriter(new OutputStreamWriter(client.getOutputStream(), StandardCharsets.UTF_8));
        String line;
        while ((line = in.readLine()) != null) {
            if (line.trim().isEmpty()) {
                continue;
            }
            long id = jsonLong(line, "id", 0);
            String reqToken = jsonString(line, "token");
            String method = jsonString(line, "method");
            if (!tokensMatch(reqToken, this.token)) {
                writeError(out, id, "bad_input", "bad token");
                break; // close on a bad token
            }
            if ("shutdown".equals(method)) {
                writeResult(out, id, "{\"shutdown\":true,\"temporary_project\":true}");
                break;
            }
            try {
                String result = dispatch(method, line);
                if (result == null) {
                    writeError(out, id, "not_found", "no such item");
                } else {
                    writeResult(out, id, result);
                }
            } catch (NotFound e) {
                writeError(out, id, "not_found", e.getMessage());
            } catch (Exception e) {
                writeError(out, id, "bridge_error", safe(e.getMessage()));
            }
        }
        client.close();
    }

    /** A lookup that found nothing; the message says why. */
    private static final class NotFound extends Exception {
        NotFound(String why) {
            super(why);
        }
    }

    private String dispatch(String method, String line) throws NotFound {
        if ("ping".equals(method)) {
            String version = currentProgram != null ? "" : "";
            return "{\"name\":\"CraftAnything bridge\",\"provider\":{\"id\":\"ghidra\",\"version\":\""
                + jsonEscape(ghidra.framework.Application.getApplicationVersion())
                + "\"},\"read_only\":true,\"analysed\":true,\"analysis_cut_short\":false,\"target\":{\"name\":\""
                + jsonEscape(currentProgram.getName()) + "\",\"image_base\":\"0x"
                + Long.toHexString(currentProgram.getImageBase().getOffset()) + "\"}}";
        }
        if ("native_functions_list".equals(method)) {
            StringBuilder sb = new StringBuilder("{\"functions\":[");
            FunctionManager fm = currentProgram.getFunctionManager();
            boolean first = true;
            for (Function f : fm.getFunctions(true)) {
                if (!first) sb.append(",");
                first = false;
                sb.append("{\"name\":\"").append(jsonEscape(f.getName())).append("\",\"address\":\"0x")
                  .append(f.getEntryPoint().toString()).append("\"}");
            }
            sb.append("]}");
            return sb.toString();
        }
        if ("native_function_address".equals(method)) {
            String name = jsonString(line, "function");
            Function f = findByName(name);
            if (f == null) return null;
            return "{\"name\":\"" + jsonEscape(f.getName()) + "\",\"address\":\"0x" + f.getEntryPoint().toString() + "\"}";
        }
        if ("native_function_pseudocode".equals(method)) {
            Function f = resolveFunction(line);
            if (f == null) {
                Address a = addressOf(jsonString(line, "address"));
                if (a == null) return null;
                f = createFunctionAt(a);
                made.add(f.getEntryPoint());
            }
            DecompileResults results = decompiler.decompileFunction(f, 0, monitor);
            String c = results != null && results.getDecompiledFunction() != null
                ? results.getDecompiledFunction().getC() : null;
            if (c == null) {
                throw new IllegalStateException("the decompiler gave no result: " + safe(results == null ? null : results.getErrorMessage()));
            }
            String sig = results.getDecompiledFunction().getSignature();
            return "{\"name\":\"" + jsonEscape(f.getName()) + "\",\"address\":\"0x" + f.getEntryPoint().toString()
                + "\",\"signature\":\"" + jsonEscape(sig == null ? "" : sig) + "\",\"pseudocode\":\"" + jsonEscape(c)
                + "\",\"created\":" + made.contains(f.getEntryPoint()) + "}";
        }
        return null;
    }

    private Function resolveFunction(String line) {
        Address a = addressOf(jsonString(line, "address"));
        if (a != null) {
            Function f = currentProgram.getFunctionManager().getFunctionContaining(a);
            if (f != null) return f;
        }
        String name = jsonString(line, "function");
        return findByName(name);
    }

    private Address addressOf(String addr) {
        if (addr == null || addr.isEmpty()) return null;
        try {
            return currentProgram.getAddressFactory().getAddress(addr.replaceFirst("^0x", ""));
        } catch (Exception e) {
            return null;
        }
    }

    // The quick analysis never made a function here (e.g. code reached only through tables of
    // pointers): disassemble from the address and make one, bounded in time. In memory only.
    private Function createFunctionAt(Address a) throws NotFound {
        MemoryBlock block = currentProgram.getMemory().getBlock(a);
        if (block == null || !block.isExecute() || !block.isInitialized()) {
            throw new NotFound("the address is not in executable memory");
        }
        TimeoutTaskMonitor limit = TimeoutTaskMonitor.timeoutIn(CREATE_SECONDS, TimeUnit.SECONDS, monitor);
        int tx = currentProgram.startTransaction("Craft Anything: function on demand");
        Function f = null;
        try {
            if (currentProgram.getListing().getInstructionAt(a) == null) {
                new DisassembleCommand(a, null, true).applyTo(currentProgram, limit);
            }
            if (currentProgram.getListing().getInstructionAt(a) == null) {
                throw new NotFound(limit.didTimeout() ? "disassembling took longer than " + CREATE_SECONDS + " seconds"
                    : "Ghidra could not disassemble code at this address");
            }
            CreateFunctionCmd cmd = new CreateFunctionCmd(a);
            if (cmd.applyTo(currentProgram, limit)) f = cmd.getFunction();
            if (f == null) {
                throw new NotFound(limit.didTimeout() ? "making a function took longer than " + CREATE_SECONDS + " seconds"
                    : "Ghidra could not make a function at this address (" + safe(cmd.getStatusMsg()) + ")");
            }
            return f;
        } finally {
            currentProgram.endTransaction(tx, f != null);
        }
    }

    private Function findByName(String name) {
        if (name == null || name.isEmpty()) return null;
        List<Function> fs = getGlobalFunctions(name);
        return fs.isEmpty() ? null : fs.get(0);
    }

    // ---- tiny JSON helpers (we control both ends; no external JSON library needed) ----

    private static void writeResult(BufferedWriter out, long id, String resultJson) throws Exception {
        out.write("{\"id\":" + id + ",\"ok\":true,\"result\":" + resultJson + "}\n");
        out.flush();
    }

    private static void writeError(BufferedWriter out, long id, String code, String message) throws Exception {
        out.write("{\"id\":" + id + ",\"ok\":false,\"error\":{\"code\":\"" + code + "\",\"message\":\"" + jsonEscape(message) + "\"}}\n");
        out.flush();
    }

    private static boolean tokensMatch(String a, String b) {
        if (a == null || b == null) return false;
        byte[] x = a.getBytes(StandardCharsets.UTF_8);
        byte[] y = b.getBytes(StandardCharsets.UTF_8);
        if (x.length != y.length) return false;
        int diff = 0;
        for (int i = 0; i < x.length; i++) diff |= (x[i] ^ y[i]);
        return diff == 0;
    }

    private static void writeEndpoint(String path, int port) throws Exception {
        String json = "{\"host\":\"127.0.0.1\",\"port\":" + port + "}";
        Path target = Paths.get(path);
        Path partial = Paths.get(path + ".part");
        Files.write(partial, json.getBytes(StandardCharsets.UTF_8));
        Files.move(partial, target, java.nio.file.StandardCopyOption.ATOMIC_MOVE);
    }

    private static String safe(String s) {
        return s == null ? "" : s;
    }

    // Minimal, forgiving extractors for the flat request objects we send.
    private static String jsonString(String json, String key) {
        String needle = "\"" + key + "\"";
        int k = json.indexOf(needle);
        if (k < 0) return "";
        int colon = json.indexOf(':', k + needle.length());
        if (colon < 0) return "";
        int i = colon + 1;
        while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
        if (i >= json.length() || json.charAt(i) != '"') return "";
        i++;
        StringBuilder sb = new StringBuilder();
        while (i < json.length()) {
            char c = json.charAt(i);
            if (c == '\\' && i + 1 < json.length()) {
                char n = json.charAt(i + 1);
                switch (n) {
                    case 'n': sb.append('\n'); break;
                    case 't': sb.append('\t'); break;
                    case 'r': sb.append('\r'); break;
                    default: sb.append(n); break;
                }
                i += 2;
                continue;
            }
            if (c == '"') break;
            sb.append(c);
            i++;
        }
        return sb.toString();
    }

    private static long jsonLong(String json, String key, long dflt) {
        String needle = "\"" + key + "\"";
        int k = json.indexOf(needle);
        if (k < 0) return dflt;
        int colon = json.indexOf(':', k + needle.length());
        if (colon < 0) return dflt;
        int i = colon + 1;
        while (i < json.length() && Character.isWhitespace(json.charAt(i))) i++;
        int start = i;
        while (i < json.length() && (Character.isDigit(json.charAt(i)) || json.charAt(i) == '-')) i++;
        try {
            return Long.parseLong(json.substring(start, i));
        } catch (Exception e) {
            return dflt;
        }
    }

    private static String jsonEscape(String s) {
        if (s == null) return "";
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            switch (c) {
                case '"': sb.append("\\\""); break;
                case '\\': sb.append("\\\\"); break;
                case '\n': sb.append("\\n"); break;
                case '\r': sb.append("\\r"); break;
                case '\t': sb.append("\\t"); break;
                default:
                    if (c < 0x20) {
                        sb.append(String.format("\\u%04x", (int) c));
                    } else {
                        sb.append(c);
                    }
            }
        }
        return sb.toString();
    }
}
