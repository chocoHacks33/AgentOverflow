import type { Metadata, Viewport } from 'next'
import { Space_Grotesk, Exo_2 } from 'next/font/google'

import './globals.css'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  variable: '--font-space-grotesk',
  display: 'swap',
})

const exo2 = Exo_2({
  subsets: ['latin'],
  variable: '--font-exo2',
  display: 'swap',
})

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
    <html lang="en" className={`${spaceGrotesk.variable} ${exo2.variable}`}>
      <body className="font-sans antialiased">{children}</body>
    </html>
  )
}
