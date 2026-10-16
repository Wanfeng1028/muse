package com.dramafactory.service.video;

import com.dramafactory.model.Shot;
import org.springframework.stereotype.Component;

@Component
public class ShotVideoRouter {

    /** 返回分镜的首选提供方名，无明确指向时返回 null。 */
    public String route(Shot shot) {
        if (shot == null) {
            return null;
        }

        String preferred = shot.getPreferredProvider();
        if (preferred != null && !preferred.isBlank()) {
            return preferred;
        }

        String videoPrompt = shot.getVideoPrompt();
        String description = shot.getDescription();
        if (videoPrompt == null && description == null) {
            return null;
        }

        StringBuilder sb = new StringBuilder();
        if (videoPrompt != null) {
            sb.append(videoPrompt).append(' ');
        }
        if (description != null) {
            sb.append(description);
        }
        String text = sb.toString().toLowerCase();

        if (text.contains("卡通")
                || text.contains("cartoon")
                || text.contains("皮克斯")
                || text.contains("pixar")
                || text.contains("动画")
                || text.contains("animation")
                || text.contains("可爱")
                || text.contains("cute")) {
            return "doubao";
        }

        if (text.contains("写实")
                || text.contains("真人")
                || text.contains("realistic")
                || text.contains("电影感")
                || text.contains("cinematic")) {
            return "novai";
        }

        if (text.contains("水墨")
                || text.contains("国风")
                || text.contains("中文文字")
                || text.contains("calligraphy")) {
            return "painted";
        }

        if (text.contains("水彩")
                || text.contains("watercolor")
                || text.contains("手绘")
                || text.contains("hand-painted")
                || text.contains("风格化")) {
            return "painted";
        }

        return null;
    }
}
