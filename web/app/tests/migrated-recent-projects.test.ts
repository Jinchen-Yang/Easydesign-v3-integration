import { describe, expect, it } from "vitest";
import {
  formatProjectOpenTime,
  loadRecentProjectOpens,
  rememberProjectOpen,
} from "../src/views/easy/recent-projects";

describe("Easy recent project opens", () => {
  it("records a real per-browser project open without changing project science state", () => {
    const writes: string[] = [];
    const value = rememberProjectOpen({}, "workbench-1", 1234, {
      setItem: (_key, payload) => writes.push(payload),
    });
    expect(value).toEqual({ "workbench-1": 1234 });
    expect(JSON.parse(writes[0])).toEqual(value);
  });

  it("ignores invalid persisted values", () => {
    expect(loadRecentProjectOpens({ getItem: () => "{broken" })).toEqual({});
    expect(
      loadRecentProjectOpens({
        getItem: () => JSON.stringify({ good: 10, zero: 0, text: "yesterday" }),
      }),
    ).toEqual({ good: 10 });
  });

  it("formats the timestamp as an unambiguous local minute", () => {
    const timestamp = new Date(2026, 8, 29, 14, 5).getTime();
    expect(formatProjectOpenTime(timestamp)).toBe("2026-09-29 14:05");
  });
});
