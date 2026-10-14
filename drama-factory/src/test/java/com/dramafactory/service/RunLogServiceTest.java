package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RunLogServiceTest {

    @TempDir
    Path tempDir;

    private RunLogService newService() {
        return new RunLogService(tempDir.toString());
    }

    // ---------- R1 ----------
    @Test
    void append_writesTimestampedLine() throws Exception {
        RunLogService service = newService();

        service.append(1L, 2, "hello");

        Path file = tempDir.resolve("run-1").resolve("step-2.log");
        assertTrue(Files.exists(file));
        String content = Files.readString(file, StandardCharsets.UTF_8);
        assertTrue(content.matches("^\\[\\d{2}:\\d{2}:\\d{2}\\] hello\\R$"));
    }

    // ---------- R2 ----------
    @Test
    void append_nullLine() throws Exception {
        RunLogService service = newService();

        service.append(1L, 2, null);

        Path file = tempDir.resolve("run-1").resolve("step-2.log");
        String content = Files.readString(file, StandardCharsets.UTF_8);
        assertFalse(content.contains("null"));
    }

    // ---------- R3 ----------
    @Test
    void append_nullRunId_throws() {
        RunLogService service = newService();

        assertThrows(IllegalArgumentException.class, () -> service.append(null, 1, "x"));
    }

    @Test
    void append_nullSeqNo_throws() {
        RunLogService service = newService();

        assertThrows(IllegalArgumentException.class, () -> service.append(1L, null, "x"));
    }

    // ---------- R4 ----------
    @Test
    void append_negativeIds_throw() {
        RunLogService service = newService();

        IllegalArgumentException ex1 = assertThrows(IllegalArgumentException.class,
                () -> service.append(-1L, 1, "x"));
        assertTrue(ex1.getMessage().contains("纯数字"));

        IllegalArgumentException ex2 = assertThrows(IllegalArgumentException.class,
                () -> service.append(1L, -2, "x"));
        assertTrue(ex2.getMessage().contains("纯数字"));
    }

    // ---------- R5 ----------
    @Test
    void read_missingFile() {
        RunLogService service = newService();

        RunLogService.LogReadResult r = service.read(9L, 9, 0);

        assertEquals("", r.content());
        assertEquals(0L, r.nextOffset());
        assertTrue(r.eof());
    }

    // ---------- R6 ----------
    @Test
    void read_negativeOffset() {
        RunLogService service = newService();
        service.append(1L, 2, "hello");

        RunLogService.LogReadResult negative = service.read(1L, 2, -10);
        RunLogService.LogReadResult zero = service.read(1L, 2, 0);

        assertEquals(zero.content(), negative.content());
    }

    // ---------- R7 ----------
    @Test
    void read_full_eof() throws Exception {
        RunLogService service = newService();
        service.append(1L, 2, "hello");

        RunLogService.LogReadResult r = service.read(1L, 2, 0);

        assertTrue(r.eof());
        assertTrue(r.content().contains("hello"));
        Path file = tempDir.resolve("run-1").resolve("step-2.log");
        assertEquals(Files.size(file), r.nextOffset());
    }

    // ---------- R8 ----------
    @Test
    void read_partial_notEof() throws Exception {
        RunLogService service = newService();
        StringBuilder expected = new StringBuilder();
        for (int i = 0; i < 3000; i++) {
            String line = "line-" + i + "-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx";
            service.append(1L, 2, line);
            expected.append(line);
        }
        Path file = tempDir.resolve("run-1").resolve("step-2.log");
        assertTrue(Files.size(file) > 64L * 1024L);

        RunLogService.LogReadResult r1 = service.read(1L, 2, 0);
        assertEquals(65536, r1.content().length());
        assertFalse(r1.eof());

        RunLogService.LogReadResult r2 = service.read(1L, 2, r1.nextOffset());
        assertEquals(65536, r1.content().length());
        assertFalse(r1.eof());
        assertTrue(r2.content().length() > 0);
        assertEquals(r1.nextOffset() + r2.content().length(),
                r1.content().length() + r2.content().length());
    }

    // ---------- R9 ----------
    @Test
    void read_offsetPastEnd() throws Exception {
        RunLogService service = newService();
        service.append(1L, 2, "hello");

        RunLogService.LogReadResult r = service.read(1L, 2, 10_000_000L);

        assertEquals("", r.content());
        assertTrue(r.eof());
        Path file = tempDir.resolve("run-1").resolve("step-2.log");
        assertEquals(Files.size(file), r.nextOffset());
    }

    // ---------- R10 ----------
    @Test
    void read_nullIds_throw() {
        RunLogService service = newService();

        assertThrows(IllegalArgumentException.class, () -> service.read(null, 1, 0));
    }

    // ---------- R11 ----------
    @Test
    void append_twice() {
        RunLogService service = newService();
        service.append(1L, 2, "first-line");
        service.append(1L, 2, "second-line");

        RunLogService.LogReadResult r = service.read(1L, 2, 0);

        assertTrue(r.content().contains("first-line"));
        assertTrue(r.content().contains("second-line"));
    }
}
