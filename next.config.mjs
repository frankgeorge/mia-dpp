/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // pdfkit uses Node.js package subpath imports (#standard-fonts/*, #fs, etc.)
  // which break when Next.js bundles the package. Marking it as external tells
  // Next.js to leave it in node_modules and let Node.js resolve it natively.
  serverExternalPackages: ["pdfkit"],
  outputFileTracingIncludes: {
    "/api/passports/thread/[id]/download": [
      "./node_modules/pdfkit/**/*",
    ],
  },
};
export default nextConfig;
