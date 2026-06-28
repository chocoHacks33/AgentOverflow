"use client"

export function ForestBackground() {
  return (
    <div className="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true">
      <div className="absolute inset-0 bg-[linear-gradient(180deg,hsl(210_33%_98%),hsl(210_24%_96%))]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_16%_10%,hsl(27_90%_52%_/0.14),transparent_28%),radial-gradient(circle_at_82%_4%,hsl(204_100%_40%_/0.12),transparent_30%)]" />
      <div className="absolute inset-0 opacity-[0.28] [background-image:linear-gradient(hsl(214_20%_86%_/0.75)_1px,transparent_1px),linear-gradient(90deg,hsl(214_20%_86%_/0.75)_1px,transparent_1px)] [background-size:32px_32px]" />
      <div className="absolute left-0 top-0 h-1 w-full bg-gradient-to-r from-primary via-[#f6c38a] to-[#0077cc]" />
    </div>
  )
}
