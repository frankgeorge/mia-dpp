export function flattenSapResponse(obj: Record<string, unknown>, prefix = ""): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("__") || k === "metadata") continue;
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string" && v.trim()) out[key] = v.trim();
    else if (typeof v === "number") out[key] = String(v);
    else if (typeof v === "object" && v !== null && !Array.isArray(v)) {
      Object.assign(out, flattenSapResponse(v as Record<string, unknown>, key));
    }
  }
  return out;
}
