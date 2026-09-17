import { getSession, respondToSession } from "@/lib/session";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: Promise<{ token: string }> }
) {
  const { token } = await params;
  const session = getSession(token);

  if (!session) {
    return Response.json(
      { error: "Session not found or expired." },
      { status: 404 }
    );
  }

  return Response.json({
    productName: session.productName,
    productUrl: session.productUrl,
    gaps: session.gaps,
    branding: session.branding ?? null,
    responded: !!session.response,
    response: session.response ?? null,
    respondedAt: session.respondedAt ?? null,
  });
}

export async function POST(
  req: Request,
  { params }: { params: Promise<{ token: string }> }
) {
  const { token } = await params;

  let body: { response?: Record<string, string> };
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body." }, { status: 400 });
  }

  const response = body.response ?? {};
  if (Object.keys(response).length === 0) {
    return Response.json(
      { error: "response object must contain at least one field." },
      { status: 400 }
    );
  }

  const ok = respondToSession(token, response);
  if (!ok) {
    return Response.json(
      { error: "Session not found or expired." },
      { status: 404 }
    );
  }

  return Response.json({ success: true });
}
