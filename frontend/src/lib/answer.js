/**
 * Labels and text built from answers and their citations: category names, page labels,
 * the meta line on source cards, document links, and the text for copy and share.
 *
 * A citation (SPEC §10) is {n, title, url, page, page_end, section, category, text,
 * source_id, document_id, chunk_id}. `page` is null for documents without pages (web pages).
 */

/** Categories for the ☰ menu and the desktop chips (DESIGN.md §4). `null` means All. */
export const CATEGORIES = Object.freeze([
	{ value: null, label: 'All', hint: 'Every indexed document' },
	{ value: 'academics', label: 'Academics', hint: 'Attendance, credits, grading' },
	{ value: 'exams', label: 'Exams', hint: 'Eligibility, schedules, re-appear' },
	{ value: 'hostel', label: 'Hostel', hint: 'Rules, timings, allotment' },
	{ value: 'fees', label: 'Fees', hint: 'Payments, refunds, fines' },
	{ value: 'placements', label: 'Placements', hint: 'Eligibility, drives, policy' }
]);

/** Thumbs-down reasons (FeedbackReason in backend/app/enums.py). "offensive" must always exist. */
export const FEEDBACK_REASONS = Object.freeze([
	{ value: 'wrong', label: 'Wrong' },
	{ value: 'outdated', label: 'Outdated' },
	{ value: 'not_found', label: "Didn't find it" },
	{ value: 'unclear', label: 'Unclear' },
	{ value: 'offensive', label: 'Offensive or harmful' }
]);

const CATEGORY_LABELS = { other: 'Other' };
for (const { value, label } of CATEGORIES) if (value) CATEGORY_LABELS[value] = label;

/** @param {string | null | undefined} value */
export function categoryLabel(value) {
	if (!value) return 'All';
	return CATEGORY_LABELS[value] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * "p.12", "pp.12–13" (short) or "Page 12", "Pages 12–13" (long); null without pages.
 * @param {{ page?: number | null, page_end?: number | null }} citation
 * @param {{ long?: boolean }} [options]
 */
export function pageLabel(citation, { long = false } = {}) {
	const { page, page_end: end } = citation;
	if (page == null) return null;
	const range = end != null && end > page;
	if (long) return range ? `Pages ${page}–${end}` : `Page ${page}`;
	return range ? `pp.${page}–${end}` : `p.${page}`;
}

/**
 * The meta line under a source title: "4.2 Unfair Means · p.12 · Exams · 2025-26".
 * @param {{ section?: string | null, page?: number | null, page_end?: number | null, category?: string }} citation
 * @param {{ long?: boolean, academicYear?: string | null }} [options]
 */
export function sourceMeta(citation, { long = false, academicYear = null } = {}) {
	return [
		citation.section,
		pageLabel(citation, { long }),
		citation.category ? categoryLabel(citation.category) : null,
		academicYear
	]
		.filter(Boolean)
		.join(' · ');
}

/** @param {string | null | undefined} url */
function safeUrl(url) {
	try {
		const parsed = new URL(url ?? '');
		return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed : null;
	} catch {
		return null;
	}
}

/**
 * Link to the cited document, opened at the cited page when it has pages. PDF viewers
 * honour "#page=N"; Android's Custom Tabs may not, so the card also shows the page (SPEC §12.1).
 * Only http(s) links are returned; anything else gives null.
 * @param {{ url?: string | null, page?: number | null }} citation
 */
export function sourceHref(citation) {
	const url = safeUrl(citation.url);
	if (!url) return null;
	if (citation.page != null && !url.hash) url.hash = `page=${citation.page}`;
	return url.href;
}

/** "Open PDF at page 12", or "Open document" for documents without pages. */
export function openLabel(/** @type {{ page?: number | null }} */ citation) {
	return citation.page != null ? `Open PDF at page ${citation.page}` : 'Open document';
}

/** @param {Array<{ document_id?: string, source_id?: string, title?: string }>} citations */
export function documentCount(citations) {
	return new Set(citations.map((c) => c.document_id ?? c.source_id ?? c.title)).size;
}

/**
 * The label meta next to "Lumen" above an answer (DESIGN.md §4 AssistantMessage).
 * Counts come from the citations; nothing is shown before they arrive.
 * @param {{ status: string, content: string, citations: any[], abstained?: boolean }} message
 */
export function answerMeta(message) {
	if (message.status === 'streaming') {
		return message.content ? 'writing the answer' : 'searching the documents';
	}
	if (message.status !== 'done' || message.abstained || !message.citations.length) return '';
	const passages = message.citations.length;
	const documents = documentCount(message.citations);
	const docs = `${documents} ${documents === 1 ? 'document' : 'documents'}`;
	if (passages === documents) return `from ${docs}`;
	return `from ${passages} passages in ${docs}`;
}

/** The answer without citation markers that point at no citation. */
export function cleanAnswer(/** @type {string} */ content, /** @type {any[]} */ citations) {
	const valid = new Set(citations.map((c) => c.n));
	return content.replace(/\[(\d{1,3})\]/g, (marker, n) => (valid.has(Number(n)) ? marker : ''));
}

/**
 * Text for Copy and Share (DESIGN.md §7): the answer, then "Sources:" with numbered
 * titles and links, then "via Lumen (unofficial)".
 * @param {{ content: string, citations: any[] }} message
 */
export function shareText(message) {
	const lines = [cleanAnswer(message.content, message.citations).trim()];
	if (message.citations.length) {
		lines.push('', 'Sources:');
		for (const citation of message.citations) {
			const page = pageLabel(citation);
			const link = sourceHref(citation);
			const label = page ? `${citation.title}, ${page}` : citation.title;
			lines.push(`[${citation.n}] ${label}${link ? `: ${link}` : ''}`);
		}
	}
	lines.push('', 'via Lumen (unofficial)');
	return lines.join('\n');
}
