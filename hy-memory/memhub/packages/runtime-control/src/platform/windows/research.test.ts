import { describe, expect, it } from "vitest";
import {
  createWindowsSupportAssessment,
  WINDOWS_RESEARCH_STATE,
} from "./research.js";

describe("Windows H08 support assessment", () => {
  it("keeps every real-machine gate blocked instead of extrapolating", () => {
    for (const capability of Object.values(
      WINDOWS_RESEARCH_STATE.capabilities,
    )) {
      if ("status" in capability && capability.status !== "implemented") {
        expect(capability.status).toBe("blocked");
        expect(capability.blocked_reason).toMatch(/windows|target_machine/);
      }
    }
    expect(WINDOWS_RESEARCH_STATE.minimum_release_gate).toMatchObject({
      os: "Windows 11",
      arch: "x64",
      status: "blocked",
    });
  });

  it("explicitly excludes Windows 10 and arm64 from the x64 release gate", () => {
    expect(WINDOWS_RESEARCH_STATE.explicit_matrix).toMatchObject({
      windows_10_x64: {
        support: "blocked",
        blocked_reason: "windows_10_matrix_not_measured",
      },
      windows_arm64: {
        support: "blocked",
        blocked_reason: "windows_arm64_matrix_not_measured",
      },
    });
  });

  it("never permits the POSIX owner-only fallback on Windows", () => {
    const assessment = createWindowsSupportAssessment();
    expect(assessment.canUsePosixOwnerOnlyFallback("win32")).toBe(false);
    expect(assessment.canUsePosixOwnerOnlyFallback("darwin")).toBe(true);
    expect(assessment.canUsePosixOwnerOnlyFallback("linux")).toBe(true);
  });

  it("requires target-machine readiness before calling x64 supported", () => {
    const assessment = createWindowsSupportAssessment();
    expect(assessment.isSupportedReleaseTarget("win32", "x64")).toBe(false);
    expect(assessment.blockedReason("win32", "x64")).toBe(
      "windows_target_machine_required",
    );
    expect(assessment.blockedReason("win32", "arm64")).toBe(
      "windows_arm64_matrix_not_measured",
    );
    expect(assessment.blockedReason("darwin", "x64")).toBeNull();
  });

  it("normalizes Windows paths for a future reparse-point containment check", () => {
    const assessment = createWindowsSupportAssessment();
    expect(
      assessment.reparseLikePath("C:\\Programs\\中文 One Memory\\runtime"),
    ).toBe("C:\\Programs\\中文 One Memory\\runtime");
    expect(assessment.reparseLikePath("relative\\path")).toBeNull();
    expect(assessment.containsReparseMarker("C:\\One Memory\\runtime")).toBe(
      true,
    );
    expect(assessment.containsReparseMarker("")).toBe(false);
  });
});
