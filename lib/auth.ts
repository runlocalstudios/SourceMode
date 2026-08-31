/**
 * Preview-gate auth logic, kept pure so it can be unit-tested without Next.
 *
 * FAIL CLOSED: if the configured password is unset, empty, or the placeholder
 * "CHANGE_ME", nothing authenticates.
 */

const PLACEHOLDER_PASSWORD = "CHANGE_ME";

/** Constant-time string comparison (works in Node and Edge runtimes). */
export function timingSafeEqualStr(a: string, b: string): boolean {
  const len = Math.max(a.length, b.length);
  let diff = a.length === b.length ? 0 : 1;
  for (let i = 0; i < len; i++) {
    diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  }
  return diff === 0;
}

export function isPasswordConfigured(password: string | undefined | null): boolean {
  return !!password && password !== PLACEHOLDER_PASSWORD;
}

/**
 * Validate an HTTP Basic Authorization header against expected credentials.
 * Returns true only when the password is properly configured AND the header
 * carries the exact username/password pair.
 */
export function checkBasicAuth(
  authHeader: string | null | undefined,
  expectedUsername: string,
  expectedPassword: string | undefined | null,
): boolean {
  if (!isPasswordConfigured(expectedPassword)) return false;
  if (!authHeader || !authHeader.startsWith("Basic ")) return false;

  let decoded: string;
  try {
    decoded = atob(authHeader.slice("Basic ".length).trim());
  } catch {
    return false;
  }
  const sep = decoded.indexOf(":");
  if (sep < 0) return false;
  const user = decoded.slice(0, sep);
  const pass = decoded.slice(sep + 1);

  const userOk = timingSafeEqualStr(user, expectedUsername);
  const passOk = timingSafeEqualStr(pass, expectedPassword as string);
  return userOk && passOk;
}
