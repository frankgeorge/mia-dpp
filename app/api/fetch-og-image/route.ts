export const runtime = "nodejs";

// GET /api/fetch-og-image?url=<product-url>
// Fetches the product page and extracts og:image (or twitter:image fallback).
// Returns { imageUrl: string | null }
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const url = searchParams.get("url");

  if (!url) {
    return Response.json({ error: "url is required" }, { status: 400 });
  }

  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent":
          "Mozilla/5.0 (compatible; MIA-DPP/1.0; +https://mia-dpp.vercel.app)",
        Accept: "text/html",
      },
      signal: AbortSignal.timeout(8000),
    });

    if (!res.ok) {
      return Response.json({ imageUrl: null });
    }

    const html = await res.text();

    // Try og:image first, then twitter:image
    const patterns = [
      /property=["']og:image["'][^>]*content=["']([^"']+)["']/i,
      /content=["']([^"']+)["'][^>]*property=["']og:image["']/i,
      /name=["']twitter:image["'][^>]*content=["']([^"']+)["']/i,
      /content=["']([^"']+)["'][^>]*name=["']twitter:image["']/i,
    ];

    let imageUrl: string | null = null;
    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match?.[1]) {
        imageUrl = match[1];
        break;
      }
    }

    // Resolve relative URLs
    if (imageUrl && !imageUrl.startsWith("http")) {
      const base = new URL(url);
      imageUrl = new URL(imageUrl, base).href;
    }

    return Response.json({ imageUrl });
  } catch {
    return Response.json({ imageUrl: null });
  }
}
