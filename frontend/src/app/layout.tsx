import './globals.css';
import React from 'react';

export const metadata = {
  title: 'AGI Screener — Technical Assessment Workspace',
  description: 'AI-Powered role-based candidate screening system',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-[#0b0f19] text-[#f8fafc]">
        {children}
      </body>
    </html>
  );
}
