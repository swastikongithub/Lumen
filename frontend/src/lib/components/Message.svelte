<script>
	/**
	 * One message (DESIGN.md §4): the student's question as a dark bubble, or Lumen's answer
	 * with its label row, the answer card (sanitised Markdown with citation chips and, while
	 * streaming, the caret), the source rows, an error notice, and feedback.
	 *
	 * The answer HTML comes from renderAnswer() (marked + DOMPurify). It has empty
	 * <span data-cite="n"> placeholders, and a CitationChip is mounted into each one whose
	 * number has a citation (or into every one while streaming, as an inert chip).
	 * @type {{
	 *   message: any,
	 *   selectedN?: number | null,
	 *   canRetry?: boolean,
	 *   onselectsource: (key: string, n: number, element: HTMLElement) => void,
	 *   onrate: (key: string, rating: 1 | -1, reason?: string | null) => void,
	 *   onretry: (key: string) => void
	 * }}
	 */
	import { mount, unmount, untrack } from 'svelte';
	import { answerMeta, sourceMeta } from '#lib/answer.js';
	import { errorText } from '#lib/chat.js';
	import { renderAnswer } from '#lib/markdown.js';
	import AbstainCard from './AbstainCard.svelte';
	import CitationChip from './CitationChip.svelte';
	import FeedbackButtons from './FeedbackButtons.svelte';
	import Icon from './Icon.svelte';

	let { message, selectedN = null, canRetry = true, onselectsource, onrate, onretry } = $props();

	const isAnswer = $derived(message.role === 'assistant');
	const streaming = $derived(message.status === 'streaming');
	const html = $derived(
		isAnswer && !message.abstained ? renderAnswer(message.content, { streaming }) : ''
	);
	const meta = $derived(isAnswer ? answerMeta(message) : '');

	/** @type {HTMLElement | undefined} */
	let answerElement = $state();
	/** The mounted chips and their reactive props. */
	let chips = $state.raw(/** @type {Array<{ props: any, instance: any }>} */ ([]));

	/** @param {number} n @param {HTMLElement} element */
	function select(n, element) {
		onselectsource(message.key, n, element);
	}

	// Mount a chip into each citation placeholder, again whenever the answer HTML changes.
	$effect(() => {
		const container = answerElement;
		if (!container || !html) return;
		const byNumber = new Map(message.citations.map((/** @type {any} */ c) => [c.n, c]));
		const pending = streaming;
		const mounted = [];
		for (const slot of container.querySelectorAll('span[data-cite]')) {
			const n = Number(slot.getAttribute('data-cite'));
			const citation = byNumber.get(n);
			if (!citation && !pending) continue; // a marker that points at no citation
			const props = $state({
				n,
				title: citation?.title ?? '',
				pending: !citation,
				selected: untrack(() => selectedN === n),
				onselect: select
			});
			mounted.push({ props, instance: mount(CitationChip, { target: slot, props }) });
		}
		chips = mounted;
		return () => {
			for (const chip of mounted) unmount(chip.instance);
		};
	});

	// Selecting a source updates the chips in place, so a focused chip keeps its focus.
	$effect(() => {
		for (const chip of chips) chip.props.selected = chip.props.n === selectedN;
	});
</script>

{#if !isAnswer}
	<p class="bubble">{message.content}</p>
{:else}
	<article class="answer-block" aria-label="Answer from Lumen">
		<p class="label">
			<svg class="mini-mark" viewBox="0 0 28 28" aria-hidden="true" focusable="false">
				<rect width="28" height="28" rx="8" fill="var(--accent)" />
				<rect x="5.5" y="11.5" width="17" height="5" rx="2.5" fill="var(--highlight)" />
			</svg>
			<span class="name">Lumen</span>
			{#if meta}<span class="meta">· {meta}</span>{/if}
		</p>

		{#if message.abstained}
			<AbstainCard {message} onselect={select} />
		{:else if message.content || streaming}
			<div class="card">
				<div
					class="answer"
					bind:this={answerElement}
					aria-live={streaming ? 'polite' : 'off'}
					aria-busy={streaming}
				>
					<!-- eslint-disable-next-line svelte/no-at-html-tags -- sanitised by DOMPurify in renderAnswer() -->
					{@html html}
				</div>

				{#if message.status === 'done' && message.citations.length}
					<div class="divider" role="presentation"></div>
					<ul class="sources" aria-label="Sources">
						{#each message.citations as citation (citation.n)}
							<li>
								<button
									type="button"
									class="source"
									onclick={(event) => select(citation.n, event.currentTarget)}
								>
									<span class="badge" aria-hidden="true">{citation.n}</span>
									<span class="names">
										<span class="title">
											<span class="visually-hidden">Source {citation.n}:</span>
											{citation.title}
										</span>
										<span class="source-meta">{sourceMeta(citation)}</span>
									</span>
									<Icon name="chevron" size={16} />
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		{/if}

		{#if message.status === 'error' || message.status === 'stopped'}
			<div class="notice" role={message.status === 'error' ? 'alert' : undefined}>
				<p>
					{message.status === 'stopped'
						? 'You stopped this answer.'
						: errorText(message.error?.code)}
				</p>
				<button
					type="button"
					class="retry"
					disabled={!canRetry}
					onclick={() => onretry(message.key)}
				>
					<Icon name="retry" size={16} />
					Try again
				</button>
			</div>
		{/if}

		{#if message.status === 'done'}
			<FeedbackButtons {message} onrate={(rating, reason) => onrate(message.key, rating, reason)} />
		{/if}
	</article>
{/if}

<style>
	.bubble {
		align-self: flex-end;
		max-width: min(280px, 85%);
		margin: 0;
		padding: 10px 14px;
		border-radius: 18px 18px 4px 18px;
		background: var(--ink);
		color: #ffffff;
		font-size: 15px;
		line-height: 21px;
		white-space: pre-wrap;
		overflow-wrap: anywhere;
	}

	.answer-block {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.label {
		margin: 0;
		display: flex;
		align-items: center;
		gap: 6px;
		font-size: 13px;
		line-height: 18px;
	}

	.mini-mark {
		width: 16px;
		height: 16px;
		flex-shrink: 0;
	}

	.name {
		font-weight: 600;
	}

	.meta {
		color: var(--text-subtle);
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 14px 16px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-2xl);
	}

	.answer {
		font-size: 15px;
		line-height: 22px;
		overflow-wrap: anywhere;
	}

	.answer :global(:is(p, ul, ol, blockquote, pre, table)) {
		margin: 0 0 10px;
	}

	.answer :global(:is(p, ul, ol, blockquote, pre, table):last-child) {
		margin-bottom: 0;
	}

	.answer :global(:is(ul, ol)) {
		padding-left: 20px;
	}

	.answer :global(li + li) {
		margin-top: 4px;
	}

	.answer :global(:is(strong, b)) {
		font-weight: 600;
	}

	.answer :global(:is(h1, h2, h3, h4, h5, h6)) {
		margin: 0 0 6px;
		font-size: 16px;
		line-height: 22px;
	}

	.answer :global(code) {
		padding: 1px 4px;
		border-radius: 4px;
		background: var(--surface-muted);
		font-size: 0.92em;
	}

	.answer :global(pre) {
		overflow-x: auto;
		padding: 10px;
		border-radius: var(--r-md);
		background: var(--surface-muted);
	}

	.answer :global(blockquote) {
		padding-left: 12px;
		border-left: 3px solid var(--border-strong);
		color: var(--text-muted);
	}

	.answer :global(table) {
		display: block;
		overflow-x: auto;
		border-collapse: collapse;
		font-size: 14px;
	}

	.answer :global(:is(th, td)) {
		padding: 6px 10px;
		border: 1px solid var(--border);
		text-align: left;
	}

	.answer :global(.caret) {
		display: inline-block;
		width: 2px;
		height: 17px;
		margin-left: 3px;
		vertical-align: -3px;
		background: var(--accent);
		animation: blink 1s steps(1) infinite;
	}

	@keyframes blink {
		50% {
			opacity: 0;
		}
	}

	.divider {
		height: 1px;
		background: var(--divider);
	}

	.sources {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.source {
		width: 100%;
		min-height: 48px;
		display: flex;
		align-items: center;
		gap: 10px;
		padding: 0;
		border: 0;
		background: transparent;
		color: var(--ink);
		text-align: left;
	}

	.source > :global(svg) {
		color: var(--text-subtle);
	}

	.source:hover .title {
		text-decoration: underline;
	}

	.badge {
		width: 24px;
		height: 24px;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 7px;
		background: var(--accent-soft);
		color: var(--accent);
		font-size: 12px;
		font-weight: 600;
	}

	.names {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.title {
		font-size: 14px;
		line-height: 19px;
		font-weight: 500;
	}

	.source-meta {
		font-size: 12px;
		line-height: 16px;
		color: var(--text-subtle);
	}

	.notice {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 10px 12px;
		border-radius: var(--r-lg);
		background: var(--surface-muted);
	}

	.notice p {
		margin: 0;
		font-size: 14px;
		line-height: 20px;
		color: var(--text-muted);
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

	.retry:disabled {
		color: var(--text-subtle);
		background: var(--surface-muted);
	}

	@media (min-width: 1024px) {
		.bubble {
			max-width: 520px;
			padding: 12px 16px;
			line-height: 22px;
		}

		.card {
			padding: 18px 20px;
		}

		.answer {
			font-size: 16px;
			line-height: 26px;
		}
	}
</style>
