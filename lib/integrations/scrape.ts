/**
 * Server-side HTML extraction for the URL scraping feature.
 * No extra packages — pure fetch + regex stripping.
 *
 * Strategy (in priority order):
 *  1. JSON-LD schema.org markup  → highest precision
 *  2. OpenGraph / meta tags      → title and description
 *  3. Spec tables / dl lists     → structured specs
 *  4. Paragraph text             → free-text fallback
 *
 * Output is a cleaned text blob passed to the LLM for field extraction.
 */

export interface ExtractedPage {
  title: string;
  description: string;
  /** Flattened key→value pairs from JSON-LD and meta tags */
  structuredData: Record<string, string>;
  /** Plain text, capped at 8 000 chars to stay within token budgets */
  text: string;
}

export async function fetchAndExtract(rawUrl: string): Promise<ExtractedPage> {
  // Normalise — ensure we have a full URL
  const url = rawUrl.startsWith("http") ? rawUrl : `https://${rawUrl}`;

  const res = await fetch(url, {
    headers: {
      "User-Agent":
        "MIA-DPP/1.0 (+https://mia-dpp.vercel.app; fetching product data for Digital Product Passport generation)",
      Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
      "Accept-Language": "en,de;q=0.9",
    },
    signal: AbortSignal.timeout(15_000),
    // Follow redirects (default in Node fetch)
  });

  if (!res.ok) {
    throw new Error(`HTTP ${res.status} fetching ${url}`);
  }

  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("html") && !contentType.includes("xml")) {
    throw new Error(
      `Expected HTML but received ${contentType}. Paste the product text directly instead.`
    );
  }

  const html = await res.text();
  return extractFromHtml(html);
}

function extractFromHtml(html: string): ExtractedPage {
  // Remove noisy blocks before any further parsing
  const cleaned = html
    .replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<nav\b[^>]*>[\s\S]*?<\/nav>/gi, " ")
    .replace(/<footer\b[^>]*>[\s\S]*?<\/footer>/gi, " ")
    .replace(/<header\b[^>]*>[\s\S]*?<\/header>/gi, " ")
    .replace(/<!--[\s\S]*?-->/g, " ");

  // ── Title ──────────────────────────────────────────────────────────────────
  const titleMatch = cleaned.match(/<title[^>]*>([^<]+)<\/title>/i);
  const title = titleMatch ? htmlDecode(titleMatch[1].trim()) : "";

  // ── Meta description (regular + og) ────────────────────────────────────────
  const descMatch =
    cleaned.match(
      /<meta[^>]+name=["']description["'][^>]+content=["']([^"']+)["']/i
    ) ||
    cleaned.match(
      /<meta[^>]+content=["']([^"']+)["'][^>]+name=["']description["']/i
    ) ||
    cleaned.match(
      /<meta[^>]+property=["']og:description["'][^>]+content=["']([^"']+)["']/i
    ) ||
    cleaned.match(
      /<meta[^>]+content=["']([^"']+)["'][^>]+property=["']og:description["']/i
    );
  const description = descMatch ? htmlDecode(descMatch[1].trim()) : "";

  // ── JSON-LD structured data ────────────────────────────────────────────────
  const structuredData: Record<string, string> = {};
  for (const match of Array.from(
    cleaned.matchAll(
      /<script[^>]+type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/gi
    )
  )) {
    try {
      const obj = JSON.parse(match[1]);
      flattenObj(obj, structuredData);
    } catch {
      // malformed JSON-LD — skip
    }
  }

  // ── Specification tables & definition lists ────────────────────────────────
  // These typically carry the most precise product data.
  const specPairs: string[] = [];

  // <table> rows with two cells (label | value)
  for (const row of Array.from(cleaned.matchAll(/<tr[^>]*>([\s\S]*?)<\/tr>/gi))) {
    const cells = Array.from(row[1].matchAll(/<t[hd][^>]*>([\s\S]*?)<\/t[hd]>/gi)).map(
      (c) => stripTags(c[1])
    );
    if (cells.length === 2 && cells[0] && cells[1]) {
      specPairs.push(`${cells[0]}: ${cells[1]}`);
    }
  }

  // <dl> definition lists
  const dlMatch = cleaned.match(/<dl[^>]*>([\s\S]*?)<\/dl>/gi);
  if (dlMatch) {
    for (const dl of dlMatch) {
      const dts = Array.from(dl.matchAll(/<dt[^>]*>([\s\S]*?)<\/dt>/gi)).map((m) =>
        stripTags(m[1])
      );
      const dds = Array.from(dl.matchAll(/<dd[^>]*>([\s\S]*?)<\/dd>/gi)).map((m) =>
        stripTags(m[1])
      );
      dts.forEach((dt, i) => {
        if (dt && dds[i]) specPairs.push(`${dt}: ${dds[i]}`);
      });
    }
  }

  // ── General text fallback ──────────────────────────────────────────────────
  const rawText = stripTags(cleaned).replace(/\s+/g, " ").trim();

  // Combine: structured specs first (most signal), then raw text
  const combined = [
    title && `Title: ${title}`,
    description && `Description: ${description}`,
    specPairs.length > 0 && `Specifications:\n${specPairs.slice(0, 60).join("\n")}`,
    `Page content: ${rawText}`,
  ]
    .filter(Boolean)
    .join("\n\n")
    .slice(0, 8000); // stay inside model context budgets

  return { title, description, structuredData, text: combined };
}

// ── Helpers ────────────────────────────────────────────────────────────────

function stripTags(s: string): string {
  return htmlDecode(s.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim());
}

function htmlDecode(s: string): string {
  return s
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&nbsp;/g, " ");
}

function flattenObj(
  obj: Record<string, unknown>,
  out: Record<string, string>,
  prefix = ""
): void {
  for (const [key, val] of Object.entries(obj)) {
    if (key === "@context") continue;
    const k = prefix ? `${prefix}.${key}` : key;
    if (typeof val === "string" || typeof val === "number") {
      out[k] = String(val);
    } else if (Array.isArray(val)) {
      val.forEach((item, i) => {
        if (typeof item === "object" && item !== null) {
          flattenObj(item as Record<string, unknown>, out, `${k}[${i}]`);
        } else if (typeof item === "string" || typeof item === "number") {
          out[`${k}[${i}]`] = String(item);
        }
      });
    } else if (typeof val === "object" && val !== null) {
      flattenObj(val as Record<string, unknown>, out, k);
    }
  }
}
