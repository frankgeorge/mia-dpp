import { auth } from "@clerk/nextjs/server";
import { createServiceClient, PRODUCT_IMAGES_BUCKET } from "@/lib/supabase";

export const runtime = "nodejs";

// POST /api/upload-image (multipart FormData — field name: "file")
// Uploads image to Supabase Storage, returns { url: string }
export async function POST(req: Request) {
  const { userId } = await auth();
  if (!userId) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const form = await req.formData();
  const file = form.get("file");

  if (!(file instanceof Blob)) {
    return Response.json({ error: "file is required" }, { status: 400 });
  }

  const mimeType = file.type || "image/jpeg";
  const ext = mimeType.split("/")[1]?.replace("jpeg", "jpg") ?? "jpg";
  const filename = `${userId}/${Date.now()}.${ext}`;

  const buffer = Buffer.from(await file.arrayBuffer());

  const supabase = createServiceClient();
  const { error } = await supabase.storage
    .from(PRODUCT_IMAGES_BUCKET)
    .upload(filename, buffer, {
      contentType: mimeType,
      upsert: false,
    });

  if (error) {
    return Response.json({ error: error.message }, { status: 500 });
  }

  const { data } = supabase.storage
    .from(PRODUCT_IMAGES_BUCKET)
    .getPublicUrl(filename);

  return Response.json({ url: data.publicUrl });
}
