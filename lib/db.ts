import { neon } from "@neondatabase/serverless";

/** Returns a Neon HTTP query function, or null when DATABASE_URL is not set. */
export function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) return null;
  return neon(url);
}
