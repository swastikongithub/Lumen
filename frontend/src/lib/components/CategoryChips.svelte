<script>
	/**
	 * The category filter as a row of pills (DESIGN.md §4), from 768 px up.
	 * The selected pill is filled with the accent colour.
	 */
	import { CATEGORIES } from '#lib/answer.js';
	import { category } from '#lib/stores.js';
</script>

<div class="chips" role="group" aria-label="Answer from">
	{#each CATEGORIES as option (option.label)}
		<button
			type="button"
			class:selected={$category === option.value}
			aria-pressed={$category === option.value}
			title={option.hint}
			onclick={() => category.set(option.value)}
		>
			{option.label}
		</button>
	{/each}
</div>

<style>
	.chips {
		display: none;
		flex-wrap: wrap;
		gap: 8px;
	}

	button {
		min-height: 44px;
		padding: 0 16px;
		border: 1px solid var(--border-strong);
		border-radius: var(--r-pill);
		background: var(--surface);
		color: var(--ink);
		font-size: 14px;
		font-weight: 500;
	}

	button:hover {
		border-color: var(--accent);
	}

	button.selected {
		border-color: var(--accent);
		background: var(--accent);
		color: #ffffff;
	}

	@media (min-width: 768px) {
		.chips {
			display: flex;
		}
	}

	/* Mouse-first screens use the mockup's 40 px pills; touch sizes stay at 44 px. */
	@media (min-width: 1024px) and (pointer: fine) {
		button {
			min-height: 40px;
		}
	}
</style>
