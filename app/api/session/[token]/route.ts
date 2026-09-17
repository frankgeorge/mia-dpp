import { db } from "@/lib/db";
import { supplierSessions } from "@/lib/db/schema";
import { eq } from "drizzle-orm";

export const runtime = "nodejs";

export async function GET(
  _req: Request,
  { params }: { params: { token: string } }
) {
  const rows = await db
    .select()
    .from(supplierSessions)
    .where(eq(supplierSessions.token, params.token))
    .limit(1);

  const session = rows[0];
  if (!session || new Date(session.expiresAt) < new Date()) {
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
    responded: session.responded,
    response: session.response ?? null,
    respondedAt: session.respondedAt?.toISOString() ?? null,
  });
}

export async function POST(
  req: Request,
  { params }: { params: { token: string } }
) {
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

  const rows = await db
    .select({ token: supplierSessions.token, expiresAt: supplierSessions.expiresAt })
    .from(supplierSessions)
    .where(eq(supplierSessions.token, params.token))
    .limit(1);

  const session = rows[0];
  if (!session || new Date(session.expiresAt) < new Date()) {
    return Response.json(
      { error: "Session not found or expired." },
      { status: 404 }
    );
  }

  await db
    .update(supplierSessions)
    .set({
      response,
      responded: true,
      respondedAt: new Date(),
    })
    .where(eq(supplierSessions.token, params.token));

  return Response.json({ success: true });
}
