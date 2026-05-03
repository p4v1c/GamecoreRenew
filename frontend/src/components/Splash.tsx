import { useEffect } from 'react'
import { motion } from 'framer-motion'

interface Props { onDone: () => void }

export default function Splash({ onDone }: Props) {
  useEffect(() => {
    const t = setTimeout(onDone, 3200)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <motion.div
      initial={{ opacity: 1 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.6, ease: 'easeInOut' }}
      style={{
        position: 'fixed', inset: 0, zIndex: 9000,
        background: '#06060e',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column',
      }}
    >
      {/* Ambient glows */}
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden', pointerEvents: 'none' }}>
        <div style={{ position: 'absolute', top: '30%', left: '10%', width: 500, height: 500, borderRadius: '50%', background: 'rgba(220,38,38,0.06)', filter: 'blur(100px)' }} />
        <div style={{ position: 'absolute', top: '25%', right: '10%', width: 500, height: 500, borderRadius: '50%', background: 'rgba(29,78,216,0.07)', filter: 'blur(100px)' }} />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.7, ease: 'easeOut' }}
        style={{ position: 'relative' }}
      >
        <div style={{
          fontSize: 72, fontWeight: 900, letterSpacing: 12,
          background: 'linear-gradient(90deg, #dc2626 0%, #ffffff 45%, #1d4ed8 100%)',
          WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
          textTransform: 'uppercase', lineHeight: 1,
          fontFamily: "'Outfit', sans-serif",
        }}>
          GameCore
        </div>
      </motion.div>
    </motion.div>
  )
}
