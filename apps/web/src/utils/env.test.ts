import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadEnv(apiUrl: string) {
    vi.stubEnv('VITE_API_URL', apiUrl)
    vi.resetModules()
    return (await import('./env')).env
}

describe('env', () => {
    afterEach(() => {
        vi.unstubAllEnvs()
    })

    it('defaults VITE_API_URL to the same-origin proxy when empty', async () => {
        expect((await loadEnv('')).VITE_API_URL).toBe('/api')
    })

    it('keeps VITE_API_URL when set', async () => {
        expect((await loadEnv('https://api.example.com')).VITE_API_URL).toBe(
            'https://api.example.com',
        )
    })
})
