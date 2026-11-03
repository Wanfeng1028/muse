package com.dramafactory.playbook;

import java.util.List;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.dramafactory.exception.ResourceNotFoundException;

import io.swagger.v3.oas.annotations.tags.Tag;

/**
 * 风格手册 REST 接口。
 */
@RestController
@RequestMapping("/api/style-playbooks")
@Tag(name = "StylePlaybooks", description = "风格手册")
public class StylePlaybookController {

    private final StylePlaybookService service;

    public StylePlaybookController(StylePlaybookService service) {
        this.service = service;
    }

    /**
     * 列出所有风格手册摘要。
     *
     * @return 摘要列表
     */
    @GetMapping("")
    public List<PlaybookSummaryDto> listPlaybooks() {
        return service.listPlaybooks().stream()
                .map(p -> new PlaybookSummaryDto(
                        p.getName(),
                        p.getDisplayName(),
                        p.getCategory(),
                        p.getMood(),
                        p.getPace(),
                        p.getBestFor(),
                        toPaletteDto(p.getColorPalette())
                ))
                .toList();
    }

    /**
     * 查询单个风格手册详情。
     *
     * @param name 手册名
     * @return 详情
     */
    @GetMapping("/{name}")
    public PlaybookDetailDto getPlaybook(@PathVariable String name) {
        StylePlaybook p = service.getPlaybook(name)
                .orElseThrow(() -> ResourceNotFoundException.withKey("StylePlaybook", name));
        return new PlaybookDetailDto(
                p.getName(),
                p.getDisplayName(),
                p.getCategory(),
                p.getMood(),
                p.getPace(),
                p.getBestFor(),
                toTasteProfileDto(p.getTasteProfile()),
                toPaletteDto(p.getColorPalette()),
                p.getSections()
        );
    }

    private TasteProfileDto toTasteProfileDto(StylePlaybook.TasteProfile tp) {
        if (tp == null) {
            return null;
        }
        return new TasteProfileDto(
                tp.designRead(),
                tp.visualVariance(),
                tp.motionIntensity(),
                tp.informationDensity(),
                tp.paletteDiscipline(),
                tp.layoutVariation(),
                tp.referenceStrategy(),
                tp.antiPatterns(),
                tp.qualityGates()
        );
    }

    private ColorPaletteDto toPaletteDto(StylePlaybook.ColorPalette cp) {
        if (cp == null) {
            return null;
        }
        return new ColorPaletteDto(
                cp.primary(),
                cp.accent(),
                cp.background(),
                cp.text(),
                cp.muted()
        );
    }

    /**
     * 风格手册摘要 DTO。
     */
    public record PlaybookSummaryDto(
            String name,
            String displayName,
            String category,
            String mood,
            String pace,
            String bestFor,
            ColorPaletteDto palette
    ) {
    }

    /**
     * 风格手册详情 DTO。
     */
    public record PlaybookDetailDto(
            String name,
            String displayName,
            String category,
            String mood,
            String pace,
            String bestFor,
            TasteProfileDto tasteProfile,
            ColorPaletteDto palette,
            Map<String, Object> sections
    ) {
    }

    /**
     * 色彩调色板 DTO。
     */
    public record ColorPaletteDto(
            List<String> primary,
            List<String> accent,
            String background,
            String text,
            String muted
    ) {
    }

    /**
     * 品味档案 DTO。
     */
    public record TasteProfileDto(
            String designRead,
            Integer visualVariance,
            Integer motionIntensity,
            Integer informationDensity,
            String paletteDiscipline,
            String layoutVariation,
            String referenceStrategy,
            List<String> antiPatterns,
            List<String> qualityGates
    ) {
    }
}
