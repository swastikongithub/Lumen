<script>
	/**
	 * "Answering from Exams ✕" when a category other than All is picked (DESIGN.md §4).
	 * Mobile only: from 768 px the selected chip already shows it. Tapping clears the filter.
	 */
	import { categoryLabel } from '#lib/answer.js';
	import { category } from '#lib/stores.js';
	import Icon from './Icon.svelte';
</script>

{#if $category}
	{@const label = categoryLabel($category)}
	<div class="filter">
		<span class="lead">Answering from</span>
		<button type="button" aria-label="Remove {label} filter" onclick={() => category.set(null)}>
			{label}
			<Icon name="close" size={14} strokeWidth={2.4} />
		</button>
	</div>
{/if}

<style>
	.filter {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 6px var(--page-pad) 0;
	}

	.lead {
		font-size: 13px;
		color: var(--text-subtle);
	}

	button {
		min-height: 44px;
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 0 12px;
		border: 0;
		border-radius: 22px;
		background: var(--accent-soft);
		color: var(--accent);
		font-size: 14px;
		font-weight: 600;
	}

	button:hover {
		color: var(--accent-hover);
	}

	@media (min-width: 768px) {
		.filter {
			display: none;
		}
	}
</style>
