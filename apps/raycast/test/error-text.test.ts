import { describe, expect, it } from "vitest";
import type { ErrorResponse } from "../src/lib/contract";
import { errorText } from "../src/lib/error-text";
import { TransportError } from "../src/lib/errors";
import { fixture } from "./helpers";

describe("errorText", () => {
  it("offers the install command and preferences when csk is missing", () => {
    const t = errorText(new TransportError("not_found", "csk was not found.", "Looked in: ..."));
    expect(t.title).toBe("csk not found");
    expect(t.copyCommand).toBe("uv tool install --editable .");
    expect(t.showPreferences).toBe(true);
    expect(t.markdown).toContain("Looked in");
  });

  it("offers the reinstall command after a startup failure", () => {
    expect(errorText(new TransportError("reinstall", "csk could not start.")).copyCommand).toBe(
      "uv tool install --editable . --reinstall",
    );
  });

  it("lists the fields of an input error", () => {
    const response = JSON.parse(fixture("validation-error")) as ErrorResponse;
    const t = errorText(response.error);
    expect(t.title).toBe("Check the input");
    expect(t.markdown).toContain("**max_isomers**");
    expect(t.copyCommand).toBeUndefined();
  });

  it("shows a crash traceback", () => {
    const t = errorText({ type: "crash", message: "the tool crashed", details: [], traceback: "Traceback ...\nBoom" });
    expect(t.title).toBe("The tool crashed");
    expect(t.markdown).toContain("## Traceback");
    expect(t.copyText).toContain("Boom");
  });

  it("still shows unknown error types", () => {
    const t = errorText({ type: "something_new", message: "from a newer csk", details: [], traceback: "" });
    expect(t.title).toBe("Error");
    expect(t.markdown).toContain("from a newer csk");
  });
});
