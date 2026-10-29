import { describe, expect, it } from "vitest";
import { nameProblem } from "~/utils/resourceNames";

describe("UI-4 nameProblem", () => {
  it("accepts a name the published pattern allows", () => {
    expect(nameProblem("upstream", "my-server_1")).toBeNull();
  });

  it("asks for a name when none is given", () => {
    expect(nameProblem("bundle", "")).toBe("Bundle name is required");
  });

  it("refuses a name outside the published pattern", () => {
    expect(nameProblem("bundle", "has space")).toBe("Bundle name must match ^[a-zA-Z0-9_-]+$");
  });

  it("refuses a double underscore in an upstream name", () => {
    expect(nameProblem("upstream", "my__server")).toBe('Upstream name must not contain "__"');
  });

  it("allows a double underscore where only upstreams forbid it", () => {
    expect(nameProblem("bundle", "my__bundle")).toBeNull();
  });

  it("refuses a reserved endpoint name, whatever its case", () => {
    expect(nameProblem("endpoint", "api")).toBe('"api" is a reserved endpoint name');
    expect(nameProblem("endpoint", "Login")).toBe('"Login" is a reserved endpoint name');
  });

  it("refuses a name another resource of the kind already has", () => {
    expect(nameProblem("bundle", "demo", ["demo", "other"])).toBe(
      'Bundle name "demo" is already taken',
    );
    expect(nameProblem("bundle", "fresh", ["demo"])).toBeNull();
  });
});
