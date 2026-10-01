/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  // pdfkit reads .afm font metric files at runtime from its data directory.
  // Without this, Next.js serverless on Vercel omits them and pdfkit produces
  // an empty or corrupt PDF response.
  outputFileTracingIncludes: {
    "/api/passports/thread/[id]/download": [
      "./node_modules/pdfkit/js/data/**/*",
      "./node_modules/pdfkit/js/standard-fonts/**/*",
    ],
  },
};
export default nextConfig;
