<script>
	/**
	 * Indexed documents (SPEC §12 screen 3): every document Lumen answers from, with its
	 * category, academic year and when it was last indexed. Phones show two columns
	 * (document, date) with the category and year under the title.
	 */
	import { onMount } from 'svelte';
	import { CATEGORIES, categoryLabel, sourceHref } from '#lib/answer.js';
	import Disclaimer from '#lib/components/Disclaimer.svelte';
	import Icon from '#lib/components/Icon.svelte';
	import { SUGGEST_DOCUMENT_URL } from '#lib/links.js';
	import { handleExternalLink } from '#lib/platform.js';
	import { formatDate, sourceIndex } from '#lib/sources.js';

	const order = CATEGORIES.map((option) => option.value);
	const rank = (/** @type {string} */ value) => {
		const i = order.indexOf(value);
		return i === -1 ? order.length : i;
	};

	const documents = $derived(
		[...$sourceIndex.documents].sort(
			(a, b) => rank(a.category) - rank(b.category) || a.title.localeCompare(b.title)
		)
	);

	onMount(() => {
		sourceIndex.load();
	});
</script>

<svelte:head>
	<title>Indexed documents · Lumen</title>
</svelte:head>

<div class="page">
	<h1>Indexed documents</h1>
	<p class="lead">
		Lumen answers only from these public documents, and links to the page each answer comes from. If
		a document you need is missing,
		<!-- eslint-disable svelte/no-navigation-without-resolve -- external URL, not an app route -->
		<a
			href={SUGGEST_DOCUMENT_URL}
			target="_blank"
			rel="noopener noreferrer"
			onclick={handleExternalLink}
		>
			suggest it<span class="visually-hidden"> (opens in a new tab)</span>
		</a>.
		<!-- eslint-enable svelte/no-navigation-without-resolve -->
	</p>
	<Disclaimer variant="full" />

	{#if $sourceIndex.status === 'error'}
		<div class="state" role="alert">
			<p>Couldn't load the document list. Check your connection and try again.</p>
			<button type="button" class="retry" onclick={() => sourceIndex.load()}>
				<Icon name="retry" size={16} />
				Try again
			</button>
		</div>
	{:else if $sourceIndex.status !== 'ready'}
		<p class="state" role="status">Loading the documents…</p>
	{:else if documents.length === 0}
		<p class="state">No documents are indexed yet.</p>
	{:else}
		<p class="count">
			{documents.length}
			{documents.length === 1 ? 'document' : 'documents'}
		</p>
		<div class="table-box">
			<table>
				<caption class="visually-hidden">Indexed documents</caption>
				<thead>
					<tr>
						<th scope="col">Document</th>
						<th scope="col" class="wide">Category</th>
						<th scope="col" class="wide">Academic year</th>
						<th scope="col">Last indexed</th>
					</tr>
				</thead>
				<tbody>
					{#each documents as document (document.source_id)}
						{@const href = sourceHref({ url: document.source_url })}
						<tr>
							<th scope="row">
								{#if href}
									<!-- eslint-disable svelte/no-navigation-without-resolve -- external document, not an app route -->
									<a {href} target="_blank" rel="noopener noreferrer" onclick={handleExternalLink}>
										{document.title}<span class="visually-hidden"> (opens in a new tab)</span>
									</a>
									<!-- eslint-enable svelte/no-navigation-without-resolve -->
								{:else}
									{document.title}
								{/if}
								<span class="narrow">
									{categoryLabel(document.category)}{document.academic_year
										? ` · ${document.academic_year}`
										: ''}
								</span>
							</th>
							<td class="wide">{categoryLabel(document.category)}</td>
							<td class="wide">{document.academic_year ?? '—'}</td>
							<td class="date">
								<time datetime={document.ingested_at}>{formatDate(document.ingested_at)}</time>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>

<style>
	.page {
		width: 100%;
		max-width: 960px;
		margin: 0 auto;
		padding: 20px var(--page-pad) calc(32px + env(safe-area-inset-bottom));
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	h1 {
		margin: 0;
		font-size: 24px;
		line-height: 30px;
	}

	.lead,
	.count,
	.state p,
	p.state {
		margin: 0;
		font-size: 15px;
		line-height: 22px;
		color: var(--text-muted);
	}

	.count {
		font-size: 13px;
		line-height: 18px;
		color: var(--text-subtle);
	}

	.state {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 12px 14px;
		border-radius: var(--r-lg);
		background: var(--surface-muted);
	}

	.retry {
		min-height: 44px;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 0 12px;
		border: 1px solid var(--border-strong);
		border-radius: var(--r-md);
		background: var(--surface);
		color: var(--ink);
		font-size: 14px;
		font-weight: 500;
	}

	.table-box {
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
		overflow: hidden;
	}

	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 14px;
		line-height: 20px;
	}

	th,
	td {
		padding: 12px 14px;
		text-align: left;
		vertical-align: top;
	}

	thead th {
		padding-block: 10px;
		background: var(--surface-muted);
		font-size: 12px;
		line-height: 16px;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--text-subtle);
	}

	tbody tr + tr :is(th, td) {
		border-top: 1px solid var(--divider);
	}

	tbody th {
		font-weight: 500;
		overflow-wrap: anywhere;
	}

	tbody th a {
		color: var(--ink);
		text-decoration-color: var(--border-strong);
		text-underline-offset: 3px;
	}

	tbody th a:hover {
		color: var(--accent);
		text-decoration-color: currentColor;
	}

	.narrow {
		display: block;
		margin-top: 2px;
		font-size: 12px;
		line-height: 16px;
		font-weight: 400;
		color: var(--text-subtle);
	}

	td {
		color: var(--text-muted);
	}

	.date {
		white-space: nowrap;
	}

	.wide {
		display: none;
	}

	@media (min-width: 768px) {
		.page {
			padding-top: 28px;
		}

		h1 {
			font-size: 28px;
			line-height: 34px;
		}

		.wide {
			display: table-cell;
		}

		.narrow {
			display: none;
		}
	}
</style>
