import { describe, expect, it } from "vitest";
import { isSixDigitVerificationCode, isValidE164PhoneNumber, normalizePhoneNumber } from "../client/src/lib/phoneAuth";

describe("phone login form helpers", () => {
  it("normalizes an international mobile number without changing its country code", () => {
    expect(normalizePhoneNumber(" +971 50-123 4567 ")).toBe("+971501234567");
    expect(isValidE164PhoneNumber("+971 50-123 4567")).toBe(true);
  });

  it("rejects local numbers without an international country code", () => {
    expect(isValidE164PhoneNumber("0501234567")).toBe(false);
    expect(isValidE164PhoneNumber("+971123")).toBe(false);
  });

  it("accepts only exactly six numeric verification digits", () => {
    expect(isSixDigitVerificationCode("123456")).toBe(true);
    expect(isSixDigitVerificationCode("12345")).toBe(false);
    expect(isSixDigitVerificationCode("12ab56")).toBe(false);
  });
});
