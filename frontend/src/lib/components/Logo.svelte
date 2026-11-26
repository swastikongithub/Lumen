<script>
	/**
	 * The mark (a document whose middle line is lit up, for the highlighted cited sentence)
	 * and the lowercase "lumen" wordmark as live text (DESIGN.md §3).
	 * @type {{ size?: 'sm' | 'md' }}
	 */
	let { size = 'sm' } = $props();
</script>

<span class="logo {size}">
	<svg class="mark" viewBox="0 0 28 28" aria-hidden="true" focusable="false">
		<rect width="28" height="28" rx="8" fill="var(--accent)" />
		<rect x="7" y="7.5" width="14" height="2.5" rx="1.25" fill="#FFFFFF" fill-opacity="0.6" />
		<rect x="5.5" y="12.25" width="17" height="3.5" rx="1.75" fill="var(--highlight)" />
		<rect x="7" y="18" width="9" height="2.5" rx="1.25" fill="#FFFFFF" fill-opacity="0.6" />
	</svg>
	<span class="wordmark">lumen</span>
</span>

<style>
	.logo {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		color: var(--ink);
	}

	.mark {
		width: 28px;
		height: 28px;
		flex-shrink: 0;
	}

	.wordmark {
		font-family: var(--font-brand);
		font-weight: 700;
		font-size: 23px;
		line-height: 1;
		letter-spacing: -0.035em;
	}

	.md .mark {
		width: 30px;
		height: 30px;
	}

	.md .wordmark {
		font-size: 25px;
	}
</style>
