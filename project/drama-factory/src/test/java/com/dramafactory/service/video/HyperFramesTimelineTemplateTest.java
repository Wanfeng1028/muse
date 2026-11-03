package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import com.dramafactory.service.video.HyperFramesVideoProvider.CommandRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.lang.reflect.Field;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static org.assertj.core.api.Assertions.*;

class HyperFramesTimelineTemplateTest {

    @TempDir
    Path tempDir;

    private final CommandRunner fakeRunner = (command, workDir, timeout) -> {
        for (String arg : command) {
            if ("--version".equals(arg)) {
                return new CommandRunner.ExecResult(0, "1.0");
            }
            if ("render".equals(arg)) {
                return new CommandRunner.ExecResult(0, "");
            }
        }
        return new CommandRunner.ExecResult(1, "unknown command");
    };

    private void setField(Object obj, String fieldName, Object value) throws Exception {
        Field f = obj.getClass().getDeclaredField(fieldName);
        f.setAccessible(true);
        f.set(obj, value);
    }

    private HyperFramesVideoProvider createProvider(CommandRunner runner) throws Exception {
        HyperFramesVideoProvider provider = new HyperFramesVideoProvider(runner);
        setField(provider, "workDirBase", tempDir.toString());
        setField(provider, "enabled", true);
        return provider;
    }

    private String readCompositionHtml() throws IOException {
        Path htmlFile = Files.walk(tempDir)
                .filter(p -> p.getFileName().toString().equals("composition.html"))
                .findFirst()
                .orElseThrow(() -> new AssertionError("composition.html not found"));
        return Files.readString(htmlFile);
    }

    private int[] extractStartAndDuration(String html, String clipName) {
        String regex1 = "data-clip=\"" + Pattern.quote(clipName) + "\".*?data-start=\"(\\d+)\".*?data-duration=\"(\\d+)\"";
        Pattern p1 = Pattern.compile(regex1, Pattern.DOTALL);
        Matcher m1 = p1.matcher(html);
        if (m1.find()) {
            return new int[]{Integer.parseInt(m1.group(1)), Integer.parseInt(m1.group(2))};
        }

        String regex2 = "data-clip=\"" + Pattern.quote(clipName) + "\".*?data-duration=\"(\\d+)\".*?data-start=\"(\\d+)\"";
        Pattern p2 = Pattern.compile(regex2, Pattern.DOTALL);
        Matcher m2 = p2.matcher(html);
        assertThat(m2.find()).isTrue();
        return new int[]{Integer.parseInt(m2.group(2)), Integer.parseInt(m2.group(1))};
    }

    private void assertBeatMath(String html, String clipName, int expectedStart, int expectedDuration) {
        int[] values = extractStartAndDuration(html, clipName);
        assertThat(values[0]).isEqualTo(expectedStart);
        assertThat(values[1]).isEqualTo(expectedDuration);
    }

    private void assertStartPlusDurationNotExceeding(String html, int maxSeconds) {
        Matcher m = Pattern.compile("data-start=\"(\\d+)\".*?data-duration=\"(\\d+)\"", Pattern.DOTALL).matcher(html);
        while (m.find()) {
            assertThat(Integer.parseInt(m.group(1)) + Integer.parseInt(m.group(2))).isLessThanOrEqualTo(maxSeconds);
        }
    }

    @Test
    void timelineTemplate_hasFourAddressableClips() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);
        setField(provider, "template", "shot-timeline");

        Shot shot = new Shot();
        shot.setDescription("TestTitle");
        shot.setShotNo(3);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 6);

        String html = readCompositionHtml();
        assertThat(html).contains("data-composition-id=\"shot-timeline\"");

        Matcher clipMatcher = Pattern.compile("data-clip=\"([^\"]+)\"").matcher(html);
        List<String> clips = new ArrayList<>();
        while (clipMatcher.find()) {
            clips.add(clipMatcher.group(1));
        }
        assertThat(clips).containsExactly("bg", "title", "subtitle", "accent");

        assertThat(html).contains("TestTitle");
        assertThat(html).contains("SHOT 3");

        assertThat(html).doesNotContain("http://");
        assertThat(html).doesNotContain("https://");
        assertThat(html).doesNotContain("<link");
        assertThat(html).doesNotContain("script src");
        assertThat(html).doesNotContain("url(");
    }

    @Test
    void timelineTemplate_beatMathSeconds6() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);
        setField(provider, "template", "shot-timeline");

        Shot shot = new Shot();
        shot.setDescription("Title");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 6);

        String html = readCompositionHtml();

        assertBeatMath(html, "bg", 0, 6);
        assertBeatMath(html, "title", 0, 4);
        assertBeatMath(html, "subtitle", 2, 4);
        assertBeatMath(html, "accent", 4, 2);

        assertStartPlusDurationNotExceeding(html, 6);
    }

    @Test
    void timelineTemplate_beatMathSeconds3() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);
        setField(provider, "template", "shot-timeline");

        Shot shot = new Shot();
        shot.setDescription("Title");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 3);

        String html = readCompositionHtml();

        assertBeatMath(html, "bg", 0, 3);
        assertBeatMath(html, "title", 0, 2);
        assertBeatMath(html, "subtitle", 1, 2);
        assertBeatMath(html, "accent", 2, 1);

        assertStartPlusDurationNotExceeding(html, 3);
    }

    @Test
    void timelineTemplate_escapesTitle() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);
        setField(provider, "template", "shot-timeline");

        Shot shot = new Shot();
        shot.setDescription("A<B>&\"C");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 6);

        String html = readCompositionHtml();
        assertThat(html).contains("A&lt;B&gt;&amp;&quot;C");
        assertThat(html).doesNotContain("A<B>");
    }

    @Test
    void defaultTemplate_staysShotCard() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);

        Shot shot = new Shot();
        shot.setDescription("Title");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 6);

        String html = readCompositionHtml();
        assertThat(html).contains("data-composition-id=\"shot-card\"");
        assertThat(html).doesNotContain("shot-timeline");
    }

    @Test
    void unknownTemplate_rejectedBeforeCli() throws Exception {
        CommandRunner failRunner = (command, workDir, timeout) -> {
            throw new AssertionError("CLI should not be invoked for invalid template");
        };
        HyperFramesVideoProvider provider = createProvider(failRunner);
        setField(provider, "template", "bogus");

        Shot shot = new Shot();
        shot.setDescription("Title");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        assertThatThrownBy(() -> provider.submit(shot, 6))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("shot-card");
    }

    @Test
    void timelineTemplate_clipStartsOrdered() throws Exception {
        HyperFramesVideoProvider provider = createProvider(fakeRunner);
        setField(provider, "template", "shot-timeline");

        Shot shot = new Shot();
        shot.setDescription("Title");
        shot.setShotNo(1);
        shot.setVideoPrompt("prompt");

        provider.submit(shot, 6);

        String html = readCompositionHtml();

        List<String> clipOrder = List.of("bg", "title", "subtitle", "accent");
        List<Integer> starts = new ArrayList<>();
        for (String clip : clipOrder) {
            starts.add(extractStartAndDuration(html, clip)[0]);
        }
        assertThat(starts).containsExactly(0, 0, 2, 4);
    }
}