import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Aletheia — Misinformation Detection",
  description: "AI-powered platform for detecting misinformation, deepfakes, and bot accounts",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased">{children}</body>
    </html>
  );
}
