// ESLint en modo informe (auditoría 2026-11-15): `npm run lint`.
// Reglas recomendadas de JS y TypeScript más las dos reglas clásicas de hooks de React.
// `no-explicit-any` queda como aviso: hay ~530 usos heredados que se irán quitando.
import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['src/**/*.{ts,tsx}'],
    languageOptions: { ecmaVersion: 2022, globals: globals.browser },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-explicit-any': 'warn',
      // Convención ya aceptada por tsconfig: un parámetro con "_" se ignora a propósito.
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      // catch {} vacío: p. ej. el logout cierra la sesión local aunque falle la llamada.
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
)
