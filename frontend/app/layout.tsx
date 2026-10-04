import type { Metadata } from "next";
import { Geist, Geist_Mono, Instrument_Serif } from "next/font/google";
import "./globals.css";
import { SiteHeader } from "@/components/site-header";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });
const serif = Instrument_Serif({ variable: "--font-serif", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });

export const metadata: Metadata = {
  title: { default: "SIGNAL — Content intelligence", template: "%s · SIGNAL" },
  description: "Every post becomes data for the next decision. Understand, decide, experiment, learn.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} ${serif.variable}`}>
      <body className="min-h-screen">
        <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-50 focus:bg-ink focus:px-3 focus:py-2 focus:text-paper">
          Skip to content
        </a>
        <SiteHeader />
        <main id="main" className="mx-auto w-full max-w-[1240px] px-5 pb-24 pt-8 sm:px-8">
          {children}
        </main>
        <footer className="mx-auto max-w-[1240px] px-5 pb-10 sm:px-8">
          <div className="rule pt-4 text-xs text-mute">
            SIGNAL reads patterns in your history. They are associations, not proof of cause. Run an experiment to find out.
          </div>
        </footer>
      </body>
    </html>
  );
}
