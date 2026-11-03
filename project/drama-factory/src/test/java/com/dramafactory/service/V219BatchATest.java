package com.dramafactory.service;

import com.dramafactory.config.CurrentUser;
import com.dramafactory.config.VideoProviderConfig;
import com.dramafactory.model.Asset;
import com.dramafactory.model.DramaProject;
import com.dramafactory.model.MvSong;
import com.dramafactory.model.PromptRecipe;
import com.dramafactory.model.RecipeVisibility;
import com.dramafactory.model.VideoTask;
import com.dramafactory.repository.AssetRepository;
import com.dramafactory.service.video.VideoProvider;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.web.context.request.RequestContextHolder;
import org.springframework.web.context.request.ServletRequestAttributes;
import org.springframework.web.multipart.MultipartFile;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Path;
import java.time.LocalDateTime;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class V219BatchATest {

    /**
     * 极简 MultipartFile stub，getOriginalFilename() 严格返回 null，
     * 绕过 MockMultipartFile 将 null 规范化为 "" 的陷阱。
     */
    private static final class NullNameMultipartFile implements MultipartFile {
        private final byte[] content;

        NullNameMultipartFile(byte[] content) {
            this.content = content;
        }

        @Override
        public String getName() {
            return "f";
        }

        @Override
        public String getOriginalFilename() {
            return null;
        }

        @Override
        public String getContentType() {
            return "image/png";
        }

        @Override
        public boolean isEmpty() {
            return content.length == 0;
        }

        @Override
        public long getSize() {
            return content.length;
        }

        @Override
        public byte[] getBytes() {
            return content.clone();
        }

        @Override
        public InputStream getInputStream() {
            return new ByteArrayInputStream(content);
        }

        @Override
        public void transferTo(File dest) throws IOException, IllegalStateException {
            throw new UnsupportedOperationException("transferTo not supported in stub");
        }
    }

    @Test
    void upload_nullOriginalName_usesFallbackFileName(@TempDir Path tempDir) throws Exception {
        AssetRepository repo = mock(AssetRepository.class);
        when(repo.save(any(Asset.class))).thenAnswer(inv -> inv.getArgument(0));

        AssetService service = new AssetService(repo, tempDir.toString());

        MultipartFile file = new NullNameMultipartFile(new byte[]{1, 2, 3});
        Asset asset = service.upload(file, null, null);

        assertNotNull(asset);
        assertEquals("file", asset.getFileName());
    }

    @Test
    void currentUserId_blankUserIdAttribute_returnsLocal() {
        // 覆盖 CurrentUser 第 37 行 if (value.isBlank()) 的 true 臂。
        // 注意：ServletRequestAttributes.getRequest() 是 final 方法，Mockito 无法 stub，
        // 因此用真实 ServletRequestAttributes 包装 mock 的 HttpServletRequest。
        jakarta.servlet.http.HttpServletRequest request = mock(jakarta.servlet.http.HttpServletRequest.class);
        when(request.getAttribute("auth.userId")).thenReturn("   ");
        ServletRequestAttributes attrs = new ServletRequestAttributes(request);
        RequestContextHolder.setRequestAttributes(attrs);
        try {
            CurrentUser currentUser = new CurrentUser();
            assertEquals(CurrentUser.DEFAULT_OWNER_ID, currentUser.currentUserId());
        } finally {
            RequestContextHolder.resetRequestAttributes();
        }
    }

    @Test
    void videoProvider_nameAgnes_returnsAgnesBean() {
        VideoProviderConfig config = new VideoProviderConfig();
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider mockProvider = mock(VideoProvider.class);

        VideoProvider result = config.videoProvider("agnes", agnes, mockProvider);

        assertSame(agnes, result);
    }

    @Test
    void videoProvider_nameMock_returnsMockBean() {
        VideoProviderConfig config = new VideoProviderConfig();
        VideoProvider agnes = mock(VideoProvider.class);
        VideoProvider mockProvider = mock(VideoProvider.class);

        VideoProvider result = config.videoProvider("mock", agnes, mockProvider);

        assertSame(mockProvider, result);
    }

    @Test
    void mvSong_onCreate_createdAtNotNull_keepsOriginalValue() {
        MvSong song = new MvSong();
        LocalDateTime original = LocalDateTime.of(2020, 1, 2, 3, 4, 5);
        song.setCreatedAt(original);

        song.onCreate();

        assertEquals(original, song.getCreatedAt());
        assertNotNull(song.getUpdatedAt());
    }

    @Test
    void videoTask_prePersist_attemptsNotNull_keepsOriginalValue() {
        VideoTask task = new VideoTask();
        task.setAttempts(3);

        task.prePersist();

        assertEquals(3, task.getAttempts());
    }

    @Test
    void dramaProject_prePersist_ownerIdBlank_fallsBackToLocal() {
        DramaProject project = new DramaProject();
        project.setOwnerId(" ");

        project.prePersist();

        assertEquals("local", project.getOwnerId());
    }

    @Test
    void promptRecipe_onCreate_usageCountAndVisibilityNotNull_keepOriginalValues() {
        PromptRecipe recipe = new PromptRecipe();
        recipe.setUsageCount(7L);
        recipe.setVisibility(RecipeVisibility.PRIVATE);

        recipe.onCreate();

        assertEquals(7L, recipe.getUsageCount());
        assertEquals(RecipeVisibility.PRIVATE, recipe.getVisibility());
        assertNotNull(recipe.getCreatedAt());
        assertNotNull(recipe.getUpdatedAt());
        assertFalse(recipe.getVisibility() == RecipeVisibility.PUBLIC && recipe.getUsageCount() == 0L);
        assertTrue(recipe.getUsageCount() > 0L);
    }
}
