export const runtime = "nodejs";

// GET /api/fetch-url?url=<product-url>
// Fetches a product page and returns:
//   - text: visible page text for LLM extraction
//   - title: page title
//   - productImageUrl: best product image (not logo/banner)
//   - pdfLinks: array of PDF URLs found on the page (manuals, datasheets)

function stripHtml(html: string): string {
  return html
    .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, " ")
    .replace(/<head[^>]*>[\s\S]*?<\/head>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 20000);
}

function extractProductImage(html: string, pageUrl: string): string | null {
  const base = new URL(pageUrl);

  // 1. schema.org Product image (most reliable for product pages)
  const schemaMatch = html.match(/"@type"\s*:\s*"Product"[\s\S]{0,2000}?"image"\s*:\s*"([^"]+)"/);
  if (schemaMatch?.[1]) return resolveUrl(schemaMatch[1], base);

  const schemaArrMatch = html.match(/"@type"\s*:\s*"Product"[\s\S]{0,2000}?"image"\s*:\s*\[([^\]]+)\]/);
  if (schemaArrMatch) {
    const urlMatch = schemaArrMatch[1].match(/"(https?:\/\/[^"]+\.(jpg|jpeg|png|webp)[^"]*)"/i);
    if (urlMatch?.[1]) return resolveUrl(urlMatch[1], base);
  }

  // 2. og:image — but only if URL suggests it's a product (not generic/logo)
  const ogMatch = html.match(/property=["']og:image["'][^>]*content=["']([^"']+)["']/i)
    ?? html.match(/content=["']([^"']+)["'][^>]*property=["']og:image["']/i);
  if (ogMatch?.[1]) {
    const ogUrl = resolveUrl(ogMatch[1], base);
    // Skip if URL contains logo/brand/hero/banner keywords
    if (ogUrl && !/logo|brand|hero|banner|header|icon|favicon/i.test(ogUrl)) {
      return ogUrl;
    }
  }

  // 3. Look for img tags with product-related alt text or src patterns
  const imgPattern = /<img[^>]+(?:src|data-src)=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["'][^>]*(?:alt=["']([^"']{3,80})["'])?[^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = imgPattern.exec(html)) !== null) {
    const src = m[1];
    const alt = (m[3] ?? "").toLowerCase();
    // Prefer images with product-related alt text
    if (/product|item|model|sensor|device|pump|valve|controller|meter|switch/i.test(alt)) {
      const resolved = resolveUrl(src, base);
      if (resolved && !/logo|icon|favicon|avatar|banner/i.test(resolved)) return resolved;
    }
  }

  // 4. First large image that isn't obviously a logo
  imgPattern.lastIndex = 0;
  while ((m = imgPattern.exec(html)) !== null) {
    const src = m[1];
    if (!/logo|icon|favicon|avatar|banner|header|sprite/i.test(src)) {
      const resolved = resolveUrl(src, base);
      if (resolved) return resolved;
    }
  }

  return null;
}

function extractPdfLinks(html: string, pageUrl: string): string[] {
  const base = new URL(pageUrl);
  const found = new Set<string>();

  // Find all href links to PDFs
  const hrefPattern = /href=["']([^"']*\.pdf[^"']*)["']/gi;
  let m: RegExpExecArray | null;
  while ((m = hrefPattern.exec(html)) !== null) {
    const resolved = resolveUrl(m[1], base);
    if (resolved) found.add(resolved);
  }

  // Also look for PDF URLs in text (some pages embed them in JS/data)
  const urlPattern = /https?:\/\/[^\s"'<>]+\.pdf(?:\?[^\s"'<>]*)?/gi;
  while ((m = urlPattern.exec(html)) !== null) {
    found.add(m[0]);
  }

  // Prioritise manuals/datasheets/instructions over other PDFs
  const priority = [...found].filter(u =>
    /manual|datasheet|data.sheet|instruction|technical|catalogue|catalog|spec|certificate|brochure/i.test(u)
  );
  const rest = [...found].filter(u => !priority.includes(u));

  return [...priority, ...rest].slice(0, 10);
}

function resolveUrl(href: string, base: URL): string | null {
  try {
    return new URL(href, base).href;
  } catch {
    return null;
  }
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const url = searchParams.get("url");

  if (!url) {
    return Response.json({ error: "url is required" }, { status: 400 });
  }

  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": "Mozilla/5.0 (compatible; MIA-DPP/1.0; +https://mia-dpp.vercel.app)",
        Accept: "text/html,application/xhtml+xml",
      },
      signal: AbortSignal.timeout(12000),
    });

    if (!res.ok) {
      return Response.json({ error: `Could not fetch page (HTTP ${res.status})` }, { status: 502 });
    }

    const html = await res.text();
    const titleMatch = html.match(/<title[^>]*>([^<]+)<\/title>/i);
    const title = titleMatch?.[1]?.trim().replace(/\s+/g, " ") ?? "";

    const text = stripHtml(html);
    const productImageUrl = extractProductImage(html, url);
    const pdfLinks = extractPdfLinks(html, url);

    return Response.json({ text, title, url, productImageUrl, pdfLinks });
  } catch (err) {
    return Response.json(
      { error: err instanceof Error ? err.message : "Failed to fetch URL" },
      { status: 502 }
    );
  }
}
