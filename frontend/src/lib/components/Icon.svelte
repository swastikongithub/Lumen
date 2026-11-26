<script module>
	/**
	 * Inline SVG icons from the mockups (24 × 24 grid, stroked with currentColor).
	 * Circles and rectangles are written as paths so every icon is a list of `d` strings.
	 */
	const ICONS = {
		menu: ['M4 7h16M4 12h16M4 17h16'],
		close: ['M6 6l12 12M18 6L6 18'],
		document: [
			'M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z',
			'M14 3v5h5M9 13h6M9 17h6'
		],
		info: ['M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0', 'M12 11v5M12 8h.01'],
		chevron: ['M9 6l6 6-6 6'],
		back: ['M15 6l-6 6 6 6'],
		thumbsUp: [
			'M7 10v11H4V10zM7 10l4-7a2 2 0 0 1 2.6 2.4L12.5 10H19a2 2 0 0 1 2 2.3l-1.3 7A2 2 0 0 1 17.7 21H7'
		],
		thumbsDown: [
			'M17 14V3h3v11zM17 14l-4 7a2 2 0 0 1-2.6-2.4l1.1-4.6H5a2 2 0 0 1-2-2.3l1.3-7A2 2 0 0 1 6.3 3H17'
		],
		copy: [
			'M11 9h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z',
			'M5 15V5a2 2 0 0 1 2-2h10'
		],
		check: ['M5 12.5l4.5 4.5L19 7.5'],
		send: ['M12 19V5M5 12l7-7 7 7'],
		stop: ['M9 7h6a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z'],
		external: ['M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5'],
		notFound: ['M4 11a7 7 0 1 0 14 0a7 7 0 1 0-14 0', 'M20 20l-3.5-3.5M8.5 8.5l5 5M13.5 8.5l-5 5'],
		clock: ['M3 12a9 9 0 1 0 18 0a9 9 0 1 0-18 0', 'M12 7v5l3 2'],
		retry: ['M20 11a8 8 0 1 0-2.3 5.7', 'M20 4v7h-7']
	};
</script>

<script>
	/**
	 * Decorative by default (aria-hidden): give the button or link around it the label.
	 * @type {{ name: keyof typeof ICONS, size?: number, strokeWidth?: number }}
	 */
	let { name, size = 18, strokeWidth = 2 } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 24 24"
	fill="none"
	stroke="currentColor"
	stroke-width={strokeWidth}
	stroke-linecap="round"
	stroke-linejoin="round"
	aria-hidden="true"
	focusable="false"
>
	{#each ICONS[name] as d (d)}
		<path {d} />
	{/each}
</svg>

<style>
	svg {
		flex-shrink: 0;
		display: block;
	}
</style>
