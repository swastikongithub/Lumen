<script>
	/**
	 * "Lumen is busy right now. Try again in 0:24" above the input (DESIGN.md §4), counting
	 * down from the server's retry_after. The input is disabled while it shows.
	 * The first sentence says why: every LLM provider is busy (rate_limited), or this device
	 * or network reached Lumen's question limit (too_many_requests, which can mean hours).
	 * Screen readers hear the wait once, in words; the ticking clock itself is hidden from
	 * them, so they aren't interrupted every second.
	 */
	import { busyReason, busySeconds, formatCountdown, spokenWait } from '#lib/stores.js';
	import Icon from './Icon.svelte';

	const REASON_TEXT = {
		rate_limited: 'Lumen is busy right now.',
		too_many_requests: 'Too many questions from this device or network.'
	};

	const reason = $derived(
		REASON_TEXT[/** @type {keyof typeof REASON_TEXT} */ ($busyReason)] ?? REASON_TEXT.rate_limited
	);

	/** Seconds left when the banner appeared, for the one-time announcement. */
	let announced = $state(0);

	$effect(() => {
		if ($busySeconds === 0) announced = 0;
		else if (announced === 0) announced = $busySeconds;
	});
</script>

<div class="slot" role="status">
	{#if $busySeconds > 0}
		<p class="banner">
			<Icon name="clock" size={16} />
			<span aria-hidden="true">
				{reason} Try again in <strong>{formatCountdown($busySeconds)}</strong>
			</span>
			<span class="visually-hidden">{reason} Try again in {spokenWait(announced)}.</span>
		</p>
	{/if}
</div>

<style>
	.slot:empty {
		display: none;
	}

	.banner {
		margin: 0;
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 12px;
		border-radius: var(--r-lg);
		background: var(--warning-bg);
		color: var(--warning-text);
		font-size: 13px;
		line-height: 18px;
	}

	strong {
		font-variant-numeric: tabular-nums;
	}
</style>
