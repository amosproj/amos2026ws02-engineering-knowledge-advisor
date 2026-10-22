import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
    globalIgnores(['dist']),
    {
        files: ['**/*.{ts,tsx}'],
        extends: [
            js.configs.recommended,
            tseslint.configs.recommended,
            reactHooks.configs.flat.recommended,
            reactRefresh.configs.vite,
        ],
        languageOptions: {
            globals: globals.browser,
        },
    },
    {
        // UI library (shadcn pattern): components files intentionally mix component
        // and non-component exports, and upstream code may set state in effects.
        files: ['src/components/**/*.{ts,tsx}'],
        rules: {
            'react-refresh/only-export-components': 'off',
            'react-hooks/set-state-in-effect': 'off',
        },
    },
])
