import * as React from "react"

const MOBILE_BREAKPOINT = 768
const MOBILE_QUERY = `(max-width: ${MOBILE_BREAKPOINT - 1}px)`

function subscribeToMobileChanges(onStoreChange: () => void) {
  const mediaQuery = window.matchMedia(MOBILE_QUERY)
  mediaQuery.addEventListener("change", onStoreChange)
  return () => mediaQuery.removeEventListener("change", onStoreChange)
}

function getMobileSnapshot() {
  return window.matchMedia(MOBILE_QUERY).matches
}

function getMobileServerSnapshot() {
  // Keep server rendering deterministic; React reconciles this with the
  // browser snapshot during hydration.
  return false
}

export function useIsMobile() {
  return React.useSyncExternalStore(
    subscribeToMobileChanges,
    getMobileSnapshot,
    getMobileServerSnapshot
  )
}
