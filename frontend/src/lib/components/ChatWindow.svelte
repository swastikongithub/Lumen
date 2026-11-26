<script module>
	/** Questions the indexed documents can answer (from evals/golden_set.jsonl). */
	export const EXAMPLE_QUESTIONS = [
		'Is there a minimum attendance for each course or only an overall percentage?',
		'Can I bring my smartwatch to the end-term exam?',
		'What time do I have to be back in my hostel room in December?',
		'Do I have to clear my backlogs to keep my placement offer?'
	];
</script>

<script>
	/**
	 * The chat screen (SPEC §12, DESIGN.md §4–5): category filter, the conversation, the busy
	 * banner and the composer. Below 1024 px a tapped citation opens the sources sheet; from
	 * 1024 px the sources panel sits beside the conversation and shows the sources of the
	 * tapped answer, or of the latest answer that has some.
	 */
	import { onMount, tick } from 'svelte';
	import { MediaQuery } from 'svelte/reactivity';
	import { chat } from '#lib/chat.js';
	import { busySeconds, category, selectedSource, sheetOpen } from '#lib/stores.js';
	import ActiveFilterPill from './ActiveFilterPill.svelte';
	import BusyBanner from './BusyBanner.svelte';
	import CategoryChips from './CategoryChips.svelte';
	import Composer from './Composer.svelte';
	import Disclaimer from './Disclaimer.svelte';
	import Message from './Message.svelte';
	import SourcesPanel from './SourcesPanel.svelte';
	import SourcesSheet from './SourcesSheet.svelte';

	const { messages, sending } = chat;
	const wide = new MediaQuery('min-width: 1024px');

	/** @type {HTMLElement | undefined} */
	let scroller = $state();
	/** The chip or row that opened the sheet, which gets focus back when it closes. */
	let opener = $state(/** @type {HTMLElement | null} */ (null));
	/** Whether the list follows new text: true unless the student scrolled up to read. */
	let stick = true;

	const canRetry = $derived(!$sending && $busySeconds === 0);
	const selectedMessage = $derived(
		$selectedSource
			? ($messages.find((message) => message.key === $selectedSource.messageKey) ?? null)
			: null
	);
	const panelMessage = $derived(
		selectedMessage ??
			$messages.findLast((message) => message.role === 'assistant' && message.citations.length) ??
			null
	);
	const panelN = $derived(
		$selectedSource && panelMessage?.key === $selectedSource.messageKey ? $selectedSource.n : null
	);

	onMount(() => {
		chat.restore();
	});

	// The sheet only exists below 1024 px.
	$effect(() => {
		if (wide.current) sheetOpen.set(false);
	});

	// Keep the newest text in view while the student is at the bottom of the list.
	$effect(() => {
		void $messages;
		const element = scroller;
		if (!stick || !element) return;
		tick().then(() => {
			element.scrollTop = element.scrollHeight;
		});
	});

	function trackScroll() {
		if (!scroller) return;
		stick = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 80;
	}

	/** @param {string} question */
	function send(question) {
		stick = true;
		selectedSource.set(null);
		chat.ask(question, { category: $category });
	}

	/** @param {string} key @param {number} n @param {HTMLElement} element */
	function selectSource(key, n, element) {
		selectedSource.set({ messageKey: key, n });
		if (!wide.current) {
			opener = element;
			sheetOpen.set(true);
		}
	}

	function closeSheet() {
		sheetOpen.set(false);
		selectedSource.set(null);
	}

	/** "Something outdated? Report it" is a thumbs down with the reason Outdated. */
	function report(/** @type {any} */ message) {
		if (message) chat.rate(message.key, -1, 'outdated');
	}
</script>

<div class="chat">
	<section class="conversation" aria-label="Conversation">
		<div class="filters" class:active={$category}>
			<div class="inner">
				<CategoryChips />
				<ActiveFilterPill />
			</div>
		</div>

		<div class="scroll" bind:this={scroller} onscroll={trackScroll}>
			<div class="inner messages">
				{#if $messages.length === 0}
					<div class="welcome">
						<h1>Ask about LPU's rules and policies</h1>
						<p class="lead">
							Lumen answers only from indexed LPU documents and cites the passage behind every
							answer. Tap a number to read it.
						</p>
						<Disclaimer variant="full" />
						<h2 id="examples-title">Try asking</h2>
						<ul class="examples" aria-labelledby="examples-title">
							{#each EXAMPLE_QUESTIONS as question (question)}
								<li>
									<button
										type="button"
										class="example"
										disabled={$sending || $busySeconds > 0}
										onclick={() => send(question)}
									>
										{question}
									</button>
								</li>
							{/each}
						</ul>
					</div>
				{:else}
					<h1 class="visually-hidden">Chat with Lumen</h1>
					{#each $messages as message (message.key)}
						<Message
							{message}
							selectedN={$selectedSource?.messageKey === message.key ? $selectedSource.n : null}
							{canRetry}
							onselectsource={selectSource}
							onrate={(key, rating, reason) => chat.rate(key, rating, reason)}
							onretry={(key) => chat.retry(key)}
						/>
					{/each}
				{/if}
			</div>
		</div>

		<div class="bar">
			<div class="inner">
				<BusyBanner />
				<Composer
					sending={$sending}
					disabled={$busySeconds > 0}
					onsend={send}
					onstop={() => chat.stop()}
				/>
			</div>
		</div>
	</section>

	{#if wide.current}
		<div class="panel">
			<SourcesPanel
				message={panelMessage}
				selectedN={panelN}
				onselect={(n) => panelMessage && selectedSource.set({ messageKey: panelMessage.key, n })}
				onreport={() => report(panelMessage)}
			/>
		</div>
	{:else}
		<SourcesSheet
			open={$sheetOpen && Boolean(selectedMessage)}
			message={selectedMessage}
			selectedN={$selectedSource?.n ?? null}
			returnFocus={opener}
			onclose={closeSheet}
			onreport={() => report(selectedMessage)}
		/>
	{/if}
</div>

<style>
	.chat {
		height: 100%;
		display: flex;
	}

	.conversation {
		flex: 1 1 auto;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	/* A centred column on tablets; full width on phones. */
	.inner {
		width: 100%;
		max-width: 760px;
		margin: 0 auto;
	}

	.filters {
		display: none;
		flex-shrink: 0;
		padding: 12px var(--page-pad) 0;
	}

	.filters.active {
		display: block;
	}

	.scroll {
		flex: 1;
		min-height: 0;
		overflow-y: auto;
		overscroll-behavior: contain;
	}

	.messages {
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 16px var(--page-pad);
	}

	.welcome {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding-top: 8px;
	}

	h1 {
		margin: 0;
		font-size: 24px;
		line-height: 30px;
	}

	.lead {
		margin: 0;
		font-size: 15px;
		line-height: 22px;
		color: var(--text-muted);
	}

	h2 {
		margin: 8px 0 0;
		font-family: var(--font-body);
		font-size: 13px;
		line-height: 18px;
		font-weight: 600;
		letter-spacing: 0;
		color: var(--text-subtle);
	}

	.examples {
		margin: 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.example {
		width: 100%;
		min-height: 44px;
		padding: 10px 14px;
		border: 1px dashed var(--dashed);
		border-radius: var(--r-xl);
		background: transparent;
		color: var(--ink);
		font-size: 14px;
		line-height: 20px;
		text-align: left;
	}

	.example:hover:not(:disabled) {
		border-style: solid;
		background: var(--surface);
	}

	.example:disabled {
		color: var(--text-subtle);
	}

	.bar {
		flex-shrink: 0;
		padding: 12px var(--page-pad) calc(16px + env(safe-area-inset-bottom));
		background: var(--surface);
		border-top: 1px solid var(--border);
	}

	.bar .inner {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	@media (min-width: 768px) {
		.filters {
			display: block;
		}
	}

	@media (min-width: 1024px) {
		.chat {
			max-width: var(--content-max);
			margin: 0 auto;
			gap: 24px;
			padding: 24px var(--page-pad) 0;
		}

		.conversation {
			flex: 999 1 560px;
		}

		.inner {
			max-width: none;
		}

		.filters {
			padding: 0 0 20px;
		}

		/* Room for focus rings, which the scroll box would otherwise clip. */
		.scroll {
			margin: 0 -4px;
			padding: 0 4px;
		}

		.messages {
			gap: 20px;
			padding: 4px 0 20px;
		}

		.welcome {
			max-width: 640px;
		}

		h1 {
			font-size: 28px;
			line-height: 34px;
		}

		.examples {
			flex-direction: row;
			flex-wrap: wrap;
		}

		.example {
			width: auto;
			border-radius: 20px;
		}

		.bar {
			padding: 0 0 24px;
			background: transparent;
			border-top: 0;
		}

		.panel {
			flex: 1 1 340px;
			min-width: 0;
			overflow-y: auto;
			padding: 4px 4px 24px;
			margin: -4px -4px 0;
		}
	}
</style>
