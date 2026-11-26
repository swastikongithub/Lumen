<script>
	/**
	 * One cited source, expanded (DESIGN.md §4 SourcesSheet / SourcesPanel): number badge,
	 * title, meta ("4.2 Unfair Means · Page 12 · Exams · 2025-26"), the passage with the
	 * sentence the answer relied on highlighted, and a link to the document at that page.
	 * The selected card (the citation the student tapped) gets a 1.5 px accent border.
	 * @type {{ citation: any, answer?: string, selected?: boolean, id?: string }}
	 */
	import { openLabel, sourceHref, sourceMeta } from '#lib/answer.js';
	import { excerpt } from '#lib/highlight.js';
	import { handleExternalLink } from '#lib/platform.js';
	import { sourceIndex } from '#lib/sources.js';
	import Icon from './Icon.svelte';

	let { citation, answer = '', selected = false, id } = $props();

	const segments = $derived(excerpt(citation.text, answer, citation.n));
	const academicYear = $derived($sourceIndex.byId.get(citation.source_id)?.academic_year ?? null);
	const href = $derived(sourceHref(citation));
	const titleId = $derived(id ? `${id}-title` : undefined);
</script>

<article {id} class:selected aria-labelledby={titleId}>
	<div class="head">
		<span class="badge" aria-hidden="true">{citation.n}</span>
		<div class="names">
			<span class="title" id={titleId}>
				<span class="visually-hidden">Source {citation.n}:</span>
				{citation.title}
			</span>
			<span class="meta">{sourceMeta(citation, { long: true, academicYear })}</span>
		</div>
	</div>

	{#if segments.length}
		<p class="excerpt">
			{#each segments as segment, i (i)}{#if segment.mark}<mark>
						{segment.text}
					</mark>{:else}{segment.text}{/if}{/each}
		</p>
	{/if}

	{#if href}
		<!-- eslint-disable svelte/no-navigation-without-resolve -- external document, not an app route -->
		<a {href} target="_blank" rel="noopener noreferrer" onclick={handleExternalLink}>
			{openLabel(citation)}
			<Icon name="external" size={16} />
			<span class="visually-hidden">(opens in a new tab)</span>
		</a>
		<!-- eslint-enable svelte/no-navigation-without-resolve -->
	{/if}
</article>

<style>
	article {
		display: flex;
		flex-direction: column;
		gap: 10px;
		padding: 14px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
		scroll-margin: 12px;
	}

	article.selected {
		/* 0.5 px less padding keeps the content still when the border thickens. */
		padding: 13.5px;
		border: 1.5px solid var(--accent);
	}

	.head {
		display: flex;
		align-items: center;
		gap: 10px;
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
		font-size: 15px;
		line-height: 20px;
		font-weight: 600;
	}

	.meta {
		font-size: 12px;
		line-height: 16px;
		color: var(--text-subtle);
	}

	.excerpt {
		margin: 0;
		padding: 12px;
		border-radius: var(--r-md);
		background: var(--bg);
		font-size: 14px;
		line-height: 21px;
		color: var(--ink-2);
		white-space: pre-line;
		overflow-wrap: anywhere;
	}

	mark {
		padding: 1px 2px;
		border-radius: 3px;
		background: var(--accent-soft);
		color: var(--ink);
	}

	a {
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
		text-decoration: none;
	}
</style>
