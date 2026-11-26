<script>
	/**
	 * The sources column from 1024 px (DESIGN.md §4 SourcesPanel). It shows the sources of
	 * one answer: the one whose citation was tapped, or the latest. The chosen source is
	 * expanded like the sheet's cards; the others are compact rows that expand on click.
	 * @type {{
	 *   message: any,
	 *   selectedN?: number | null,
	 *   onselect: (n: number) => void,
	 *   onreport: () => void
	 * }}
	 */
	import { onMount, tick } from 'svelte';
	import { sourceMeta } from '#lib/answer.js';
	import { sourceIndex } from '#lib/sources.js';
	import SourceCard from './SourceCard.svelte';

	let { message, selectedN = null, onselect, onreport } = $props();

	/** @type {HTMLElement | undefined} */
	let panel = $state();

	const citations = $derived(message?.citations ?? []);
	const expandedN = $derived(
		citations.some((/** @type {any} */ c) => c.n === selectedN)
			? selectedN
			: (citations[0]?.n ?? null)
	);
	const reported = $derived(message?.rating === -1 && message?.reason === 'outdated');

	onMount(() => {
		sourceIndex.load();
	});

	// Bring the source of a tapped citation into view.
	$effect(() => {
		if (selectedN == null) return;
		const n = selectedN;
		tick().then(() =>
			panel
				?.querySelector(`#panel-source-${n}`)
				?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
		);
	});
</script>

<aside bind:this={panel} aria-labelledby="panel-title">
	<div class="heading">
		<h2 id="panel-title">{message?.abstained ? 'Closest matches' : 'Sources'}</h2>
		{#if citations.length}
			<span>{citations.length} {citations.length === 1 ? 'passage' : 'passages'}</span>
		{/if}
	</div>

	{#if !citations.length}
		<p class="empty">
			The documents behind each answer appear here, with the passage it relied on highlighted.
		</p>
	{:else}
		{#each citations as citation (citation.n)}
			{#if citation.n === expandedN}
				<SourceCard {citation} answer={message.content} selected id="panel-source-{citation.n}" />
			{:else}
				<button
					type="button"
					class="row"
					id="panel-source-{citation.n}"
					onclick={() => onselect(citation.n)}
				>
					<span class="badge" aria-hidden="true">{citation.n}</span>
					<span class="names">
						<span class="title">
							<span class="visually-hidden">Source {citation.n}:</span>
							{citation.title}
						</span>
						<span class="meta">{sourceMeta(citation, { long: true })}</span>
					</span>
				</button>
			{/if}
		{/each}

		{#if message.status === 'done'}
			<p class="report">
				{#if reported}
					<span role="status">Thanks, this answer is reported as outdated.</span>
				{:else if message.id}
					Something outdated? <button type="button" onclick={onreport}>Report it</button>
				{/if}
			</p>
		{/if}
	{/if}

	<details>
		<summary>How this answer was found</summary>
		<ol>
			<li>Searched the indexed documents by meaning and by keyword.</li>
			<li>Re-ranked the best matches and kept the strongest passages.</li>
			<li>
				Wrote the answer only from those passages, citing each one, or said it couldn't find the
				answer.
			</li>
		</ol>
	</details>
</aside>

<style>
	aside {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.heading {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 12px;
	}

	h2 {
		margin: 0;
		font-size: 19px;
		line-height: 26px;
	}

	.heading span,
	.empty,
	.report {
		font-size: 13px;
		line-height: 19px;
		color: var(--text-subtle);
	}

	.empty,
	.report {
		margin: 0;
	}

	.row {
		width: 100%;
		min-height: 56px;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 10px 14px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
		color: var(--ink);
		text-align: left;
		scroll-margin: 12px;
	}

	.row:hover {
		border-color: var(--border-strong);
	}

	.badge {
		width: 26px;
		height: 26px;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--r-sm);
		background: var(--accent-soft);
		color: var(--accent);
		font-size: 13px;
		font-weight: 600;
	}

	.names {
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.title {
		font-size: 14px;
		line-height: 19px;
		font-weight: 600;
	}

	.meta {
		font-size: 12px;
		line-height: 16px;
		color: var(--text-subtle);
	}

	.report button {
		min-height: 40px;
		padding: 0 2px;
		border: 0;
		background: none;
		color: var(--accent);
		font-size: inherit;
		font-weight: 600;
		text-decoration: underline;
	}

	details {
		padding: 14px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
	}

	summary {
		min-height: 28px;
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
	}

	ol {
		margin: 10px 0 0;
		padding-left: 20px;
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 13px;
		line-height: 19px;
		color: var(--text-muted);
	}
</style>
