import { createSession } from "@/lib/session";
import { NAMEPLATE_ELEMENTS } from "@/lib/standards/idta";
import { buildHtml, buildText } from "@/lib/email";

export const runtime = "nodejs";

interface SendBody {
  contactEmail: string;
  productName: string;
  productUrl: string;
  gaps: string[]; // NAMEPLATE_ELEMENTS names
  branding?: { orgName?: string; logoUrl?: string; brandColor?: string };
}

export async function POST(req: Request) {
  const body: SendBody = await req.json();
  const { contactEmail, productName, productUrl = "", gaps = [], branding } = body;

  if (!contactEmail || !productName || gaps.length === 0) {
    return Response.json(
      { error: "contactEmail, productName, and at least one gap are required." },
      { status: 400 }
    );
  }

  const gapDetails = gaps.map((name) => {
    const el = NAMEPLATE_ELEMENTS.find((e) => e.name === name);
    return { name, hint: el?.hint ?? name, required: el?.required ?? false };
  });

  const token = createSession({
    productName,
    productUrl,
    contactEmail,
    gaps: gapDetails,
    branding,
  });

  const baseUrl =
    process.env.NEXT_PUBLIC_BASE_URL ?? "https://mia-dpp.vercel.app";
  const portalUrl = `${baseUrl}/reply/${token}`;

  const subject = `[MIA-${token.slice(0, 6)}] Missing product data — ${productName}`;
  const emailHtml = buildHtml({ productName, productUrl, gapDetails, portalUrl, token });
  const emailText = buildText({ productName, productUrl, gapDetails, portalUrl, token });

  const resendKey = process.env.RESEND_API_KEY;

  if (resendKey) {
    const r = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${resendKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        from: "MIA <onboarding@resend.dev>",
        to: [contactEmail],
        subject,
        html: emailHtml,
        text: emailText,
      }),
    });

    if (!r.ok) {
      const detail = await r.text().catch(() => "");
      console.error("Resend error", r.status, detail);
      // Fall through — return the draft so the user can send manually
      return Response.json({
        token,
        portalUrl,
        sent: false,
        draft: emailText,
        error: "Email delivery failed — copy the draft below and send manually.",
      });
    }

    return Response.json({ token, portalUrl, sent: true });
  }

  // No Resend key configured — return draft for manual copy-paste
  return Response.json({ token, portalUrl, sent: false, draft: emailText });
}
