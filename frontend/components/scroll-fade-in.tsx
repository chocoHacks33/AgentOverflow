"use client"

import { useEffect, useRef, useState, type ReactNode } from "react"

interface ScrollFadeInProps {
  children: ReactNode
  /** Delay in ms before animating (for stagger) */
  delay?: number
  /** How far from viewport (0–1) to trigger. Default 0.15 = when 15% visible */
  threshold?: number
  /** Optional extra class for the wrapper */
  className?: string
  /** Slight upward motion (true) or fade only (false). Default true */
  slideUp?: boolean
}

export function ScrollFadeIn({
  children,
  delay = 0,
  threshold = 0.15,
  className = "",
  slideUp = true,
}: ScrollFadeInProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [isVisible, setVisible] = useState(false)
  const [motionDisabled, setMotionDisabled] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)")
    if (reducedMotion.matches || !("IntersectionObserver" in window)) {
      setMotionDisabled(reducedMotion.matches)
      setVisible(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries
        if (!entry.isIntersecting) return
        setVisible(true)
        observer.disconnect()
      },
      {
        threshold: Math.min(threshold, 0.05),
        rootMargin: "0px 0px -40px 0px",
      }
    )

    observer.observe(el)
    const fallbackId = window.setTimeout(
      () => setVisible(true),
      Math.max(2500, delay + 1000)
    )

    return () => {
      observer.disconnect()
      window.clearTimeout(fallbackId)
    }
  }, [threshold, delay])

  return (
    <div
      ref={ref}
      className={className}
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible
          ? "translateY(0)"
          : slideUp
            ? "translateY(24px)"
            : "none",
        transition: motionDisabled
          ? "none"
          : `opacity 0.65s cubic-bezier(0.22, 1, 0.36, 1) ${delay}ms, transform 0.65s cubic-bezier(0.22, 1, 0.36, 1) ${delay}ms`,
      }}
    >
      {children}
    </div>
  )
}
