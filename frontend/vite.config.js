import { readFileSync } from 'node:fs';
import { defineConfig } from 'vitest/config';
import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';

const { version } = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf8'));

export default defineConfig({
	plugins: [
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// SPA mode (SPEC §12): every route falls back to one empty shell, so the same
			// build/ folder works on Cloudflare Pages and inside the Capacitor WebView.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	define: {
		// Sent as X-App-Version (src/lib/session.js).
		__APP_VERSION__: JSON.stringify(version)
	},
	// Component tests mount Svelte components in jsdom, which needs Svelte's browser build.
	resolve: process.env.VITEST ? { conditions: ['browser'] } : undefined,
	test: {
		environment: 'jsdom',
		include: ['src/**/*.test.js'],
		expect: { requireAssertions: true },
		restoreMocks: true,
		unstubGlobals: true
	}
});
