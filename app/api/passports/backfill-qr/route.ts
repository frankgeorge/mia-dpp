import { auth } from "@clerk/nextjs/server";
import sql from "@/lib/db";

export const runtime = "nodejs";

const API_URL = process.env.NEXT_PUBLIC_MIA_API_URL ?? "";
const BASE_URL =
  process.env.NEXT_PUBLIC_BASE_URL ?? "https://mia-dpp.vercel.app";

// POST /api/passports/backfill-qr
// Silently generates QR codes for any deployed passports that are missing them.
export async function POST() {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const rows = await sql<{ thread_id: string }[]>`
    SELECT thread_id FROM passports
    WHERE user_id = ${userId}
      AND status = 'deployed'
      AND (qr_code_b64 IS NULL OR passport_url IS NULL)
  `;

  if (rows.length === 0) {
    return Response.json({ backfilled: 0, total: 0 });
  }

  let backfilled = 0;

  for (const row of rows) {
    try {
      const res = await fetch(
        `${API_URL}/api/workspaces/${row.thread_id}/deploy`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ passport_base_url: BASE_URL }),
        }
      );
      if (!res.ok) continue;

      const data = (await res.json()) as {
        passport_url?: string;
        qr_code_png_b64?: string;
      };

      if (data.passport_url && data.qr_code_png_b64) {
        await sql`
          UPDATE passports
          SET passport_url = ${data.passport_url},
              qr_code_b64  = ${data.qr_code_png_b64},
              updated_at   = NOW()
          WHERE thread_id = ${row.thread_id}
            AND user_id   = ${userId}
        `;
        backfilled++;
      }
    } catch {
      // Non-blocking — skip failures silently
    }
  }

  return Response.json({ backfilled, total: rows.length });
}
