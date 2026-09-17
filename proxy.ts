import { clerkMiddleware } from "@clerk/nextjs/server";

const PROTECTED_PREFIXES = [
  "/workspace",
  "/dashboard",
  "/settings",
  "/api/email",
  "/api/chat",
  "/api/upload",
  "/api/passport",
  "/api/sap",
];

export default clerkMiddleware(async (auth, req) => {
  const path = req.nextUrl.pathname;
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
