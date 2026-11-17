import { Component, type ReactNode } from 'react'

type Props = { fallback: ReactNode; children: ReactNode }

/** Catches a failed lazy load or an unavailable WebGL context. */
export class ViewerErrorBoundary extends Component<Props, { failed: boolean }> {
    state = { failed: false }

    static getDerivedStateFromError() {
        return { failed: true }
    }

    render() {
        return this.state.failed ? this.props.fallback : this.props.children
    }
}
