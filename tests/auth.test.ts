import { describe, expect, it } from "vitest";
import { checkBasicAuth, isPasswordConfigured, timingSafeEqualStr } from "../lib/auth";

function basic(user: string, pass: string): string {
  return "Basic " + Buffer.from(`${user}:${pass}`).toString("base64");
}

describe("timingSafeEqualStr", () => {
  it("matches equal strings", () => {
    expect(timingSafeEqualStr("abc", "abc")).toBe(true);
  });
  it("rejects different strings and different lengths", () => {
    expect(timingSafeEqualStr("abc", "abd")).toBe(false);
    expect(timingSafeEqualStr("abc", "abcd")).toBe(false);
    expect(timingSafeEqualStr("", "a")).toBe(false);
  });
});

describe("isPasswordConfigured (fail closed)", () => {
  it("rejects unset, empty, and placeholder", () => {
    expect(isPasswordConfigured(undefined)).toBe(false);
    expect(isPasswordConfigured(null)).toBe(false);
    expect(isPasswordConfigured("")).toBe(false);
    expect(isPasswordConfigured("CHANGE_ME")).toBe(false);
  });
  it("accepts a real password", () => {
    expect(isPasswordConfigured("s3cret")).toBe(true);
  });
});

describe("checkBasicAuth", () => {
  it("passes with correct credentials", () => {
    expect(checkBasicAuth(basic("preview", "s3cret"), "preview", "s3cret")).toBe(true);
  });
  it("fails with wrong password", () => {
    expect(checkBasicAuth(basic("preview", "wrong"), "preview", "s3cret")).toBe(false);
  });
  it("fails with wrong username", () => {
    expect(checkBasicAuth(basic("admin", "s3cret"), "preview", "s3cret")).toBe(false);
  });
  it("fails when password is unset — even if the header 'matches'", () => {
    expect(checkBasicAuth(basic("preview", ""), "preview", undefined)).toBe(false);
    expect(checkBasicAuth(null, "preview", undefined)).toBe(false);
  });
  it("fails when password is CHANGE_ME — even with a matching header", () => {
    expect(checkBasicAuth(basic("preview", "CHANGE_ME"), "preview", "CHANGE_ME")).toBe(false);
  });
  it("fails on missing/malformed headers", () => {
    expect(checkBasicAuth(null, "preview", "s3cret")).toBe(false);
    expect(checkBasicAuth("Bearer abc", "preview", "s3cret")).toBe(false);
    expect(checkBasicAuth("Basic !!!not-base64!!!", "preview", "s3cret")).toBe(false);
    expect(checkBasicAuth("Basic " + Buffer.from("nocolon").toString("base64"), "preview", "s3cret")).toBe(false);
  });
  it("passwords containing colons survive parsing", () => {
    expect(checkBasicAuth(basic("preview", "a:b:c"), "preview", "a:b:c")).toBe(true);
  });
});
