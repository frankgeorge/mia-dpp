import { db } from "@/lib/db";
import { passports } from "@/lib/db/schema";
import { eq } from "drizzle-orm";
import type { DppPackage } from "@/lib/standards/types";

export const runtime = "nodejs";

export async function POST(req: Request) {
  const body = await req.json();
  const dpp: DppPackage = body.dpp;

  if (!dpp?.passportId) {
    return Response.json({ error: "Invalid DPP payload." }, { status: 400 });
  }

  await db
    .insert(passports)
    .values({
      passportId: dpp.passportId,
      productName: dpp.productName ?? "Unknown",
      productUrl: null,
      submodelId: "nameplate",
      status: "complete",
      submodel: dpp as any,
    })
    .onConflictDoUpdate({
      target: passports.passportId,
      set: {
        submodel: dpp as any,
        status: "complete",
        updatedAt: new Date(),
      },
    });

  const baseUrl =
    process.env.NEXT_PUBLIC_BASE_URL ?? "https://mia-dpp.vercel.app";
  const url = `${baseUrl}/passport/${encodeURIComponent(dpp.passportId)}`;

  return Response.json({ passportId: dpp.passportId, url });
}

export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const id = searchParams.get("id");

  if (!id) {
    return Response.json({ error: "id query param required." }, { status: 400 });
  }

  const rows = await db
    .select()
    .from(passports)
    .where(eq(passports.passportId, id))
    .limit(1);

  if (!rows[0]) {
    return Response.json({ error: "Passport not found." }, { status: 404 });
  }

  return Response.json({ dpp: rows[0].submodel, savedAt: rows[0].generatedAt });
}
