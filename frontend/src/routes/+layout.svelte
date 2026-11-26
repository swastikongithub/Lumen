<script>
	/**
	 * The app shell: header, the one-line disclaimer below 1024 px (from there the header
	 * shows it as a pill), and the page. The shell is one screen tall: the chat scrolls its
	 * own message list and keeps the composer in view; the other pages scroll inside <main>.
	 */
	import '../app.css';
	import { afterNavigate } from '$app/navigation';
	import AppHeader from '#lib/components/AppHeader.svelte';
	import Disclaimer from '#lib/components/Disclaimer.svelte';
	import { menuOpen } from '#lib/stores.js';

	let { children } = $props();

	afterNavigate(() => menuOpen.set(false));
</script>

<div class="app">
	<AppHeader />
	<div class="disclaimer">
		<Disclaimer variant="bar" />
	</div>
	<main id="main">
		{@render children()}
	</main>
</div>

<style>
	.app {
		height: 100dvh;
		display: flex;
		flex-direction: column;
	}

	.disclaimer {
		flex-shrink: 0;
	}

	/* Positioned, so .visually-hidden text in a scrolled page stays inside it. */
	main {
		position: relative;
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}

	@media (min-width: 1024px) {
		.disclaimer {
			display: none;
		}
	}
</style>
