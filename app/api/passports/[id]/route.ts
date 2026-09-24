import sql from "@/lib/db";

export const runtime = "nodejs";

// GET /api/passports/[id] — public, no auth required
export async function GET(
  _req: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;

  const rows = await sql`
    SELECT id, product_name, submodel, status, qr_code_b64, passport_url, aas_json, created_at
    FROM passports
    WHERE id = ${id}
    LIMIT 1
  `;

  if (!rows[0]) {
    return Response.json({ error: "Passport not found" }, { status: 404 });
  }

  return Response.json(rows[0]);
}
