import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

const envDir = fileURLToPath(new URL('../..', import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, envDir, '')

    return {
        envDir,
        plugins: [react(), tailwindcss()],
        resolve: {
            alias: {
                '@components': fileURLToPath(new URL('./src/components', import.meta.url)),
                '@utils': fileURLToPath(new URL('./src/utils', import.meta.url)),
                '@queries': fileURLToPath(new URL('./src/queries', import.meta.url)),
                '@pages': fileURLToPath(new URL('./src/pages', import.meta.url)),
                '@styles': fileURLToPath(new URL('./src/styles', import.meta.url)),
            },
        },
        server: {
            // Mirror the Nginx /api proxy so the app always calls a same-origin /api
            proxy: {
                '/api': env.API_PROXY_TARGET || 'http://localhost:8000',
            },
        },
    }
})
