import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Forge Console",
  description: "Forge enterprise mission control surface",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
