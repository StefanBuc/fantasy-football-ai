import { useSyncExternalStore } from 'react'

function subscribe(listener: () => void) {
  window.addEventListener('popstate', listener)
  return () => window.removeEventListener('popstate', listener)
}

export function useSitePath() {
  return useSyncExternalStore(subscribe, () => window.location.pathname, () => '/')
}

export function navigate(to: string, replace = false) {
  if (replace) window.history.replaceState(null, '', to)
  else window.history.pushState(null, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.requestAnimationFrame(() => {
    if (window.location.hash) document.getElementById(window.location.hash.slice(1))?.scrollIntoView()
    else window.scrollTo({ top: 0 })
  })
}
