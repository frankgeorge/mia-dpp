import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
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
    <ClerkProvider afterSignOutUrl="/">
      <html lang="en">
        <head>
          <script
            type="text/javascript"
            dangerouslySetInnerHTML={{
              __html: `(function(c,l,a,r,i,t,y){c[a]=c[a]||function(){(c[a].q=c[a].q||[]).push(arguments)};t=l.createElement(r);t.async=1;t.src="https://www.clarity.ms/tag/"+i;y=l.getElementsByTagName(r)[0];y.parentNode.insertBefore(t,y);})(window,document,"clarity","script","yozuy0bes5");`,
            }}
          />
        </head>
        <body className="font-sans antialiased">{children}</body>
      </html>
    </ClerkProvider>
  );
}
