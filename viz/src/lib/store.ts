import { useSyncExternalStore } from 'react'

/** Minimal external store: get/set/subscribe plus a selector hook. */
export function createStore<T extends object>(initial: T) {
  let state = initial
  const listeners = new Set<() => void>()
  const get = () => state
  const set = (patch: Partial<T> | ((s: T) => Partial<T>)) => {
    const next = typeof patch === 'function' ? patch(state) : patch
    state = { ...state, ...next }
    listeners.forEach((l) => l())
  }
  const subscribe = (l: () => void) => {
    listeners.add(l)
    return () => listeners.delete(l)
  }
  function use(): T
  function use<U>(selector: (s: T) => U): U
  function use<U>(selector?: (s: T) => U) {
    return useSyncExternalStore(subscribe, () => (selector ? selector(state) : state))
  }
  return { get, set, subscribe, use }
}
