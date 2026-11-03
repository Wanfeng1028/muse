package com.dramafactory.api;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.transaction.annotation.Transactional;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Transactional
class SkillHubQueryFilterTest {

    @Autowired
    private MockMvc mockMvc;

    static Path SKILLS_TMP;

    @DynamicPropertySource
    static void props(DynamicPropertyRegistry r) {
        try {
            SKILLS_TMP = Files.createTempDirectory("skillhub-query-test");
        } catch (Exception e) {
            throw new RuntimeException(e);
        }
        r.add("drama.skills.dir", () -> SKILLS_TMP.toString());
    }

    private String bodyWithParams(String... nameValuePairs) throws Exception {
        var builder = get("/api/skillhub/index");
        for (int i = 0; i < nameValuePairs.length; i += 2) {
            builder = builder.param(nameValuePairs[i], nameValuePairs[i + 1]);
        }
        MvcResult r = mockMvc.perform(builder).andExpect(status().isOk()).andReturn();
        return r.getResponse().getContentAsString(StandardCharsets.UTF_8);
    }

    private int baselineTotal() throws Exception {
        return JsonPath.read(bodyWithParams(), "$.total");
    }

    private int intField(String body, String field) {
        return JsonPath.read(body, "$." + field);
    }

    @Test
    void qAndSourceOfficial_returnsSingleOfficialVideoSkill() throws Exception {
        String body = bodyWithParams("q", "video", "source", "官方出品");
        int total = intField(body, "total");
        assertEquals(1, total, "q=video 且 source=官方出品 应只命中 openmontage-video-edit");
        List<String> ids = JsonPath.read(body, "$.skills[*].id");
        assertEquals(List.of("openmontage-video-edit"), ids);
        List<String> sources = JsonPath.read(body, "$.skills[*].source");
        assertTrue(sources.stream().allMatch("官方出品"::equals));
    }

    @Test
    void qAndSourceCommunity_excludesOfficial() throws Exception {
        String videoBody = bodyWithParams("q", "video");
        int qv = intField(videoBody, "total");
        String body = bodyWithParams("q", "video", "source", "社区收录");
        int total = intField(body, "total");
        assertEquals(qv - 1, total, "q=video 且 source=社区收录 应排除官方出品，total 应为 qv-1");
        List<String> sources = JsonPath.read(body, "$.skills[*].source");
        assertTrue(sources.stream().allMatch("社区收录"::equals), "所有条目 source 应为社区收录");
        List<String> ids = JsonPath.read(body, "$.skills[*].id");
        assertFalse(ids.contains("openmontage-video-edit"), "ids 不应包含官方出品的 openmontage-video-edit");
    }

    @Test
    void qIsCaseInsensitive() throws Exception {
        String lower = bodyWithParams("q", "video");
        String upper = bodyWithParams("q", "VIDEO");
        int lowerTotal = intField(lower, "total");
        int upperTotal = intField(upper, "total");
        assertEquals(lowerTotal, upperTotal, "q 应大小写不敏感，VIDEO 与 video 的 total 应相等");
        assertTrue(upperTotal > 0, "q=VIDEO 应命中至少一条");
    }

    @Test
    void qBlankIsIgnored() throws Exception {
        String body = bodyWithParams("q", "   ");
        int total = intField(body, "total");
        int base = baselineTotal();
        assertEquals(base, total, "q 为空白时应被忽略，total 应等于基线");
        int size = intField(body, "size");
        assertEquals(50, size, "q 空白被忽略后应走分页分支，size 缺省应为 50");
    }

    @Test
    void sourceInvalidValueIsIgnored() throws Exception {
        String body = bodyWithParams("source", "不存在的来源");
        int total = intField(body, "total");
        int base = baselineTotal();
        assertEquals(base, total, "source 传无效值时应视为未传，total 应等于基线");
    }

    @Test
    void sizeAboveMaxClampedTo200() throws Exception {
        String body = bodyWithParams("size", "500");
        int size = intField(body, "size");
        assertEquals(200, size, "size=500 应被钳制为 200");
        List<?> skills = JsonPath.read(body, "$.skills");
        assertEquals(200, skills.size(), "skills 数组长度应为 200");
    }

    @Test
    void sizeZeroAndNegativeClampedTo1() throws Exception {
        String zeroBody = bodyWithParams("size", "0");
        int zeroSize = intField(zeroBody, "size");
        assertEquals(1, zeroSize, "size=0 应被钳制为 1");
        List<?> zeroSkills = JsonPath.read(zeroBody, "$.skills");
        assertEquals(1, zeroSkills.size(), "size=0 时 skills 长度应为 1");

        String negBody = bodyWithParams("size", "-10");
        int negSize = intField(negBody, "size");
        assertEquals(1, negSize, "size=-10 应被钳制为 1");
    }

    @Test
    void pageFarBeyondTotalReturnsEmptyPage() throws Exception {
        String body = bodyWithParams("page", "99999", "size", "10");
        List<?> skills = JsonPath.read(body, "$.skills");
        assertTrue(skills.isEmpty(), "page 越界时 skills 应为空数组");
        int total = intField(body, "total");
        int base = baselineTotal();
        assertEquals(base, total, "page 越界时 total 仍应为过滤后总数（基线）");
        int page = intField(body, "page");
        assertEquals(99999, page, "page 应原样返回 99999");
        int totalPages = intField(body, "totalPages");
        assertEquals((base + 9) / 10, totalPages, "totalPages 应为 ceil(total/10)");
    }

    @Test
    void pageNegativeClampedToZero() throws Exception {
        String body = bodyWithParams("page", "-3", "size", "10");
        int page = intField(body, "page");
        assertEquals(0, page, "page=-3 应被钳制为 0");
        List<?> skills = JsonPath.read(body, "$.skills");
        assertEquals(10, skills.size(), "page 钳制为 0 后 skills 长度应为 10");
    }

    @Test
    void totalPagesIsCeilOfTotalOverSize() throws Exception {
        String body = bodyWithParams("size", "100");
        int totalPages = intField(body, "totalPages");
        int base = baselineTotal();
        assertEquals((base + 99) / 100, totalPages, "totalPages 应为 ceil(total/100)");
        List<?> skills = JsonPath.read(body, "$.skills");
        assertEquals(100, skills.size(), "skills 长度应为 100");
    }

    @Test
    void qNoMatchReturnsZeroTotal() throws Exception {
        String body = bodyWithParams("q", "zzz-no-such-skill-xyz");
        int total = intField(body, "total");
        assertEquals(0, total, "q 无匹配时 total 应为 0");
        int totalPages = intField(body, "totalPages");
        assertEquals(0, totalPages, "total=0 时 totalPages 应为 0");
        List<?> skills = JsonPath.read(body, "$.skills");
        assertTrue(skills.isEmpty(), "q 无匹配时 skills 应为空数组");
    }

    @Test
    void lastPageNonEmpty_nextPageEmpty() throws Exception {
        int base = baselineTotal();
        int lastPage = (base + 99) / 100 - 1;
        String lastBody = bodyWithParams("page", String.valueOf(lastPage), "size", "100");
        List<?> lastSkills = JsonPath.read(lastBody, "$.skills");
        assertFalse(lastSkills.isEmpty(), "最后一页 skills 应非空");

        String nextBody = bodyWithParams("page", String.valueOf(lastPage + 1), "size", "100");
        List<?> nextSkills = JsonPath.read(nextBody, "$.skills");
        assertTrue(nextSkills.isEmpty(), "最后一页之后 skills 应为空数组");
        int total = intField(nextBody, "total");
        assertEquals(base, total, "越界页 total 仍应等于基线");
    }
}