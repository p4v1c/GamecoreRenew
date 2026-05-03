import { useEffect, useRef } from 'react'
import { onGp } from '../../../hooks/useGamepad'

export function useSubPageGamepad(onBack: () => void, onClose: () => void, enabled = true) {
  const onBackRef  = useRef(onBack)
  const onCloseRef = useRef(onClose)
  useEffect(() => { onBackRef.current  = onBack  }, [onBack])
  useEffect(() => { onCloseRef.current = onClose }, [onClose])

  useEffect(() => {
    if (!enabled) return
    const offs = [
      onGp('gp:back', () => onBackRef.current()),
      onGp('gp:menu', () => onCloseRef.current()),
    ]
    return () => offs.forEach(o => o())
  }, [enabled])
}
