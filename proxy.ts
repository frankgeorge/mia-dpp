import { clerkMiddleware } from "@clerk/nextjs/server";

const PROTECTED_PREFIXES = [
  "/workspace",
  "/dashboard",
  "/settings",
  "/api/email",
  "/api/chat",
  "/api/upload",
  "/api/sap",
];

// Routes that must remain public (direct browser navigation, QR scans, etc.)
const PUBLIC_PREFIXES = [
  "/api/passports/thread/",  // includes /download — must be accessible without session cookie
  "/passport/",
];

export default clerkMiddleware(async (auth, req) => {
  const path = req.nextUrl.pathname;
  if (PUBLIC_PREFIXES.some((prefix) => path.startsWith(prefix))) return;
  if (PROTECTED_PREFIXES.some((prefix) => path.startsWith(prefix))) {
    await auth.protect();
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
    "/__clerk/:path*",
  ],
};
