package com.dramafactory.service.skill;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.net.JarURLConnection;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Enumeration;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;
import java.util.regex.Pattern;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

@Service
public class SkillInstallService {

    private static final Logger log = LoggerFactory.getLogger(SkillInstallService.class);
    private static final Pattern ID_PATTERN = Pattern.compile("^[a-z0-9][a-z0-9._-]*$");

    private final SkillRegistry registry;
    private final SkillHubClient hubClient;
    private final Path skillsDir;
    private final Path normalizedSkillsDir;

    public SkillInstallService(SkillRegistry registry,
                               SkillHubClient hubClient,
                               @Value("${drama.skills.dir:data/skills}") String skillsDir) {
        this.registry = registry;
        this.hubClient = hubClient;
        this.skillsDir = Paths.get(skillsDir);
        this.normalizedSkillsDir = this.skillsDir.toAbsolutePath().normalize();
    }

    public record InstallResult(String id, String version, boolean alreadyInstalled, String source) {
    }

    public InstallResult install(String id, String version) {
        checkId(id);
        Optional<SkillDescriptor> bundled = registry.bundledOf(id);
        if (bundled.isPresent()) {
            return installBundled(bundled.get(), version);
        }
        if (hubClient.isEnabled()) {
            return installFromHub(id, version);
        }
        throw new IllegalArgumentException("未知的 skill: " + id + "（非内置且 skillhub 未启用）");
    }

    private InstallResult installBundled(SkillDescriptor descriptor, String version) {
        String id = descriptor.getId();
        String targetVersion = (version == null || version.isBlank()) ? descriptor.getVersion() : version.trim();
        if (version != null && !version.isBlank() && !version.trim().equals(descriptor.getVersion())) {
            throw new IllegalArgumentException(
                    "内置 skill 仅提供版本 " + descriptor.getVersion() + "：id=" + id);
        }
        Optional<SkillRegistry.InstalledSkill> existing = registry.installedOf(id);
        if (existing.isPresent()
                && SkillDescriptor.compareVersions(existing.get().version(), targetVersion) == 0) {
            log.info("内置 skill 已安装且版本一致，跳过: id={}, version={}", id, targetVersion);
            return new InstallResult(id, targetVersion, true, "bundled");
        }
        Path staging = skillsDir.resolve(".staging-" + id + "-" + UUID.randomUUID());
        try {
            copyBundledToStaging(id, staging);
            validateStaged(staging, id);
            moveIntoPlace(staging, id);
        } catch (RuntimeException | IOException e) {
            deleteQuietly(staging);
            if (e instanceof IllegalArgumentException || e instanceof IllegalStateException) {
                throw (RuntimeException) e;
            }
            throw new IllegalStateException("安装内置 skill 失败: " + id + "（" + e.getMessage() + "）", e);
        }
        log.info("内置 skill 安装完成: id={}, version={}", id, targetVersion);
        return new InstallResult(id, targetVersion, false, "bundled");
    }

    private void copyBundledToStaging(String id, Path staging) throws IOException {
        URL url = getClass().getResource("/skills-bundled/" + id);
        if (url == null) {
            throw new IllegalStateException("内置 skill 资源缺失: " + id);
        }
        String protocol = url.getProtocol();
        if ("file".equals(protocol)) {
            Path srcDir;
            try {
                srcDir = Paths.get(url.toURI());
            } catch (URISyntaxException e) {
                throw new IOException("内置 skill 资源路径非法: " + id, e);
            }
            try (Stream<Path> walk = Files.walk(srcDir)) {
                walk.filter(Files::isRegularFile).forEach(p -> {
                    Path rel = srcDir.relativize(p);
                    Path dest = staging.resolve(rel.toString()).normalize();
                    if (!dest.startsWith(staging.toAbsolutePath().normalize()))
                        throw new IllegalStateException("内置 skill 含非法路径: " + rel);
                    try {
                        Files.createDirectories(dest.getParent());
                        Files.copy(p, dest);
                    } catch (IOException e) {
                        throw new UncheckedIOException(e);
                    }
                });
            }
        } else if ("jar".equals(url.getProtocol())) {
            JarURLConnection conn = (JarURLConnection) url.openConnection();
            try (JarFile jar = conn.getJarFile()) {
                String prefix = "skills-bundled/" + id + "/";
                Path base = staging.toAbsolutePath().normalize();
                Enumeration<JarEntry> en = jar.entries();
                while (en.hasMoreElements()) {
                    JarEntry e = en.nextElement();
                    String name = e.getName();
                    if (!name.startsWith(prefix) || e.isDirectory()) continue;
                    Path dest = base.resolve(name.substring(prefix.length())).normalize();
                    if (!dest.startsWith(base))
                        throw new IllegalStateException("内置 skill 含非法路径: " + name);
                    Files.createDirectories(dest.getParent());
                    try (InputStream in = jar.getInputStream(e)) {
                        Files.copy(in, dest);
                    }
                }
            }
        } else {
            throw new IllegalStateException("不支持的资源协议: " + url.getProtocol());
        }
    }

    private String validateStaged(Path staging, String id) throws IOException {
        Path md = staging.resolve("SKILL.md");
        if (!Files.isRegularFile(md))
            throw new IllegalStateException("skill 包缺少 SKILL.md: " + id);
        String content = Files.readString(md, StandardCharsets.UTF_8);
        try {
            SkillDescriptor d = SkillDescriptor.fromFrontmatter(
                    id, content, SkillDescriptor.Source.SKILLHUB, "", null);
            return d.getVersion();
        } catch (IllegalArgumentException e) {
            throw new IllegalStateException(
                    "SKILL.md 非法: " + id + "（" + e.getMessage() + "）", e);
        }
    }

    private void moveIntoPlace(Path staging, String id) throws IOException {
        Path target = skillsDir.resolve(id).toAbsolutePath().normalize();
        if (!target.startsWith(normalizedSkillsDir))
            throw new IllegalStateException("安装路径逃逸: " + id);
        try {
            Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
        } catch (AtomicMoveNotSupportedException ex) {
            Files.move(staging, target, StandardCopyOption.REPLACE_EXISTING);
        }
    }
    private InstallResult installFromHub(String id, String version) {
        List<SkillHubClient.HubSkill> all = hubClient.fetchSkills();
        List<SkillHubClient.HubSkill> cands = new ArrayList<>();
        for (SkillHubClient.HubSkill s : all) {
            if (id.equals(s.id())) {
                cands.add(s);
            }
        }
        if (cands.isEmpty()) {
            throw new IllegalArgumentException("skillhub 未收录 skill: " + id);
        }
        SkillHubClient.HubSkill sel;
        if (version == null || version.isBlank()) {
            sel = cands.get(0);
            for (SkillHubClient.HubSkill s : cands) {
                if (SkillDescriptor.compareVersions(s.version(), sel.version()) > 0) {
                    sel = s;
                }
            }
        } else {
            String v = version.trim();
            sel = null;
            for (SkillHubClient.HubSkill s : cands) {
                if (v.equals(s.version())) {
                    sel = s;
                    break;
                }
            }
            if (sel == null) {
                throw new IllegalArgumentException("skillhub 无此版本: " + id + "@" + v);
            }
        }
        Optional<SkillRegistry.InstalledSkill> existing = registry.installedOf(id);
        if (existing.isPresent()
                && SkillDescriptor.compareVersions(existing.get().version(), sel.version()) == 0) {
            log.info("skill 已安装且版本一致，跳过: {}@{}", id, sel.version());
            return new InstallResult(id, sel.version(), true, "skillhub");
        }
        Path staging = skillsDir.resolve(".staging-" + id + "-" + UUID.randomUUID());
        try {
            Path zip = hubClient.downloadPackage(sel, skillsDir);
            try {
                unzip(zip, staging);
            } finally {
                Files.deleteIfExists(zip);
            }
            validateStaged(staging, id);
            moveIntoPlace(staging, id);
        } catch (IOException | RuntimeException e) {
            deleteQuietly(staging);
            if (e instanceof RuntimeException re) {
                throw re;
            }
            throw new IllegalStateException("从 skillhub 安装失败: " + id + "（" + e.getMessage() + "）", e);
        }
        return new InstallResult(id, sel.version(), false, "skillhub");
    }

    private void unzip(Path zip, Path staging) throws IOException {
        try (ZipInputStream in = new ZipInputStream(Files.newInputStream(zip))) {
            ZipEntry entry;
            Path base = staging.toAbsolutePath().normalize();
            while ((entry = in.getNextEntry()) != null) {
                Path dest = base.resolve(entry.getName()).normalize();
                if (!dest.startsWith(base)) {
                    throw new IllegalStateException("zip 含非法路径，已拒绝解压: " + entry.getName());
                }
                if (entry.isDirectory()) {
                    Files.createDirectories(dest);
                } else {
                    Files.createDirectories(dest.getParent());
                    Files.copy(in, dest);
                }
                in.closeEntry();
            }
        }
    }

    public boolean uninstall(String id) {
        checkId(id);
        Path target = skillsDir.resolve(id).toAbsolutePath().normalize();
        if (!target.startsWith(normalizedSkillsDir)) {
            throw new IllegalStateException("路径逃逸: " + id);
        }
        if (!Files.isDirectory(target)) {
            return false;
        }
        try {
            deleteRecursively(target);
        } catch (IOException e) {
            throw new IllegalStateException("卸载失败: " + id, e);
        }
        log.info("已卸载 skill: {}", id);
        return true;
    }

    private static void deleteQuietly(Path p) {
        try {
            deleteRecursively(p);
        } catch (Exception ignored) {
        }
    }

    private static void deleteRecursively(Path p) throws IOException {
        if (!Files.exists(p)) {
            return;
        }
        try (Stream<Path> walk = Files.walk(p)) {
            List<Path> paths = walk.sorted(Comparator.reverseOrder()).toList();
            for (Path q : paths) {
                Files.deleteIfExists(q);
            }
        }
    }

    private static void checkId(String id) {
        if (id == null || !ID_PATTERN.matcher(id).matches()) {
            throw new IllegalArgumentException("非法 skill id: " + id);
        }
    }
}
