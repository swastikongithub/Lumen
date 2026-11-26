import prettier from 'eslint-config-prettier';
import path from 'node:path';
import js from '@eslint/js';
import svelte from 'eslint-plugin-svelte';
import { defineConfig, includeIgnoreFile } from 'eslint/config';
import globals from 'globals';

const gitignorePath = path.resolve(import.meta.dirname, '.gitignore');

export default defineConfig([
	includeIgnoreFile(gitignorePath),
	js.configs.recommended,
	svelte.configs.recommended,
	prettier,
	svelte.configs.prettier,
	{
		languageOptions: {
			globals: {
				...globals.browser,
				...globals.node,
				// Injected by Vite's `define` (vite.config.js).
				__APP_VERSION__: 'readonly'
			}
		}
	},
	{
		// Svelte compiles *.svelte.test.js with runes, so a component test can pass $state props.
		files: ['**/*.svelte.test.js'],
		languageOptions: { globals: { $state: 'readonly', $derived: 'readonly' } }
	},
	{
		rules: {
			'svelte/button-has-type': 'error',
			// Parameters that start with _ document an argument a function ignores on purpose.
			'no-unused-vars': ['error', { argsIgnorePattern: '^_' }]
		}
	}
]);
