import type { Metadata } from "next";
import "@fontsource-variable/inter";
import "@fontsource-variable/jetbrains-mono";
import "./globals.css";
export const dynamic = "force-dynamic";
export const metadata: Metadata = {
  title: "NeuralOps · AI Reliability",
  description:
    "Observe, investigate, and improve the reliability of your AI systems.",
};
export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
