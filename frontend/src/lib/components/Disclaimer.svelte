<script module>
	/** The full disclaimer (SPEC §12). The bar and pill are its one-line forms (DESIGN.md §4). */
	export const DISCLAIMER =
		'Unofficial student project. Answers come from public LPU documents and may be outdated. ' +
		'Always confirm with the official source linked in each answer.';
</script>

<script>
	import Icon from './Icon.svelte';

	/**
	 * `bar`: one line under the mobile header. `pill`: in the desktop header.
	 * `full`: the whole sentence, for the welcome screen and the info pages.
	 * @type {{ variant?: 'bar' | 'pill' | 'full' }}
	 */
	let { variant = 'bar' } = $props();
</script>

{#if variant === 'full'}
	<p class="full">
		<Icon name="info" size={16} />
		<span>{DISCLAIMER}</span>
	</p>
{:else}
	<p class={variant}>
		<Icon name="info" size={14} />
		{#if variant === 'pill'}
			<span>Unofficial student project · confirm with the linked document</span>
		{:else}
			<span>Unofficial · always confirm with the linked document</span>
		{/if}
	</p>
{/if}

<style>
	p {
		margin: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--text-muted);
	}

	.bar {
		padding: 8px var(--page-pad);
		background: var(--info-bg);
		font-size: 12px;
		line-height: 16px;
	}

	.pill {
		gap: 6px;
		padding: 6px 12px;
		border-radius: var(--r-pill);
		background: var(--info-bg);
		font-size: 13px;
		line-height: 18px;
	}

	.full {
		align-items: flex-start;
		padding: 12px 14px;
		border-radius: var(--r-lg);
		background: var(--info-bg);
		font-size: 13px;
		line-height: 19px;
	}

	.full :global(svg) {
		margin-top: 2px;
	}
</style>
