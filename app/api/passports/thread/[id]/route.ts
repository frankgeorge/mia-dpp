import sql from "@/lib/db";

export const runtime = "nodejs";

// GET /api/passports/thread/[id] — public endpoint to fetch a passport by thread_id
// Used by the /passport/[id] page to render the AAS data without auth
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const rows = await sql`
    SELECT id, thread_id, product_name, submodel, status,
           qr_code_b64, passport_url, aas_json, product_image_url, created_at, updated_at
    FROM passports
    WHERE thread_id = ${id}
    LIMIT 1
  `;

  if (!rows[0]) {
    return Response.json({ error: "Passport not found" }, { status: 404 });
  }

  return Response.json(rows[0]);
}
