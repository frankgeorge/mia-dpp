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

function isLikelyLogo(url: string): boolean {
  // URL path contains obvious logo/brand/social-share indicators
  return /logo|brand|hero|banner|header|icon|favicon|og[-_]image|social|share|meta[-_]img|default[-_]img|placeholder/i.test(url);
}

function extractProductImage(html: string, pageUrl: string): string | null {
  const base = new URL(pageUrl);

  // 1. schema.org Product image — most reliable, always a real product photo
  const schemaMatch = html.match(/"@type"\s*:\s*"Product"[\s\S]{0,3000}?"image"\s*:\s*"([^"]+)"/);
  if (schemaMatch?.[1]) return resolveUrl(schemaMatch[1], base);

  const schemaArrMatch = html.match(/"@type"\s*:\s*"Product"[\s\S]{0,3000}?"image"\s*:\s*\[([^\]]+)\]/);
  if (schemaArrMatch) {
    const urlMatch = schemaArrMatch[1].match(/"(https?:\/\/[^"]+\.(jpg|jpeg|png|webp)[^"]*)"/i);
    if (urlMatch?.[1]) return resolveUrl(urlMatch[1], base);
  }

  // 2. img inside known product-image containers (e-commerce / product page patterns)
  const containerPatterns = [
    // data attributes used by product galleries
    /data-zoom(?:-image|-src)?=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["']/gi,
    /data-image=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["']/gi,
    /data-src=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["']/gi,
    // product image containers (WooCommerce, Shopify, typical B2B sites)
    /<(?:div|figure|section)[^>]*class=["'][^"']*(?:product[-_]image|product[-_]photo|product[-_]gallery|pdp[-_]image|main[-_]image|item[-_]image)[^"']*["'][^>]*>[\s\S]{0,500}?<img[^>]+src=["']([^"']+)["']/gi,
  ];

  for (const pattern of containerPatterns) {
    pattern.lastIndex = 0;
    const m = pattern.exec(html);
    if (m) {
      // last capture group is the URL
      const candidate = resolveUrl(m[m.length - 1], base);
      if (candidate && !isLikelyLogo(candidate)) return candidate;
    }
  }

  // 3. img tags with product-signalling alt text
  const imgPattern = /<img[^>]+src=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["'][^>]*alt=["']([^"']{3,120})["'][^>]*>/gi;
  let m: RegExpExecArray | null;
  while ((m = imgPattern.exec(html)) !== null) {
    const src = m[1];
    const alt = (m[3] ?? "").toLowerCase();
    if (/product|item|model|sensor|device|pump|valve|controller|meter|switch|unit|machine|equipment|instrument|tool|part/i.test(alt)) {
      const resolved = resolveUrl(src, base);
      if (resolved && !isLikelyLogo(resolved)) return resolved;
    }
  }

  // 4. img tags where src path itself suggests a product image
  const imgSrcPattern = /<img[^>]+src=["']([^"']+\.(jpg|jpeg|png|webp)[^"']*)["'][^>]*>/gi;
  imgSrcPattern.lastIndex = 0;
  while ((m = imgSrcPattern.exec(html)) !== null) {
    const src = m[1];
    if (/product|item|catalog|catalogue|article|sku|p[-_]\d|img[-_]\d/i.test(src)) {
      const resolved = resolveUrl(src, base);
      if (resolved && !isLikelyLogo(resolved)) return resolved;
    }
  }

  // 5. og:image — last resort only, og:image is almost always the company's
  //    social-share branding image, not the actual product photo.
  //    Only use it if the URL strongly suggests a product (contains product/item/sku in path)
  const ogMatch =
    html.match(/property=["']og:image["'][^>]*content=["']([^"']+)["']/i) ??
    html.match(/content=["']([^"']+)["'][^>]*property=["']og:image["']/i);
  if (ogMatch?.[1]) {
    const ogUrl = resolveUrl(ogMatch[1], base);
    if (ogUrl && !isLikelyLogo(ogUrl) && /product|item|sku|catalog|p[-_]\d/i.test(ogUrl)) {
      return ogUrl;
    }
  }

  // 6. First non-logo image on the page as absolute last fallback
  imgSrcPattern.lastIndex = 0;
  while ((m = imgSrcPattern.exec(html)) !== null) {
    const src = m[1];
    if (!isLikelyLogo(src) && src.length > 20) {
      const resolved = resolveUrl(src, base);
      if (resolved) return resolved;
    }
  }

  return null;
}

function extractPdfLinks(html: string, pageUrl: string): string[] {
  const base = new URL(pageUrl);
  const found = new Set<string>();

  const hrefPattern = /href=["']([^"']*\.pdf[^"']*)["']/gi;
  let m: RegExpExecArray | null;
  while ((m = hrefPattern.exec(html)) !== null) {
    const resolved = resolveUrl(m[1], base);
    if (resolved) found.add(resolved);
  }

  const urlPattern = /https?:\/\/[^\s"'<>]+\.pdf(?:\?[^\s"'<>]*)?/gi;
  while ((m = urlPattern.exec(html)) !== null) {
    found.add(m[0]);
  }

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
