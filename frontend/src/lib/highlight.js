/**
 * The excerpt on a source card, with the sentence the answer relied on highlighted
 * (DESIGN.md §4 SourcesSheet).
 *
 * The API sends the whole cited passage, not the sentence, so the sentence is guessed:
 * take the answer's sentences that cite [n], and pick the passage sentence sharing the
 * most words with them (numbers count double, since they are what students check).
 * Below a minimum overlap nothing is highlighted rather than something wrong.
 */

const STOPWORDS = new Set(
	(
		'the and for are but not you your yours with this that these those from have has had was ' +
		'were will would can could should may might must shall into onto than then them they ' +
		'their there here what when where which while who whom whose why how all any each also ' +
		'only such some more most other its it’s our ours out over under about above after ' +
		'before between both does did doing done being been very just per via etc one'
	).split(' ')
);

const MIN_SCORE = 2;
// A citation marker with the space before it: "exam [1]." becomes "exam.".
const MARKER = /\s*\[\d{1,3}\]/g;

/** Distinct content words, lowercased: 3+ letters, or any number. @param {string} text */
export function contentWords(text) {
	const words = new Set();
	for (const [word] of text.toLowerCase().matchAll(/[\p{L}\p{N}]+(?:[.,][\p{N}]+)*/gu)) {
		const numeric = /\p{N}/u.test(word);
		if ((numeric || word.length >= 3) && !STOPWORDS.has(word)) words.add(word);
	}
	return words;
}

/**
 * Split text into sentences whose concatenation is the original text, so they can be
 * rendered back in place. A sentence ends at . ! or ? followed by whitespace, or at a newline.
 * @param {string} text
 */
export function splitSentences(text) {
	const sentences = [];
	let start = 0;
	for (const match of text.matchAll(/[.!?]["')\]]*\s+|\n+/g)) {
		const end = /** @type {number} */ (match.index) + match[0].length;
		sentences.push(text.slice(start, end));
		start = end;
	}
	if (start < text.length) sentences.push(text.slice(start));
	return sentences;
}

/**
 * The answer's sentences that cite [n], without their markers.
 * @param {string} answer
 * @param {number} n
 */
export function citingSentences(answer, n) {
	const marker = `[${n}]`;
	return splitSentences(answer)
		.filter((sentence) => sentence.includes(marker))
		.map((sentence) => sentence.replace(MARKER, '').trim());
}

/**
 * Index range [start, end) of the passage sentence that best supports the claims, or null.
 * @param {string} passage
 * @param {string[]} claims
 */
export function bestSentence(passage, claims) {
	const wanted = contentWords(claims.join(' '));
	if (!wanted.size) return null;

	let best = null;
	let bestScore = 0;
	let offset = 0;
	for (const sentence of splitSentences(passage)) {
		let score = 0;
		for (const word of contentWords(sentence)) {
			if (wanted.has(word)) score += /\p{N}/u.test(word) ? 2 : 1;
		}
		if (score > bestScore) {
			bestScore = score;
			const lead = sentence.length - sentence.trimStart().length;
			best = { start: offset + lead, end: offset + sentence.trimEnd().length };
		}
		offset += sentence.length;
	}
	return bestScore >= MIN_SCORE ? best : null;
}

/** Move `index` back (or forward) to the nearest space, so the excerpt doesn't cut a word. */
function snapToSpace(text, index, direction) {
	if (index <= 0 || index >= text.length) return Math.max(0, Math.min(index, text.length));
	const found = direction < 0 ? text.lastIndexOf(' ', index) : text.indexOf(' ', index);
	return found === -1 ? index : found;
}

/**
 * The excerpt for one citation: segments to render in order, `mark: true` for the
 * highlighted sentence. Long passages are cut to `context` characters around it, with "…".
 * @param {string} passage the cited chunk's text
 * @param {string} answer the answer's text (with its [n] markers)
 * @param {number} n the citation number
 * @param {{ context?: number }} [options]
 * @returns {Array<{ text: string, mark: boolean }>}
 */
export function excerpt(passage, answer, n, { context = 220 } = {}) {
	const text = (passage ?? '')
		.replace(/[ \t]+/g, ' ')
		.replace(/\n{3,}/g, '\n\n')
		.trim();
	if (!text) return [];

	const range = bestSentence(text, citingSentences(answer ?? '', n));
	if (!range) {
		const end = snapToSpace(text, context * 2, 1);
		return [{ text: end < text.length ? `${text.slice(0, end)} …` : text, mark: false }];
	}

	const from = snapToSpace(text, range.start - context, -1);
	const to = snapToSpace(text, range.end + context, 1);
	const segments = [];
	const before = text.slice(from, range.start);
	const after = text.slice(range.end, to);
	if (from > 0 || before)
		segments.push({ text: `${from > 0 ? '… ' : ''}${before.trimStart()}`, mark: false });
	segments.push({ text: text.slice(range.start, range.end), mark: true });
	if (to < text.length || after)
		segments.push({ text: `${after.trimEnd()}${to < text.length ? ' …' : ''}`, mark: false });
	return segments.filter((segment) => segment.text);
}
