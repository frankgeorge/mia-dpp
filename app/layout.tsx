import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MIA - Digital Product Passports for Mittelstand manufacturers",
  description:
    "Turn the product data you already have into a standards-compliant Digital Product Passport. Agents do the mapping. You approve every decision.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  );
}
