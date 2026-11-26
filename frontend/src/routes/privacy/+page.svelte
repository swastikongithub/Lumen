<script>
	/**
	 * Privacy policy (SPEC §13, PLAY_STORE.md §5): what is collected, why, for how long, who
	 * processes it, and "Clear my data". Google Play links to this page, so it must match the
	 * Data safety answers.
	 */
	import { tick } from 'svelte';
	import { clearSessionData } from '#lib/api.js';
	import { chat } from '#lib/chat.js';
	import Icon from '#lib/components/Icon.svelte';
	import { CONTACT_URL } from '#lib/links.js';
	import { features, handleExternalLink } from '#lib/platform.js';
	import { resetSession } from '#lib/session.js';

	/** @type {'idle' | 'confirm' | 'working' | 'done' | 'error'} */
	let step = $state('idle');
	/** @type {HTMLButtonElement | undefined} */
	let cancelButton = $state();
	/** @type {HTMLButtonElement | undefined} */
	let clearButton = $state();
	/** @type {HTMLElement | undefined} */
	let doneMessage = $state();

	const savedOnDevice = features.saveAnswers ? ' and your saved answers on this device' : '';

	async function ask() {
		step = 'confirm';
		await tick();
		cancelButton?.focus();
	}

	async function cancel() {
		step = 'idle';
		await tick();
		clearButton?.focus();
	}

	async function clear() {
		step = 'working';
		try {
			await clearSessionData();
			await resetSession();
			await chat.clear();
			step = 'done';
			await tick();
			doneMessage?.focus();
		} catch {
			step = 'error';
		}
	}
</script>

<svelte:head>
	<title>Privacy & data · Lumen</title>
</svelte:head>

<article class="page">
	<h1>Privacy & data</h1>
	<p class="updated">Last updated 26 November 2026</p>
	<p class="lead">
		Lumen is an unofficial student project. You don't need an account, and it never asks for your
		name, email or phone number.
	</p>

	<section aria-labelledby="kept">
		<h2 id="kept">What Lumen keeps</h2>
		<ul>
			<li>
				<strong>Your questions and Lumen's answers</strong>, so a conversation can continue and
				answers can be checked.
			</li>
			<li><strong>Your feedback</strong>: thumbs up or down, and the reason you picked.</li>
			<li>
				<strong>A random app ID</strong>, created and stored on this device, that links your
				questions together. It isn't tied to your name or to any account.
			</li>
			<li>
				<strong>A salted hash of your IP address</strong>, used only to limit how many questions one
				device can ask in a short time. Your IP address itself isn't stored.
			</li>
			<li>
				<strong>Whether you use the website or the Android app</strong>, and its version, to find
				bugs.
			</li>
		</ul>
	</section>

	<section aria-labelledby="why">
		<h2 id="why">Why</h2>
		<ul>
			<li>To answer your question, including follow-up questions about earlier answers.</li>
			<li>To find answers that are wrong, outdated or harmful, and fix them.</li>
			<li>To stop abuse and keep the free service running.</li>
		</ul>
	</section>

	<section aria-labelledby="how-long">
		<h2 id="how-long">How long</h2>
		<p>
			Questions, answers, feedback and request logs are deleted after 30 days. You can delete yours
			sooner with <a href="#clear">Clear my data</a>.
		</p>
	</section>

	<section aria-labelledby="who">
		<h2 id="who">Who else processes it</h2>
		<p>
			To write an answer, your question and the matching document passages are sent to a language
			model provider: Groq, or Google Gemini when Groq is busy. Langfuse records each request (the
			question, each step and how long it took) so problems can be fixed. The server runs on Google
			Cloud Run, the database on Neon, and the website on Cloudflare Pages. Answers may be kept in a
			cache, not linked to you, so a repeated question is answered faster. The website loads its
			fonts from Google Fonts.
		</p>
		<p>These services process the data for Lumen. It is never sold, and Lumen has no ads.</p>
	</section>

	<section aria-labelledby="not-kept">
		<h2 id="not-kept">What Lumen doesn't collect</h2>
		<p>
			Name, email, phone number, location, contacts, photos, files or payment details. Please don't
			type personal details into your questions.
		</p>
	</section>

	<section id="clear" class="clear" aria-labelledby="clear-title">
		<h2 id="clear-title">Clear my data</h2>
		<p>
			Deletes every conversation, answer and piece of feedback linked to this device's app ID from
			Lumen's server{savedOnDevice}, and starts a new app ID.
		</p>

		{#if step === 'done'}
			<p class="done" role="status" tabindex="-1" bind:this={doneMessage}>
				<Icon name="check" size={18} />
				Your data is deleted.
			</p>
		{:else if step === 'confirm' || step === 'working'}
			<div class="confirm">
				<p>
					This deletes your chat history on our server{savedOnDevice}. It can't be undone.
				</p>
				<div class="actions">
					<button type="button" class="danger" disabled={step === 'working'} onclick={clear}>
						{step === 'working' ? 'Deleting…' : 'Delete my data'}
					</button>
					<button
						type="button"
						class="secondary"
						bind:this={cancelButton}
						disabled={step === 'working'}
						onclick={cancel}
					>
						Cancel
					</button>
				</div>
			</div>
		{:else}
			{#if step === 'error'}
				<p class="error" role="alert">
					Couldn't delete your data. Check your connection and try again.
				</p>
			{/if}
			<button type="button" class="danger-outline" bind:this={clearButton} onclick={ask}>
				Clear my data
			</button>
		{/if}
	</section>

	<section aria-labelledby="contact">
		<h2 id="contact">Questions</h2>
		<p>
			Ask about privacy or report a problem on
			<!-- eslint-disable svelte/no-navigation-without-resolve -- external URL, not an app route -->
			<a href={CONTACT_URL} target="_blank" rel="noopener noreferrer" onclick={handleExternalLink}>
				Lumen's GitHub issues page<span class="visually-hidden"> (opens in a new tab)</span>
			</a>
			<!-- eslint-enable svelte/no-navigation-without-resolve -->
		</p>
	</section>
</article>

<style>
	.page {
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
		padding: 20px var(--page-pad) calc(40px + env(safe-area-inset-bottom));
		display: flex;
		flex-direction: column;
		gap: 20px;
	}

	h1 {
		margin: 0;
		font-size: 24px;
		line-height: 30px;
	}

	.updated {
		margin: -14px 0 0;
		font-size: 13px;
		line-height: 18px;
		color: var(--text-subtle);
	}

	h2 {
		margin: 0 0 8px;
		font-size: 19px;
		line-height: 26px;
	}

	p,
	ul {
		margin: 0;
		font-size: 15px;
		line-height: 23px;
		color: var(--text-muted);
	}

	p + p {
		margin-top: 10px;
	}

	.lead {
		color: var(--ink-2);
	}

	ul {
		padding-left: 20px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	strong {
		font-weight: 600;
		color: var(--ink);
	}

	.clear {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 16px;
		background: var(--surface);
		border: 1px solid var(--border);
		border-radius: var(--r-xl);
		scroll-margin: 16px;
	}

	.clear h2 {
		margin: 0;
	}

	.clear p + p {
		margin-top: 0;
	}

	.confirm {
		display: flex;
		flex-direction: column;
		gap: 12px;
		padding: 12px;
		border-radius: var(--r-lg);
		background: var(--danger-soft);
	}

	.confirm p {
		color: var(--ink);
	}

	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}

	button {
		min-height: 48px;
		padding: 0 18px;
		border-radius: var(--r-lg);
		font-size: 15px;
		font-weight: 600;
	}

	.danger-outline {
		align-self: flex-start;
		border: 1.5px solid var(--danger);
		background: var(--surface);
		color: var(--danger);
	}

	.danger-outline:hover {
		background: var(--danger-soft);
	}

	.danger {
		border: 0;
		background: var(--danger);
		color: #ffffff;
	}

	.secondary {
		border: 1px solid var(--border-strong);
		background: var(--surface);
		color: var(--ink);
	}

	button:disabled {
		opacity: 0.7;
	}

	.done {
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--accent);
		font-weight: 600;
	}

	.error {
		color: var(--danger);
	}

	@media (min-width: 768px) {
		.page {
			padding-top: 28px;
		}

		h1 {
			font-size: 28px;
			line-height: 34px;
		}
	}
</style>
