"use client"

import { useEffect, useRef, useState } from "react"

interface CountUpOnScrollProps {
  /** Target number to count up to */
  target: number
  /** Optional suffix after the number (e.g. "kg", "k", "%") */
  suffix?: string
  /** Duration of the count animation in ms. Default 1200 = quick. */
  duration?: number
  /** Decimal places for display. Default 0. */
  decimals?: number
  /** When to trigger (0–1). Default 0.2 = when 20% visible */
  threshold?: number
  /** Optional className for the wrapper span */
  className?: string
}

function easeOutQuart(t: number): number {
  return 1 - (1 - t) ** 4
}

export function CountUpOnScroll({
  target,
  suffix = "",
  duration = 1200,
  decimals = 0,
  threshold = 0.2,
  className = "",
}: CountUpOnScrollProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const [displayValue, setDisplayValue] = useState(0)
  const [hasAnimated, setHasAnimated] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el || hasAnimated) return

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries
        if (!entry.isIntersecting) return

        setHasAnimated(true)
        const startTime = performance.now()

        const tick = (now: number) => {
          const elapsed = now - startTime
          const progress = Math.min(elapsed / duration, 1)
          const eased = easeOutQuart(progress)
          const current = target * eased

          setDisplayValue(current)

          if (progress < 1) {
            requestAnimationFrame(tick)
          } else {
            setDisplayValue(target)
          }
        }

        requestAnimationFrame(tick)
      },
      { threshold, rootMargin: "0px 0px -30px 0px" }
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [target, duration, threshold, hasAnimated])

  const formatted =
    decimals > 0
      ? displayValue.toFixed(decimals)
      : Math.round(displayValue).toLocaleString()

  return (
    <span ref={ref} className={className}>
      {formatted}
      {suffix}
    </span>
  )
}
