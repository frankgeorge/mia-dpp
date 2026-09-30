import { auth } from "@clerk/nextjs/server";
import { createServiceClient, HANDOVER_DOCS_BUCKET } from "@/lib/supabase";

export const runtime = "nodejs";

const BUCKET = HANDOVER_DOCS_BUCKET;

// POST /api/upload-handover-doc — upload a document to Supabase Storage for Handover Documentation
// Returns { url, fileName } where url is the public download link
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const form = await req.formData();
  const file = form.get("file");

  if (!(file instanceof Blob)) {
    return Response.json({ error: "file is required" }, { status: 400 });
  }

  const fileName = (file as File).name ?? `document-${Date.now()}`;
  const mimeType = file.type || "application/octet-stream";
  const safeName = fileName.replace(/[^a-zA-Z0-9._-]/g, "_");
  const storagePath = `${userId}/${Date.now()}_${safeName}`;

  const buffer = Buffer.from(await file.arrayBuffer());

  const supabase = createServiceClient();

  // Create bucket if it doesn't exist (idempotent — no-op if already exists)
  await supabase.storage.createBucket(BUCKET, { public: true }).catch(() => {});

  const { error } = await supabase.storage
    .from(BUCKET)
    .upload(storagePath, buffer, {
      contentType: mimeType,
      upsert: false,
    });

  if (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }

  const { data } = supabase.storage.from(BUCKET).getPublicUrl(storagePath);

  return Response.json({ url: data.publicUrl, fileName });
}
