/**
 * Answer rendering: Markdown with `marked`, then sanitised with DOMPurify (SPEC §12).
 *
 * The model's text is untrusted, so DOMPurify keeps only the tags an answer needs, and
 * links can only open http(s)/mailto URLs in a new tab. Citation markers like [1] become
 * empty `<span data-cite="1"></span>` placeholders; Message.svelte mounts a CitationChip
 * into each one once it knows which numbers have a citation.
 */

import DOMPurify from 'dompurify';
import { Marked } from 'marked';

// [12] but not [12](url), which is a Markdown link.
const MARKER = /\[(\d{1,3})\](?!\()/;
const MARKER_AT_START = new RegExp(`^${MARKER.source}`);

const ALLOWED_TAGS = [
	'p',
	'br',
	'strong',
	'em',
	'b',
	'i',
	'del',
	'code',
	'pre',
	'blockquote',
	'ul',
	'ol',
	'li',
	'a',
	'h1',
	'h2',
	'h3',
	'h4',
	'h5',
	'h6',
	'table',
	'thead',
	'tbody',
	'tr',
	'th',
	'td',
	'hr',
	'span'
];
const ALLOWED_ATTR = ['href', 'title', 'start', 'align'];

const marked = new Marked({ gfm: true, async: false });
marked.use({
	extensions: [
		{
			name: 'citation',
			level: 'inline',
			start(src) {
				const index = src.search(MARKER);
				return index === -1 ? undefined : index;
			},
			tokenizer(src) {
				const match = MARKER_AT_START.exec(src);
				if (match) return { type: 'citation', raw: match[0], n: Number(match[1]) };
				return undefined;
			},
			renderer(token) {
				return `<span data-cite="${token.n}"></span>`;
			}
		}
	]
});

/** @type {ReturnType<typeof DOMPurify> | null} */
let purifier = null;

/** A DOMPurify instance of our own, so its link hook can't affect anything else. */
function getPurifier() {
	if (purifier) return purifier;
	purifier = DOMPurify(window);
	purifier.addHook('afterSanitizeAttributes', (node) => {
		// data-* attributes pass DOMPurify by default; keep only the citation placeholder's.
		for (const { name } of [...node.attributes]) {
			if (name.startsWith('data-') && name !== 'data-cite') node.removeAttribute(name);
		}
		if (node.tagName === 'A') {
			node.setAttribute('target', '_blank');
			node.setAttribute('rel', 'noopener noreferrer');
		}
	});
	return purifier;
}

/** @param {string} markdown */
export function renderMarkdown(markdown) {
	const html = /** @type {string} */ (marked.parse(markdown ?? ''));
	return getPurifier().sanitize(html, {
		ALLOWED_TAGS,
		ALLOWED_ATTR,
		ALLOWED_URI_REGEXP: /^(?:https?:|mailto:)/i
	});
}

const CARET = '<span class="caret" aria-hidden="true"></span>';
// Closing tags at the very end, so the caret goes inside the last paragraph or list item.
const TRAILING_CLOSE =
	/(?:<\/(?:p|li|ul|ol|blockquote|h[1-6]|td|th|tr|tbody|thead|table|pre|code|strong|em|b|i|del)>\s*)+$/;

/**
 * The streaming caret (DESIGN.md §4): a 2 px accent bar after the last character.
 * @param {string} html sanitised HTML
 */
export function withCaret(html) {
	const match = TRAILING_CLOSE.exec(html);
	if (!match) return html + CARET;
	return html.slice(0, match.index) + CARET + html.slice(match.index);
}

/**
 * Sanitised HTML for an answer, with citation placeholders and, while it streams, the caret.
 * @param {string} content
 * @param {{ streaming?: boolean }} [options]
 */
export function renderAnswer(content, { streaming = false } = {}) {
	const html = renderMarkdown(content);
	return streaming ? withCaret(html) : html;
}
