<script>
	/**
	 * Feedback under an answer (DESIGN.md §4): thumbs up/down, then Copy on the web
	 * (Save + Share come with the Android app). Thumbs down opens "What went wrong?"
	 * with the reason chips. "Offensive or harmful" is always shown: Google Play's
	 * AI-Generated Content policy requires an in-app way to report offensive output.
	 *
	 * The API can't remove a rating, so tapping the selected thumb again does nothing;
	 * tapping the other one replaces it.
	 * @type {{ message: any, onrate: (rating: 1 | -1, reason?: string | null) => void }}
	 */
	import { FEEDBACK_REASONS, shareText } from '#lib/answer.js';
	import { copyText, features, haptics, share } from '#lib/platform.js';
	import Icon from './Icon.svelte';

	let { message, onrate } = $props();

	let copied = $state(false);
	/** @type {ReturnType<typeof setTimeout> | undefined} */
	let copiedTimer;
	const reasonsId = $derived(`reasons-${message.key}`);

	/** @param {1 | -1} rating */
	function thumbs(rating) {
		if (message.rating === rating) return;
		haptics.tap();
		onrate(rating, null);
	}

	/** @param {string} reason */
	function pickReason(reason) {
		if (message.reason === reason) return;
		onrate(-1, reason);
	}

	async function copy() {
		copied = await copyText(shareText(message));
		clearTimeout(copiedTimer);
		copiedTimer = setTimeout(() => (copied = false), 2000);
	}

	async function shareAnswer() {
		haptics.tap();
		await share({ title: 'Answer from Lumen', text: shareText(message) });
	}

	$effect(() => () => clearTimeout(copiedTimer));
</script>

<div class="feedback">
	<div class="actions">
		<span class="ask">Was this helpful?</span>
		<button
			type="button"
			class="icon up"
			class:on={message.rating === 1}
			aria-label="Helpful"
			aria-pressed={message.rating === 1}
			onclick={() => thumbs(1)}
		>
			<Icon name="thumbsUp" strokeWidth={1.8} />
		</button>
		<button
			type="button"
			class="icon down"
			class:on={message.rating === -1}
			aria-label="Not helpful"
			aria-pressed={message.rating === -1}
			onclick={() => thumbs(-1)}
		>
			<Icon name="thumbsDown" strokeWidth={1.8} />
		</button>
		{#if features.share}
			<button type="button" class="icon" aria-label="Share answer" onclick={shareAnswer}>
				<Icon name="external" strokeWidth={1.8} />
			</button>
		{:else}
			<button type="button" class="icon copy" aria-label="Copy answer" onclick={copy}>
				<Icon name={copied ? 'check' : 'copy'} strokeWidth={1.8} />
				<span class="copy-label" aria-hidden="true">{copied ? 'Copied' : 'Copy answer'}</span>
			</button>
		{/if}
	</div>

	{#if message.rating === -1}
		<div class="reasons" role="group" aria-labelledby={reasonsId}>
			<span class="question" id={reasonsId}>What went wrong?</span>
			<div class="chips">
				{#each FEEDBACK_REASONS as reason (reason.value)}
					<button
						type="button"
						class:on={message.reason === reason.value}
						aria-pressed={message.reason === reason.value}
						onclick={() => pickReason(reason.value)}
					>
						{reason.label}
					</button>
				{/each}
			</div>
			{#if message.reason}
				<p class="thanks" role="status">
					{message.reason === 'offensive'
						? 'Thanks for reporting this. Reports like this are reviewed first.'
						: 'Thanks. This helps fix wrong answers.'}
				</p>
			{/if}
		</div>
	{/if}

	{#if message.feedbackError}
		<p class="error" role="alert">Couldn't send your feedback. Please try again.</p>
	{/if}
	<span class="visually-hidden" role="status">{copied ? 'Answer copied' : ''}</span>
</div>

<style>
	.feedback {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.actions {
		display: flex;
		align-items: center;
		gap: 4px;
	}

	.ask,
	.copy-label {
		display: none;
	}

	.icon {
		width: 44px;
		height: 44px;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		padding: 0;
		border: 0;
		border-radius: var(--r-lg);
		background: transparent;
		color: var(--text-subtle);
	}

	.icon:hover {
		background: var(--surface-muted);
	}

	.up.on {
		background: var(--accent-soft);
		color: var(--accent);
	}

	.down.on {
		background: var(--danger-soft);
		color: var(--danger);
	}

	.reasons {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 12px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
	}

	.question {
		font-size: 13px;
		line-height: 18px;
		font-weight: 600;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	.chips button {
		min-height: 44px;
		padding: 0 14px;
		border: 1px solid var(--border-strong);
		border-radius: 22px;
		background: var(--surface);
		color: var(--ink);
		font-size: 14px;
	}

	.chips button:hover {
		border-color: var(--ink);
	}

	.chips button.on {
		border-color: var(--ink);
		background: var(--ink);
		color: #ffffff;
	}

	.thanks,
	.error {
		margin: 0;
		font-size: 13px;
		line-height: 18px;
		color: var(--text-muted);
	}

	.error {
		color: var(--danger);
	}

	/* Desktop (DESIGN.md Desktop mockup): a label and bordered buttons, "Copy answer" in words. */
	@media (min-width: 1024px) {
		.ask {
			display: inline;
			margin-right: 6px;
			font-size: 13px;
			color: var(--text-subtle);
		}

		.icon {
			border: 1px solid var(--border);
			border-radius: var(--r-md);
			background: var(--surface);
		}

		.copy {
			width: auto;
			margin-left: auto;
			padding: 0 12px;
			color: var(--text-muted);
			font-size: 13px;
			font-weight: 500;
		}

		.copy-label {
			display: inline;
		}
	}

	@media (min-width: 1024px) and (pointer: fine) {
		.icon {
			width: 40px;
			height: 40px;
		}

		.copy {
			width: auto;
		}
	}
</style>
