import type { Metadata } from "next";
import type { ReactNode } from "react";

import { env } from "@/config/env";
import { AuthProvider } from "@/contexts/AuthContext";

export const metadata: Metadata = {
  title: env.appName,
  description: "AI-powered Industrial Intelligence Platform",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
