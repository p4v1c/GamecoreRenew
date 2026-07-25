import React from 'react'

/**
 * The project had no error boundary at all: any React throw produced a white
 * screen. That was survivable while every component was ours — it stops being
 * survivable once a theme runs third-party JS on a TV with no pointer.
 *
 * Two uses:
 *   · one per theme surface, so a broken screen falls back to the default one
 *     instead of taking the whole UI down;
 *   · one around the app, as the last net.
 */
interface Props {
  children: React.ReactNode
  /** Rendered instead of the children once something threw. */
  fallback: React.ReactNode
  /** Reported to the theme layer so it can record the crash and refuse to reload. */
  onError?: (error: Error) => void
  /** Changing this remounts the boundary — used to retry after a theme switch. */
  resetKey?: string
}

interface State { failed: boolean }

export default class ErrorBoundary extends React.Component<Props, State> {
  state: State = { failed: false }

  static getDerivedStateFromError(): State {
    return { failed: true }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[gamecore] render error caught by boundary:', error, info.componentStack)
    this.props.onError?.(error)
  }

  componentDidUpdate(prev: Props) {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) {
      this.setState({ failed: false })
    }
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}
