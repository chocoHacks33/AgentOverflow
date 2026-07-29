const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "")

export function apiUrl(pathname: string) {
  const path = pathname.startsWith("/") ? pathname : `/${pathname}`
  return configuredApiUrl ? `${configuredApiUrl}${path}` : `/api${path}`
}
