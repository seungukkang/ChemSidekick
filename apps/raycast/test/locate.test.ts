import { describe, expect, it } from "vitest";
import { TransportError } from "../src/lib/errors";
import { candidatePaths, locateCsk } from "../src/lib/locate";

describe("locateCsk", () => {
  it("uses the preference alone when it is set", () => {
    expect(candidatePaths(" /opt/csk ", "/Users/me")).toEqual(["/opt/csk"]);
  });

  it("tries ~/.local/bin first, then Homebrew", () => {
    expect(candidatePaths(undefined, "/Users/me")).toEqual([
      "/Users/me/.local/bin/csk",
      "/opt/homebrew/bin/csk",
      "/usr/local/bin/csk",
    ]);
  });

  it("returns the first executable candidate", () => {
    const found = locateCsk("", "/Users/me", (p) => p === "/opt/homebrew/bin/csk");
    expect(found).toBe("/opt/homebrew/bin/csk");
  });

  it("explains where it looked when csk is missing", () => {
    try {
      locateCsk(undefined, "/Users/me", () => false);
      expect.unreachable();
    } catch (e) {
      expect(e).toBeInstanceOf(TransportError);
      const err = e as TransportError;
      expect(err.kind).toBe("not_found");
      expect(err.message).toContain("uv tool install --editable .");
      expect(err.detail).toContain("/Users/me/.local/bin/csk");
    }
  });

  it("names a wrong preference", () => {
    expect(() => locateCsk("/nope/csk", "/Users/me", () => false)).toThrow(/preferences .* \/nope\/csk/);
  });
});
