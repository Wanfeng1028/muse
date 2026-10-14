
package com.dramafactory.model;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

/**
 * CameraMove.fromLabel 的解析规则测试。
 */
class CameraMoveTest {

    @Test
    void fromLabel_null_returnsNull() {
        assertNull(CameraMove.fromLabel(null));
    }

    @Test
    void fromLabel_empty_returnsNull() {
        assertNull(CameraMove.fromLabel(""));
    }

    @Test
    void fromLabel_blank_returnsNull() {
        assertNull(CameraMove.fromLabel(" "));
    }

    @Test
    void fromLabel_allValidLabels_roundTrip() {
        for (CameraMove move : CameraMove.values()) {
            assertEquals(move, CameraMove.fromLabel(move.getLabel()));
        }
    }

    @Test
    void fromLabel_invalidLabel_throwsWithOriginalLabel() {
        IllegalArgumentException ex = assertThrows(IllegalArgumentException.class,
                () -> CameraMove.fromLabel("旋转飞行"));
        assertEquals("未知的运镜标签: 旋转飞行", ex.getMessage());
    }
}

