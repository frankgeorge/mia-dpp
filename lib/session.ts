/**
 * In-memory supplier session store.
 *
 * Sessions are created when MIA sends a gap-request email and are resolved
 * when the supplier submits the reply portal form. The module-level Map
 * persists across requests on the same Vercel Fluid Compute instance.
 *
 * Production upgrade path: replace the Map with Vercel KV or any key-value
 * store — the interface is identical.
 */

export interface GapField {
  name: string;
  hint: string;
  required: boolean;
}

export interface OrgBranding {
  orgName?: string;
  logoUrl?: string;
  brandColor?: string;
}

export interface SupplierSession {
  token: string;
  productName: string;
  productUrl: string;
  contactEmail: string;
  /** IDTA Nameplate element names still missing from the scraped page */
  gaps: GapField[];
  createdAt: string;
  expiresAt: string;
  branding?: OrgBranding;
  /** Keyed by NAMEPLATE_ELEMENTS name; populated when supplier submits */
  response?: Record<string, string>;
  respondedAt?: string;
}

const sessions = new Map<string, SupplierSession>();

export function createSession(
  data: Omit<SupplierSession, "token" | "createdAt" | "expiresAt">
): string {
  const token = uid();
  const now = Date.now();
  sessions.set(token, {
    ...data,
    token,
    createdAt: new Date(now).toISOString(),
    expiresAt: new Date(now + 7 * 24 * 60 * 60 * 1000).toISOString(),
  });
  return token;
}

export function getSession(token: string): SupplierSession | undefined {
  const s = sessions.get(token);
  if (!s) return undefined;
  if (new Date(s.expiresAt) < new Date()) {
    sessions.delete(token);
    return undefined;
  }
  return s;
}

export function respondToSession(
  token: string,
  response: Record<string, string>
): boolean {
  const s = getSession(token);
  if (!s) return false;
  sessions.set(token, {
    ...s,
    response,
    respondedAt: new Date().toISOString(),
  });
  return true;
}

function uid(): string {
  return (
    Math.random().toString(36).slice(2, 10) +
    Math.random().toString(36).slice(2, 10)
  );
}
