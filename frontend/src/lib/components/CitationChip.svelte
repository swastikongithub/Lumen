<script>
	/**
	 * An inline citation [n] in an answer (DESIGN.md §4). Message.svelte mounts one into each
	 * citation placeholder of the rendered answer. While the answer streams, its citations
	 * aren't known yet, so the chip is `pending`: shown, but not a button.
	 * Tapping it selects the matching source card (`onselect(n, chipElement)`).
	 * The inline chips are the one exception to the 44 px tap-target rule (DESIGN.md §2).
	 * @type {{
	 *   n: number,
	 *   title?: string,
	 *   pending?: boolean,
	 *   selected?: boolean,
	 *   onselect?: (n: number, element: HTMLElement) => void
	 * }}
	 */
	let { n, title = '', pending = false, selected = false, onselect } = $props();
</script>

{#if pending}
	<span class="chip">{n}</span>
{:else}
	<button
		type="button"
		class="chip"
		class:selected
		aria-label={title ? `Source ${n}: ${title}` : `Source ${n}`}
		aria-pressed={selected}
		onclick={(event) => onselect?.(n, event.currentTarget)}
	>
		{n}
	</button>
{/if}

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 22px;
		height: 20px;
		margin: 0 1px;
		padding: 0 5px;
		border: 0;
		border-radius: var(--r-xs);
		background: var(--accent-soft);
		color: var(--accent);
		font-size: 12px;
		font-weight: 600;
		line-height: 1;
		vertical-align: 1px;
	}

	button.chip:hover {
		color: var(--accent-hover);
	}

	.selected {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	@media (min-width: 1024px) {
		.chip {
			min-width: 24px;
			height: 22px;
			padding: 0 6px;
		}
	}
</style>
