import { useCallback, useEffect, useRef } from 'react'

export type SessionGuard = () => boolean
const activeStandaloneSession = () => true

export function useRequestGeneration(key: string, isSessionCurrent: SessionGuard = activeStandaloneSession): () => SessionGuard {
  const current = useRef({ key, isSessionCurrent, active: true })
  if (current.current.key !== key || current.current.isSessionCurrent !== isSessionCurrent) {
    current.current = { key, isSessionCurrent, active: true }
  }
  useEffect(() => {
    const generation = current.current
    generation.active = true
    return () => { generation.active = false }
  }, [key, isSessionCurrent])
  return useCallback(() => {
    const generation = current.current
    return () => current.current === generation && generation.active && generation.isSessionCurrent()
  }, [])
}
