import sql from "@/lib/db";

export const runtime = "nodejs";

// GET /api/passports/thread/[id]/download — download the AAS JSON for a passport
export async function GET(_req: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;

  const rows = await sql`
    SELECT product_name, aas_json FROM passports WHERE thread_id = ${id} LIMIT 1
  `;

  if (!rows[0]) {
    return Response.json({ error: "Passport not found" }, { status: 404 });
  }

  const { product_name, aas_json } = rows[0];
  if (!aas_json) {
    return Response.json({ error: "No AAS data available for this passport" }, { status: 404 });
  }

  const filename = `${String(product_name).replace(/[^a-z0-9]/gi, "_").toLowerCase()}-dpp.json`;
  return new Response(JSON.stringify(aas_json, null, 2), {
    headers: {
      "Content-Type": "application/json",
      "Content-Disposition": `attachment; filename="${filename}"`,
    },
  });
}
