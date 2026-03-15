import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Second Brain",
  description: "Agentic Knowledge Hub built with Next.js and FastAPI",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">
        {children}
      </body>
    </html>
  );
}
