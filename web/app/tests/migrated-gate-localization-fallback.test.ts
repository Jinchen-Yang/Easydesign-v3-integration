import { describe, expect, it } from "vitest";
import { gateLocalizationText } from "../src/views/easy/EasyLiveApp";

describe("Gate scientific-language fallback", () => {
  it("shows the source passage instead of an ellipsis when localization is unavailable", () => {
    const source = "Whole-VHH accessibility has not yet been validated.";
    expect(gateLocalizationText({}, "gate.warning.0", source)).toBe(source);
    expect(gateLocalizationText({}, "gate.warning.0", source)).not.toBe("…");
  });

  it("prefers the localized passage after a retry succeeds", () => {
    expect(
      gateLocalizationText(
        { "gate.warning.0": "尚未验证完整 VHH 的空间可达性。" },
        "gate.warning.0",
        "Whole-VHH accessibility has not yet been validated.",
      ),
    ).toBe("尚未验证完整 VHH 的空间可达性。");
  });
});
