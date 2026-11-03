import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Small data-loading hook: keeps loading/error/data in one place and exposes a
 * reload() for the "Re-run" style refresh buttons.
 */
export function useFetch(loader, deps = []) {
  const [state, setState] = useState({ loading: true, error: null, data: null })
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)
  loaderRef.current = loader

  useEffect(() => {
    let alive = true
    setState((prev) => ({ ...prev, loading: true, error: null }))
    Promise.resolve()
      .then(() => loaderRef.current())
      .then((data) => {
        if (alive) setState({ loading: false, error: null, data })
      })
      .catch((err) => {
        if (alive) setState({ loading: false, error: err.message || String(err), data: null })
      })
    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nonce, ...deps])

  const reload = useCallback(() => setNonce((n) => n + 1), [])
  return { ...state, reload }
}
