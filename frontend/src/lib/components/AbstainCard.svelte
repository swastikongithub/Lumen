<script>
	/**
	 * An abstained answer (DESIGN.md §4): a dashed card instead of an answer, the closest
	 * passages Lumen found (not evidence), and a link to suggest a document.
	 * @type {{ message: any, onselect: (n: number, element: HTMLElement) => void }}
	 */
	import { categoryLabel, pageLabel } from '#lib/answer.js';
	import { handleExternalLink } from '#lib/platform.js';
	import { SUGGEST_DOCUMENT_URL } from '#lib/links.js';
	import Icon from './Icon.svelte';

	let { message, onselect } = $props();

	const closest = $derived(message.citations ?? []);
</script>

<div class="abstain">
	<p class="title">
		<Icon name="notFound" />
		<span>I couldn't find this in the indexed documents.</span>
	</p>
	<p class="explain">
		Lumen only answers from the documents it has indexed{message.category
			? `, and this question searched only ${categoryLabel(message.category)}`
			: ''}.
		{closest.length ? 'Closest matches:' : 'Try rephrasing the question.'}
	</p>

	{#if closest.length}
		<ul>
			{#each closest as citation (citation.n)}
				{@const page = pageLabel(citation)}
				<li>
					<button type="button" onclick={(event) => onselect(citation.n, event.currentTarget)}>
						<span class="name">{citation.title}{page ? ` · ${page}` : ''}</span>
						<Icon name="chevron" size={16} />
					</button>
				</li>
			{/each}
		</ul>
	{/if}

	<!-- eslint-disable svelte/no-navigation-without-resolve -- external URL, not an app route -->
	<a
		class="suggest"
		href={SUGGEST_DOCUMENT_URL}
		target="_blank"
		rel="noopener noreferrer"
		onclick={handleExternalLink}
	>
		Suggest a document to add
	</a>
	<!-- eslint-enable svelte/no-navigation-without-resolve -->
</div>

<style>
	.abstain {
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 14px 16px;
		border: 1.5px dashed var(--dashed);
		border-radius: var(--r-2xl);
		background: var(--surface);
	}

	.title {
		margin: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 15px;
		line-height: 22px;
		font-weight: 600;
	}

	.title :global(svg) {
		color: var(--text-muted);
	}

	.explain {
		margin: 0;
		font-size: 14px;
		line-height: 20px;
		color: var(--text-muted);
	}

	ul {
		margin: 0;
		padding: 0;
		list-style: none;
	}

	li + li {
		border-top: 1px solid var(--divider);
	}

	button {
		width: 100%;
		min-height: 44px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 0;
		border: 0;
		background: transparent;
		text-align: left;
		font-size: 14px;
		font-weight: 500;
		color: var(--ink);
	}

	button :global(svg) {
		color: var(--text-subtle);
	}

	button:hover .name {
		text-decoration: underline;
	}

	.suggest {
		min-height: 44px;
		display: flex;
		align-items: center;
		align-self: flex-start;
		font-size: 14px;
		font-weight: 600;
		text-decoration: none;
	}
</style>
