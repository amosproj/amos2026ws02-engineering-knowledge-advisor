import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
import { defineConfig } from 'vitest/config'

const envDir = fileURLToPath(new URL('../..', import.meta.url))

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
    const env = loadEnv(mode, envDir, '')
    const storageUploadPath = `/storage/${env.S3_BUCKET}`
    // presigned downloads of the 3D models, mirrors the Nginx rule
    const modelDownloadPath = new RegExp(`^/storage/${env.S3_BUCKET}/files/[^/?]+/model\\.glb\\?`)

    return {
        envDir,
        plugins: [
            react(),
            tailwindcss(),
            {
                name: 'allow-long-uploads',
                configureServer(server) {
                    // Node aborts requests not fully received after 300 s, too short for large STEP files
                    if (server.httpServer && 'requestTimeout' in server.httpServer) {
                        server.httpServer.requestTimeout = 0
                    }
                },
            },
        ],
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
            watch: {
                usePolling: env.WEB_PROFILE === 'dev',
            },
            // Mirror the Nginx proxies so the app always calls same-origin /api and /storage
            proxy: {
                '/api': env.WEB_API_PROXY_TARGET || 'http://localhost:8000',
                '/storage': {
                    target: env.WEB_STORAGE_PROXY_TARGET || 'http://localhost:9000',
                    rewrite: (path) => path.replace(/^\/storage/, ''),
                    // a presigned link is signed for the storage's host, which the target is
                    changeOrigin: true,
                    // the link carries the credentials; S3 refuses a second one, e.g. the app's Authorization header
                    configure: (proxy) => {
                        proxy.on('proxyReq', (proxyReq) => {
                            proxyReq.removeHeader('authorization')
                            proxyReq.removeHeader('cookie')
                        })
                    },
                    // Only presigned POST uploads and presigned model downloads may reach object storage
                    bypass: (req) =>
                        (req.method === 'POST' && req.url === storageUploadPath) ||
                        (req.method === 'GET' && modelDownloadPath.test(req.url ?? ''))
                            ? undefined
                            : false,
                },
            },
        },
        test: {
            // Tests must not depend on the developer's .env
            env: { VITE_API_URL: '' },
        },
    }
})
