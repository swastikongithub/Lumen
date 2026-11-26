<script>
	/**
	 * The sources of one answer below 1024 px (DESIGN.md §4 SourcesSheet): a bottom sheet
	 * on phones and a centred dialog from 768 px. It is a native modal <dialog>, so focus
	 * stays inside, the page behind is inert and Esc closes it. On close, focus goes back
	 * to the chip or row that opened it (`returnFocus`).
	 * @type {{
	 *   open: boolean,
	 *   message: any,
	 *   selectedN?: number | null,
	 *   returnFocus?: HTMLElement | null,
	 *   onclose: () => void,
	 *   onreport: () => void
	 * }}
	 */
	import { tick } from 'svelte';
	import { documentCount } from '#lib/answer.js';
	import { sourceIndex } from '#lib/sources.js';
	import Icon from './Icon.svelte';
	import SourceCard from './SourceCard.svelte';

	let { open, message, selectedN = null, returnFocus = null, onclose, onreport } = $props();

	/** @type {HTMLDialogElement | undefined} */
	let dialog = $state();

	const citations = $derived(message?.citations ?? []);
	const documents = $derived(documentCount(citations));
	const hasPages = $derived(citations.some((/** @type {any} */ c) => c.page != null));
	const reported = $derived(message?.rating === -1 && message?.reason === 'outdated');

	$effect(() => {
		if (!dialog) return;
		if (open && !dialog.open) {
			dialog.showModal();
			sourceIndex.load();
			tick().then(() =>
				dialog?.querySelector('article.selected')?.scrollIntoView({ block: 'nearest' })
			);
		} else if (!open && dialog.open) {
			dialog.close();
		}
	});

	// Runs for Esc, the close button and a tap on the backdrop.
	function handleClose() {
		onclose();
		if (returnFocus?.isConnected) returnFocus.focus();
	}
</script>

<dialog bind:this={dialog} aria-labelledby="sheet-title" closedby="any" onclose={handleClose}>
	{#if message}
		<div class="handle" aria-hidden="true"></div>
		<header>
			<div>
				<h2 id="sheet-title">
					{message.abstained ? 'Closest matches' : 'Sources for this answer'}
				</h2>
				<p class="sub">
					{documents}
					{documents === 1 ? 'document' : 'documents'} · tap to open {hasPages
						? 'the PDF at that page'
						: 'the document'}
				</p>
			</div>
			<button
				type="button"
				class="close"
				aria-label="Close sources"
				onclick={() => dialog?.close()}
			>
				<Icon name="close" />
			</button>
		</header>

		<div class="cards">
			{#each citations as citation (citation.n)}
				<SourceCard
					{citation}
					answer={message.content}
					selected={citation.n === selectedN}
					id="sheet-source-{citation.n}"
				/>
			{/each}
		</div>

		<p class="footer">
			Lumen only answers from indexed documents.
			{#if reported}
				<span role="status">Thanks, this answer is reported as outdated.</span>
			{:else if message.id && message.status === 'done'}
				Something outdated? <button type="button" class="report" onclick={onreport}>
					Report it
				</button>
			{/if}
		</p>
	{/if}
</dialog>

<style>
	dialog {
		width: 100%;
		max-width: 100%;
		max-height: min(88dvh, 760px);
		margin: auto 0 0;
		padding: 10px 16px calc(20px + env(safe-area-inset-bottom));
		border: 0;
		border-radius: 20px 20px 0 0;
		background: var(--surface);
		color: var(--ink);
	}

	dialog[open] {
		display: flex;
		flex-direction: column;
		gap: 14px;
		animation: slide-up 0.2s ease-out;
	}

	dialog::backdrop {
		background: var(--scrim-strong);
	}

	.handle {
		flex-shrink: 0;
		align-self: center;
		width: 36px;
		height: 4px;
		border-radius: 2px;
		background: var(--border-strong);
	}

	header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
	}

	h2 {
		margin: 4px 0 4px;
		font-size: 21px;
		line-height: 26px;
	}

	.sub {
		margin: 0;
		font-size: 13px;
		line-height: 18px;
		color: var(--text-subtle);
	}

	.close {
		width: 44px;
		height: 44px;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border: 0;
		border-radius: 22px;
		background: var(--surface-muted);
		color: var(--ink);
	}

	.cards {
		min-height: 0;
		overflow-y: auto;
		display: flex;
		flex-direction: column;
		gap: 14px;
		overscroll-behavior: contain;
	}

	.footer {
		margin: 0;
		font-size: 13px;
		line-height: 19px;
		color: var(--text-subtle);
	}

	.report {
		min-height: 44px;
		padding: 0 2px;
		border: 0;
		background: none;
		color: var(--accent);
		font-size: inherit;
		font-weight: 600;
		text-decoration: underline;
	}

	@keyframes slide-up {
		from {
			transform: translateY(24px);
			opacity: 0;
		}
	}

	@media (min-width: 768px) {
		dialog {
			width: min(560px, calc(100vw - 48px));
			margin: auto;
			padding-bottom: 20px;
			border-radius: 20px;
		}

		.handle {
			display: none;
		}
	}
</style>
