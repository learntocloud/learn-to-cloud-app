import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { Navbar } from "@/components/navbar";
import { Footer } from "@/components/footer";
import { AppInsightsProvider } from "@/components/app-insights-provider";
import { CelebrationProvider } from "@/components/celebration-provider";
import "./globals.css";

// Optimize fonts: use swap to prevent FOIT (Flash of Invisible Text)
// and preload to start font download early
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
  display: "swap", // Show fallback font immediately, swap when loaded
  preload: true,
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
  display: "swap",
  preload: false, // Don't preload mono font - not critical for initial render
});

export const metadata: Metadata = {
  title: "Learn to Cloud",
  description: "Track your progress through the Learn to Cloud guide",
  icons: {
    icon: "/favicon.svg",
  },
};

// Viewport configuration for better mobile performance
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#3b82f6",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body
          className={`${geistSans.variable} ${geistMono.variable} antialiased bg-gray-50`}
        >
          <AppInsightsProvider>
            <CelebrationProvider>
              <div className="min-h-screen flex flex-col">
                <Navbar />
                <main className="flex-1">{children}</main>
                <Footer />
              </div>
            </CelebrationProvider>
          </AppInsightsProvider>
        </body>
      </html>
    </ClerkProvider>
  );
}
