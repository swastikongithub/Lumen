<script>
	/**
	 * The top bar (DESIGN.md §4, Main and Desktop mockups).
	 * Below 768 px: ☰ category menu, logo, "Indexed docs" link, 56 px tall.
	 * From 768 px: logo and the page links; from 1024 px also the disclaimer pill.
	 * The safe-area padding keeps it clear of the status bar in the Android app.
	 */
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import CategoryMenu from './CategoryMenu.svelte';
	import Disclaimer from './Disclaimer.svelte';
	import Icon from './Icon.svelte';
	import Logo from './Logo.svelte';

	const links = [
		{ route: '/', href: resolve('/'), label: 'Chat' },
		{ route: '/sources', href: resolve('/sources'), label: 'Indexed documents' },
		{ route: '/privacy', href: resolve('/privacy'), label: 'Privacy & data' }
	];
</script>

<header>
	<div class="start">
		<CategoryMenu />
		<a class="home" href={resolve('/')} aria-label="Lumen, go to chat">
			<span class="logo-sm"><Logo size="sm" /></span>
			<span class="logo-md"><Logo size="md" /></span>
		</a>
		<nav aria-label="Main">
			{#each links as link (link.route)}
				<a href={link.href} aria-current={page.route.id === link.route ? 'page' : undefined}>
					{link.label}
				</a>
			{/each}
		</nav>
	</div>

	<a class="docs" href={resolve('/sources')}>
		<Icon name="document" />
		Indexed docs
	</a>
	<div class="pill">
		<Disclaimer variant="pill" />
	</div>
</header>

<style>
	header {
		flex-shrink: 0;
		min-height: calc(var(--header-h) + env(safe-area-inset-top));
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: env(safe-area-inset-top) 12px 0 4px;
		background: var(--surface);
		border-bottom: 1px solid var(--border);
	}

	.start {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.home {
		min-height: 44px;
		display: flex;
		align-items: center;
		padding: 0 4px;
		border-radius: var(--r-md);
		color: var(--ink);
		text-decoration: none;
	}

	.logo-md,
	nav,
	.pill {
		display: none;
	}

	.docs {
		min-height: 44px;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 8px;
		border-radius: var(--r-md);
		color: var(--ink);
		font-size: 14px;
		font-weight: 500;
		text-decoration: none;
	}

	nav {
		gap: 4px;
	}

	nav a {
		min-height: 44px;
		display: flex;
		align-items: center;
		padding: 0 12px;
		border-radius: var(--r-md);
		color: var(--text-muted);
		font-size: 14px;
		font-weight: 500;
		text-decoration: none;
	}

	nav a:hover {
		color: var(--ink);
		background: var(--surface-muted);
	}

	nav a[aria-current='page'] {
		background: var(--surface-muted);
		color: var(--ink);
		font-weight: 600;
	}

	@media (min-width: 768px) {
		header {
			min-height: calc(64px + env(safe-area-inset-top));
			flex-wrap: wrap;
			padding: calc(10px + env(safe-area-inset-top)) var(--page-pad) 10px;
		}

		.start {
			flex-wrap: wrap;
			gap: 20px;
		}

		.logo-sm,
		.docs {
			display: none;
		}

		.logo-md,
		nav {
			display: flex;
		}
	}

	@media (min-width: 1024px) {
		.start {
			gap: 28px;
		}

		.pill {
			display: block;
		}
	}
</style>
