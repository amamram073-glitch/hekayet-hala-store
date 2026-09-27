export function normalizePhoneNumber(value: string): string {
  const trimmed = value.trim();
  const hasLeadingPlus = trimmed.startsWith("+");
  const digits = trimmed.replace(/\D/g, "");
  return hasLeadingPlus ? `+${digits}` : digits;
}

export function isValidE164PhoneNumber(value: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(normalizePhoneNumber(value));
}

export function isSixDigitVerificationCode(value: string): boolean {
  return /^\d{6}$/.test(value.trim());
}
