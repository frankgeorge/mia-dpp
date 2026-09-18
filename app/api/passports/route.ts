import { auth } from "@clerk/nextjs/server";
import sql from "@/lib/db";

export const runtime = "nodejs";

// GET /api/passports — list all passports for the signed-in user
export async function GET() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const rows = await sql`
    SELECT id, thread_id, product_name, submodel, status,
           qr_code_b64, passport_url, basyx_shell_id, created_at, updated_at
    FROM passports
    WHERE user_id = ${userId}
    ORDER BY updated_at DESC
  `;

  return Response.json(rows);
}

// POST /api/passports — upsert a passport record (called after deploy or on save)
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const body = await req.json();
  const {
    thread_id,
    product_name,
    submodel = "IDTA 02006",
    status = "draft",
    qr_code_b64 = null,
    passport_url = null,
    basyx_shell_id = null,
    aas_json = null,
  } = body;

  if (!thread_id || !product_name) {
    return Response.json({ error: "thread_id and product_name are required" }, { status: 400 });
  }

  const rows = await sql`
    INSERT INTO passports (user_id, thread_id, product_name, submodel, status,
                           qr_code_b64, passport_url, basyx_shell_id, aas_json)
    VALUES (${userId}, ${thread_id}, ${product_name}, ${submodel}, ${status},
            ${qr_code_b64}, ${passport_url}, ${basyx_shell_id}, ${aas_json})
    ON CONFLICT (thread_id) DO UPDATE SET
      product_name   = EXCLUDED.product_name,
      status         = EXCLUDED.status,
      qr_code_b64    = COALESCE(EXCLUDED.qr_code_b64, passports.qr_code_b64),
      passport_url   = COALESCE(EXCLUDED.passport_url, passports.passport_url),
      basyx_shell_id = COALESCE(EXCLUDED.basyx_shell_id, passports.basyx_shell_id),
      aas_json       = COALESCE(EXCLUDED.aas_json, passports.aas_json),
      updated_at     = NOW()
    RETURNING *
  `;

  return Response.json(rows[0]);
}
