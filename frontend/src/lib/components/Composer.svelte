<script module>
	/** The backend's limit on a question (backend/app/api/chat.py MAX_MESSAGE_CHARS). */
	export const MAX_QUESTION_CHARS = 1000;
</script>

<script>
	/**
	 * The question box (DESIGN.md §2 Input): a 48 px pill with a 48 px accent send button on
	 * phones, a bordered box with a hint line from 1024 px (Desktop mockup).
	 * Enter sends and Shift + Enter adds a line, except while an input method is composing.
	 * While an answer streams the button stops it; while Lumen is busy (the BusyBanner
	 * shows), the box and the button are disabled and grey.
	 * @type {{
	 *   sending?: boolean,
	 *   disabled?: boolean,
	 *   onsend: (question: string) => void,
	 *   onstop: () => void
	 * }}
	 */
	import { MediaQuery } from 'svelte/reactivity';
	import { haptics } from '#lib/platform.js';
	import Icon from './Icon.svelte';

	let { sending = false, disabled = false, onsend, onstop } = $props();

	const wide = new MediaQuery('min-width: 1024px');

	let question = $state('');
	/** @type {HTMLTextAreaElement | undefined} */
	let textarea = $state();

	/** @param {Event} [event] */
	function submit(event) {
		event?.preventDefault();
		const text = question.trim();
		if (disabled || sending) return;
		if (!text) {
			textarea?.focus();
			return;
		}
		haptics.tap();
		onsend(text);
		question = '';
	}

	/** @param {KeyboardEvent} event */
	function keydown(event) {
		// keyCode 229 is a key press that an input method (IME) is still handling.
		if (event.key !== 'Enter' || event.shiftKey || event.isComposing || event.keyCode === 229) {
			return;
		}
		event.preventDefault();
		submit();
	}
</script>

<form onsubmit={submit}>
	<label for="question" class="visually-hidden">Ask a question</label>
	<div class="field" class:disabled>
		<textarea
			id="question"
			bind:this={textarea}
			bind:value={question}
			{disabled}
			rows="1"
			maxlength={MAX_QUESTION_CHARS}
			placeholder={wide.current
				? 'Ask about exams, attendance, hostel, fees or placements…'
				: 'Ask about exams, attendance, hostel…'}
			enterkeyhint="send"
			autocomplete="off"
			aria-describedby="question-hint"
			onkeydown={keydown}></textarea>
		{#if sending}
			<button type="button" class="send stop" aria-label="Stop the answer" onclick={onstop}>
				<Icon name="stop" size={20} />
			</button>
		{:else}
			<button
				type="submit"
				class="send"
				{disabled}
				aria-label={disabled ? 'Send (unavailable)' : 'Send'}
			>
				<Icon name="send" size={20} />
			</button>
		{/if}
	</div>
	<p class="hint" id="question-hint">
		Enter to send · Shift + Enter for a new line · Answers only come from indexed documents
	</p>
</form>

<style>
	form {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.field {
		display: flex;
		align-items: flex-end;
		gap: 8px;
	}

	textarea {
		flex: 1;
		min-width: 0;
		min-height: 48px;
		max-height: 128px;
		padding: 12px 16px;
		border: 1px solid var(--border-strong);
		border-radius: 24px;
		background: var(--bg);
		color: var(--ink);
		font: inherit;
		font-size: 15px;
		line-height: 21px;
		resize: none;
		/* Grows with the question where supported; elsewhere it scrolls. */
		field-sizing: content;
	}

	/* Empty, the box is one line and a long placeholder is cut short, not wrapped. */
	textarea:placeholder-shown {
		field-sizing: fixed;
		height: 48px;
	}

	textarea::placeholder {
		color: var(--text-subtle);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	textarea:disabled {
		border-color: var(--disabled);
		background: var(--surface-muted);
		color: var(--text-subtle);
	}

	.send {
		width: 48px;
		height: 48px;
		flex-shrink: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0;
		border: 0;
		border-radius: 24px;
		background: var(--accent);
		color: #ffffff;
	}

	.send:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.send.stop {
		background: var(--ink);
	}

	.send:disabled {
		background: var(--disabled);
		color: var(--text-subtle);
	}

	.hint {
		display: none;
		margin: 0;
		font-size: 12px;
		line-height: 16px;
		color: var(--text-subtle);
	}

	@media (min-width: 1024px) {
		.field {
			gap: 10px;
			padding: 10px 10px 10px 16px;
			background: var(--surface);
			border: 1px solid var(--border-strong);
			border-radius: 18px;
		}

		/* The box shows the focus ring, so the borderless textarea inside doesn't. */
		.field:focus-within {
			outline: 2px solid var(--accent);
			outline-offset: 2px;
		}

		.field.disabled {
			border-color: var(--disabled);
			background: var(--surface-muted);
		}

		textarea,
		textarea:disabled {
			min-height: 56px;
			max-height: 200px;
			padding: 6px 0;
			border: 0;
			border-radius: 0;
			background: transparent;
			line-height: 22px;
			outline: none;
		}

		.send {
			width: 44px;
			height: 44px;
			border-radius: var(--r-lg);
		}

		.hint {
			display: block;
		}
	}
</style>
