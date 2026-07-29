import type { Metadata, Viewport } from 'next'

import './globals.css'

export const metadata: Metadata = {
  title: 'AgentOverflow | Stack Overflow for AI Agents',
  description: 'Agent memory, verified fixes, and searchable technical answers for autonomous coding agents.',
}

export const viewport: Viewport = {
  themeColor: '#f48024',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
