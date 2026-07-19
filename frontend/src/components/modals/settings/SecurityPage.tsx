import { useState, useEffect, useRef } from 'react'
import { Overlay, BackHeader } from '../../ui'
import { VirtualKeyboard } from '../../ui/VirtualKeyboard'
import { api } from '../../../api'
import { onGp } from '../../../hooks/useGamepad'
import { useSubPageGamepad } from './useSubPageGamepad'
import QRCode from 'qrcode'

// Password change happens same-origin against localhost:8765 — the TV is
// trusted (loopback), but the current password is still required so a guest
// with the remote can't silently lock the owner out.
type KbStep = null | 'current' | 'new' | 'confirm'

export function SecurityPage({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const [kbStep, setKbStep]     = useState<KbStep>(null)
  const [currentPwd, setCurrentPwd] = useState('')
  const [newPwd, setNewPwd]     = useState('')
  const [busy, setBusy]         = useState(false)
  const [msg, setMsg]           = useState('')
  const [msgError, setMsgError] = useState(false)
  const [qrData, setQrData]     = useState('')
  const [caUrl, setCaUrl]       = useState('')

  const busyRef = useRef(busy)
  useEffect(() => { busyRef.current = busy }, [busy])

  useEffect(() => {
    api.sysinfo().then(si => {
      const url = `https://${si.ip}:8443/gc/ca.crt`
      setCaUrl(url)
      QRCode.toDataURL(url, { width: 220, margin: 1, color: { dark: '#000000', light: '#ffffff' } })
        .then(setQrData)
        .catch(() => {})
    }).catch(() => {})
  }, [])

  useSubPageGamepad(kbStep ? () => setKbStep(null) : onBack, onClose, true)

  useEffect(() => {
    if (kbStep) return
    const off = onGp('gp:confirm', () => { if (!busyRef.current) startChange() })
    return () => off()
  }, [kbStep])

  const startChange = () => { setMsg(''); setKbStep('current') }

  const doChange = async (current: string, next: string) => {
    setKbStep(null)
    setBusy(true); setMsg('Changing password…'); setMsgError(false)
    try {
      const r = await api.auth.changePassword(current, next)
      if (r.ok) {
        setMsg('Password changed — every web session has been logged out.')
        setMsgError(false)
      } else {
        setMsg(
          r.error === 'bad_password' ? 'Current password is wrong.' :
          r.error === 'too_many_attempts' ? `Too many attempts — retry in ${r.retry_in ?? 'a few'} s.` :
          r.error === 'empty_password' ? 'Empty password refused.' :
          'Password change failed.',
        )
        setMsgError(true)
      }
    } catch {
      setMsg('Password change failed.'); setMsgError(true)
    }
    setBusy(false)
  }

  if (kbStep) {
    const titles: Record<Exclude<KbStep, null>, string> = {
      current: 'Current password',
      new:     'New password',
      confirm: 'Confirm new password',
    }
    return (
      <Overlay onClose={onClose}>
        <BackHeader label="SECURITY" onBack={() => setKbStep(null)} />
        <VirtualKeyboard
          title={titles[kbStep]}
          password
          onConfirm={value => {
            if (kbStep === 'current') { setCurrentPwd(value); setKbStep('new') }
            else if (kbStep === 'new') {
              if (!value) { setMsg('Empty password refused.'); setMsgError(true); setKbStep(null); return }
              setNewPwd(value); setKbStep('confirm')
            } else {
              if (value !== newPwd) { setMsg('Passwords differ — nothing changed.'); setMsgError(true); setKbStep(null); return }
              doChange(currentPwd, value)
            }
          }}
          onCancel={() => setKbStep(null)}
        />
      </Overlay>
    )
  }

  return (
    <Overlay onClose={onClose}>
      <BackHeader label="SECURITY" onBack={onBack} />

      {/* Web password */}
      <div
        onClick={() => { if (!busy) startChange() }}
        style={{
          display: 'flex', alignItems: 'center', gap: 14, padding: '16px 18px',
          borderRadius: 12, cursor: busy ? 'default' : 'pointer', marginBottom: 14,
          background: 'rgba(124,58,237,0.15)', border: '1px solid rgba(124,58,237,0.4)',
          opacity: busy ? 0.6 : 1,
        }}
      >
        <span style={{ fontSize: 24 }}>🔑</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Change web password</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginTop: 3 }}>
            Shared login for https://…:8443 — changing it logs every device out
          </div>
        </div>
        <div style={{ color: 'rgba(255,255,255,0.25)', fontSize: 20 }}>›</div>
      </div>

      {msg && (
        <div style={{
          fontSize: 13, marginBottom: 14, padding: '9px 12px', borderRadius: 8,
          background: msgError ? 'rgba(239,68,68,0.08)' : 'rgba(74,222,128,0.08)',
          color: msgError ? '#f87171' : '#4ade80', fontWeight: 600,
        }}>
          {busy ? '⏳ ' : ''}{msg}
        </div>
      )}

      {/* HTTPS certificate */}
      <div style={{
        padding: '16px 18px', borderRadius: 12,
        background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.07)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: 24 }}>📜</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>HTTPS certificate (CA)</div>
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.4)', marginTop: 3 }}>
              Scan with your phone/PC and install the certificate once — no more browser warning.
            </div>
          </div>
        </div>
        {qrData && (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: 14, gap: 8 }}>
            <img src={qrData} alt="CA QR code" style={{ width: 180, height: 180, borderRadius: 8, background: '#fff', padding: 6 }} />
            <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', fontFamily: 'monospace' }}>{caUrl}</div>
          </div>
        )}
        {!qrData && caUrl && (
          <div style={{ marginTop: 12, fontSize: 12, color: 'rgba(255,255,255,0.45)', fontFamily: 'monospace', textAlign: 'center' }}>{caUrl}</div>
        )}
      </div>

      <div style={{ marginTop: 12, textAlign: 'center', fontSize: 10, color: 'rgba(255,255,255,0.18)', letterSpacing: 1 }}>
        ✕ Change password · ○ Back
      </div>
    </Overlay>
  )
}
