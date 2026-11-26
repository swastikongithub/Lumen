<script>
	/**
	 * The mobile ☰ menu (DESIGN.md §4): pick the category answers come from, or open
	 * one of the app's pages. Below 768 px only; wider screens show CategoryChips.
	 * Picking an option, tapping the scrim or pressing Esc closes it.
	 */
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { CATEGORIES } from '#lib/answer.js';
	import { category, menuOpen } from '#lib/stores.js';
	import Icon from './Icon.svelte';

	/** @type {HTMLButtonElement | undefined} */
	let toggleButton = $state();
	/** @type {HTMLElement | undefined} */
	let panel = $state();

	function close({ returnFocus = true } = {}) {
		menuOpen.set(false);
		if (returnFocus) toggleButton?.focus();
	}

	/** @param {string | null} value */
	async function pick(value) {
		category.set(value);
		close();
		if (page.route.id !== '/') await goto(resolve('/'));
	}

	/** @param {KeyboardEvent} event */
	function onkeydown(event) {
		if (event.key === 'Escape' && $menuOpen) {
			event.preventDefault();
			close();
		}
	}

	// Opening moves focus to the selected option, so keyboard users start inside the menu.
	$effect(() => {
		if ($menuOpen) panel?.querySelector('[aria-pressed="true"]')?.focus();
	});
</script>

<svelte:window {onkeydown} />

<button
	bind:this={toggleButton}
	type="button"
	class="toggle"
	class:open={$menuOpen}
	aria-label="Category menu"
	aria-expanded={$menuOpen}
	aria-controls="category-menu"
	onclick={() => menuOpen.update((open) => !open)}
>
	<Icon name={$menuOpen ? 'close' : 'menu'} size={22} />
</button>

{#if $menuOpen}
	<button type="button" class="scrim" aria-label="Close menu" tabindex="-1" onclick={() => close()}
	></button>
	<nav id="category-menu" bind:this={panel} aria-label="Menu">
		<span class="label" id="menu-answer-from">Answer from</span>
		<div class="options" role="group" aria-labelledby="menu-answer-from">
			{#each CATEGORIES as option (option.label)}
				{@const selected = $category === option.value}
				<button
					type="button"
					class="row option"
					class:selected
					aria-pressed={selected}
					onclick={() => pick(option.value)}
				>
					<span class="text">
						<span>{option.label}</span>
						<span class="hint">{option.hint}</span>
					</span>
					{#if selected}
						<span class="tick"><Icon name="check" strokeWidth={2.4} /></span>
					{/if}
				</button>
			{/each}
		</div>

		<div class="divider" role="presentation"></div>

		<span class="label">Lumen</span>
		<a class="row" href={resolve('/sources')} onclick={() => close({ returnFocus: false })}>
			Indexed documents
			<Icon name="chevron" size={16} />
		</a>
		<a class="row" href={resolve('/privacy')} onclick={() => close({ returnFocus: false })}>
			Privacy &amp; data
			<Icon name="chevron" size={16} />
		</a>
	</nav>
{/if}

<style>
	.toggle {
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border: 0;
		border-radius: var(--r-lg);
		background: transparent;
		color: var(--ink);
	}

	.toggle.open {
		background: var(--surface-muted);
	}

	.scrim {
		position: fixed;
		inset: calc(var(--header-h) + env(safe-area-inset-top)) 0 0 0;
		z-index: 30;
		padding: 0;
		border: 0;
		background: var(--scrim);
		cursor: default;
	}

	nav {
		position: fixed;
		top: calc(var(--header-h) + env(safe-area-inset-top) + 6px);
		left: 8px;
		z-index: 31;
		width: 272px;
		max-width: calc(100vw - 16px);
		max-height: calc(100dvh - var(--header-h) - env(safe-area-inset-top) - 16px);
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: 8px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-2xl);
		box-shadow: var(--shadow-menu);
	}

	.label {
		padding: 8px 12px 6px;
		font-size: 12px;
		line-height: 16px;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-subtle);
	}

	.options {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.row {
		width: 100%;
		min-height: 52px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 6px 12px;
		border: 0;
		border-radius: var(--r-md);
		background: transparent;
		text-align: left;
		font-size: 15px;
		line-height: 20px;
		font-weight: 500;
		color: var(--ink);
		text-decoration: none;
	}

	.row:hover {
		background: var(--surface-muted);
		color: var(--ink);
	}

	a.row :global(svg) {
		color: var(--text-subtle);
	}

	.option.selected {
		background: var(--accent-soft);
		font-weight: 600;
	}

	.text {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 1px;
	}

	.hint {
		font-size: 12px;
		line-height: 16px;
		font-weight: 400;
		color: var(--text-subtle);
	}

	.tick {
		color: var(--accent);
	}

	.divider {
		height: 1px;
		margin: 6px 4px;
		background: var(--divider);
	}

	/* Wider screens use CategoryChips and the header nav instead. */
	@media (min-width: 768px) {
		.toggle,
		.scrim,
		nav {
			display: none;
		}
	}
</style>
