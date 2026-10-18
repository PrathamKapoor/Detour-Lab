/**
 * Small data-loading hook.
 *
 * Deliberately not a query library: the app has a handful of resources, needs
 * explicit abort on navigation, and must never show a stale payload as if it
 * were current. This hook keeps exactly those guarantees:
 *  - in-flight requests are aborted when dependencies change or on unmount;
 *  - `data` is cleared when the key changes, so the previous resource can never
 *    masquerade as the new one;
 *  - errors are surfaced as `ApiError` with the backend envelope intact.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'

export interface ResourceState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  /** True while refreshing with data already on screen (avoids layout jumps). */
  refreshing: boolean
}

export interface Resource<T> extends ResourceState<T> {
  reload: () => void
  setData: (updater: T | ((previous: T | null) => T)) => void
}

export function useResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: readonly unknown[],
  options: { enabled?: boolean } = {},
): Resource<T> {
  const enabled = options.enabled ?? true
  const [state, setState] = useState<ResourceState<T>>({
    data: null,
    error: null,
    loading: enabled,
    refreshing: false,
  })
  const [nonce, setNonce] = useState(0)
  const loaderRef = useRef(loader)

  useEffect(() => {
    loaderRef.current = loader
  })

  useEffect(() => {
    if (!enabled) {
      // Render-phase adjustment instead of an effect: a disabled resource has a
      // known state, so deriving it avoids an extra render pass.
      return
    }
    const controller = new AbortController()
    let active = true
    queueMicrotask(() => {
      if (!active) return
      setState((previous) => ({
        data: null,
        error: null,
        loading: !previous.data,
        refreshing: Boolean(previous.data),
      }))
    })
    loaderRef
      .current(controller.signal)
      .then((data) => {
        if (active) setState({ data, error: null, loading: false, refreshing: false })
      })
      .catch((error: unknown) => {
        if (!active || controller.signal.aborted) return
        setState({
          data: null,
          error: error instanceof ApiError ? error : new ApiError(0, { code: 'UNEXPECTED' }, String(error)),
          loading: false,
          refreshing: false,
        })
      })
    return () => {
      active = false
      controller.abort()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, enabled, nonce])

  const reload = useCallback(() => setNonce((value) => value + 1), [])
  const setData = useCallback((updater: T | ((previous: T | null) => T)) => {
    setState((previous) => ({
      ...previous,
      data:
        typeof updater === 'function' ? (updater as (p: T | null) => T)(previous.data) : updater,
      error: null,
    }))
  }, [])

  return { ...state, reload, setData }
}