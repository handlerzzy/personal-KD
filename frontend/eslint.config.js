import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import pluginVue from 'eslint-plugin-vue'

export default [
  { ignores: ['dist/', 'node_modules/'] },
  js.configs.recommended,
  {
    plugins: { '@typescript-eslint': tseslint.plugin },
    languageOptions: {
      parser: tseslint.parser,
      parserOptions: { sourceType: 'module' },
    },
  },
  ...pluginVue.configs['flat/recommended'].map(c => ({
    ...c,
    files: ['**/*.vue'],
    plugins: { ...c.plugins, '@typescript-eslint': tseslint.plugin },
  })),
  {
    files: ['**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    rules: {
      'no-undef': 'off',
      'no-unused-vars': 'off',
      'no-unused-expressions': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'vue/multi-word-component-names': 'off',
      'vue/max-attributes-per-line': 'off',
      'vue/html-closing-bracket-spacing': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/html-indent': 'off',
      'vue/attributes-order': 'off',
      'vue/component-definition-name-casing': 'off',
      'no-console': 'off',
    },
  },
  {
    files: ['**/*.ts'],
    rules: {
      'no-undef': 'off',
      'no-unused-vars': 'off',
      '@typescript-eslint/no-explicit-any': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
      'no-console': 'off',
    },
  },
]
