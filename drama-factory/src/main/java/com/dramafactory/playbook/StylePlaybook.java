package com.dramafactory.playbook;

import java.util.List;
import java.util.Map;

/**
 * 风格手册 POJO，承载单个 style playbook 的解析结果。
 * <p>name 为文件名去后缀的唯一标识，sections 保留除 identity/taste_profile 外的原始顶层映射。</p>
 */
public class StylePlaybook {

    private String name;
    private String displayName;
    private String category;
    private String mood;
    private String pace;
    private String bestFor;
    private TasteProfile tasteProfile;
    private ColorPalette colorPalette;
    private Map<String, Object> sections;

    public String getName() {
        return name;
    }

    public void setName(String name) {
        this.name = name;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public String getCategory() {
        return category;
    }

    public void setCategory(String category) {
        this.category = category;
    }

    public String getMood() {
        return mood;
    }

    public void setMood(String mood) {
        this.mood = mood;
    }

    public String getPace() {
        return pace;
    }

    public void setPace(String pace) {
        this.pace = pace;
    }

    public String getBestFor() {
        return bestFor;
    }

    public void setBestFor(String bestFor) {
        this.bestFor = bestFor;
    }

    public TasteProfile getTasteProfile() {
        return tasteProfile;
    }

    public void setTasteProfile(TasteProfile tasteProfile) {
        this.tasteProfile = tasteProfile;
    }

    public ColorPalette getColorPalette() {
        return colorPalette;
    }

    public void setColorPalette(ColorPalette colorPalette) {
        this.colorPalette = colorPalette;
    }

    public Map<String, Object> getSections() {
        return sections;
    }

    public void setSections(Map<String, Object> sections) {
        this.sections = sections;
    }

    /**
     * 品味档案，仅部分手册存在。
     */
    public record TasteProfile(
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

    /**
     * 色彩调色板。
     */
    public record ColorPalette(
            List<String> primary,
            List<String> accent,
            String background,
            String text,
            String muted
    ) {
    }
}
