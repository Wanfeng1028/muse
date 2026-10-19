package com.dramafactory.service.skill;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import static org.junit.jupiter.api.Assertions.*;

class SkillInstallServiceTest {

    private static SkillInstallService serviceFor(Path skillsDir) {
        SkillRegistry registry = new SkillRegistry(skillsDir.toString());
        SkillHubClient hub = new SkillHubClient("", url -> {
            throw new AssertionError("不应发起 HTTP");
        });
        return new SkillInstallService(registry, hub, skillsDir.toString());
    }

    private static byte[] zipBytes(String[][] entries) throws Exception {
        ByteArrayOutputStream bos = new ByteArrayOutputStream();
        try (ZipOutputStream zos = new ZipOutputStream(bos, StandardCharsets.UTF_8)) {
            for (String[] e : entries) {
                zos.putNextEntry(new ZipEntry(e[0]));
                zos.write(e[1].getBytes(StandardCharsets.UTF_8));
                zos.closeEntry();
            }
        }
        return bos.toByteArray();
    }

    @Test
    void installBundledSkill(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        SkillInstallService s = serviceFor(dir);
        SkillInstallService.InstallResult r = s.install("video-scrub", null);
        assertEquals("video-scrub", r.id());
        assertFalse(r.alreadyInstalled());
        assertEquals("bundled", r.source());
        assertEquals("1.0.0", r.version());
        assertTrue(Files.isRegularFile(dir.resolve("video-scrub/SKILL.md")));
    }

    @Test
    void installIsIdempotent(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        SkillInstallService s = serviceFor(dir);
        s.install("video-sync", null);
        SkillInstallService.InstallResult r2 = s.install("video-sync", null);
        assertTrue(r2.alreadyInstalled());
    }

    @Test
    void installUnknownIdThrows(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        SkillInstallService s = serviceFor(dir);
        assertThrows(IllegalArgumentException.class, () -> s.install("no-such-xyz", null));
    }

    @Test
    void installRewrittenSkillSucceeds(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        SkillInstallService s = serviceFor(dir);
        // 改写收录的 skill 与普通内置 skill 一样可安装
        SkillInstallService.InstallResult r = s.install("openmontage-video-edit", null);
        assertEquals("openmontage-video-edit", r.id());
        assertTrue(Files.isRegularFile(dir.resolve("openmontage-video-edit").resolve("SKILL.md")));
    }

    @Test
    void uninstallFlow(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        SkillInstallService s = serviceFor(dir);
        s.install("video-sync", null);
        assertTrue(s.uninstall("video-sync"));
        assertFalse(Files.exists(dir.resolve("video-sync")));
        assertFalse(s.uninstall("video-sync"));
    }

    @Test
    void zipSlipIsRejected(@TempDir Path tmp) throws Exception {
        Path dir = tmp.resolve("skills");
        Files.createDirectories(dir);
        byte[] evilZip = zipBytes(new String[][]{
            {"../evil.txt", "evil"},
            {"SKILL.md", "---\nname: evil\nversion: 1.0.0\n---\nbody\n"}});
        String manifest = "{\"hub\":\"t\",\"version\":1,\"skills\":[{\"id\":\"evil\",\"name\":\"evil\","
            + "\"version\":\"1.0.0\",\"description\":\"d\",\"author\":\"a\",\"license\":\"MIT\","
            + "\"packageUrl\":\"http://hub.test/evil.zip\",\"sha256\":\"\"}]}";
        SkillHubClient.SkillHttpGateway fake = url -> url.endsWith("manifest.json")
            ? new SkillHubClient.SkillHttpGateway.GatewayResponse(200, manifest.getBytes(StandardCharsets.UTF_8))
            : new SkillHubClient.SkillHttpGateway.GatewayResponse(200, evilZip);
        SkillHubClient hub = new SkillHubClient("http://hub.test", fake);
        SkillInstallService s = new SkillInstallService(new SkillRegistry(dir.toString()), hub, dir.toString());
        assertThrows(IllegalStateException.class, () -> s.install("evil", null));
        assertTrue(Files.notExists(dir.resolve("evil")));
        assertTrue(Files.notExists(tmp.resolve("evil.txt")));
    }
}
