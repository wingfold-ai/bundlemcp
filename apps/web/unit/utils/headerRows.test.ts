import { describe, expect, it } from "vitest";
import { headersToRows, rowsToHeaders } from "~/utils/headerRows";

describe("UI-1 rowsToHeaders", () => {
  it("leaves out a row without a header name", () => {
    const rows = [
      { key: "", val: "x-ignored" },
      { key: "   ", val: "x-ignored" },
      { key: "x-tenant", val: "x-org" },
    ];
    expect(rowsToHeaders(rows, { emptyValue: "keep" })).toEqual({ "x-tenant": "x-org" });
  });

  it("trims the header name", () => {
    expect(rowsToHeaders([{ key: "  x-tenant ", val: "x-org" }], { emptyValue: "keep" })).toEqual({
      "x-tenant": "x-org",
    });
  });

  it("sends an empty value as typed when asked to keep it", () => {
    expect(rowsToHeaders([{ key: "x-foo", val: "" }], { emptyValue: "keep" })).toEqual({
      "x-foo": "",
    });
  });

  it("sends the header's own name for an empty value when asked to", () => {
    expect(rowsToHeaders([{ key: "x-foo", val: "" }], { emptyValue: "key" })).toEqual({
      "x-foo": "x-foo",
    });
  });

  it("round-trips a stored header map through rows", () => {
    const headers = { "x-tenant": "x-org", authorization: "authorization" };
    expect(rowsToHeaders(headersToRows(headers), { emptyValue: "keep" })).toEqual(headers);
  });
});
