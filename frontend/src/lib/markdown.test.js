import { describe, expect, it } from 'vitest';
import { renderAnswer, renderMarkdown, withCaret } from './markdown.js';

const CARET = '<span class="caret" aria-hidden="true"></span>';

describe('renderMarkdown', () => {
	it('renders Markdown and turns citation markers into placeholders', () => {
		expect(renderMarkdown('You need **75%** attendance [1].')).toBe(
			'<p>You need <strong>75%</strong> attendance <span data-cite="1"></span>.</p>\n'
		);
	});

	it('handles adjacent markers and markers in lists', () => {
		expect(renderMarkdown('Both apply [2][3].')).toBe(
			'<p>Both apply <span data-cite="2"></span><span data-cite="3"></span>.</p>\n'
		);
		expect(renderMarkdown('- Bring your ID [1]\n- No phones [2]')).toBe(
			'<ul>\n<li>Bring your ID <span data-cite="1"></span></li>\n' +
				'<li>No phones <span data-cite="2"></span></li>\n</ul>\n'
		);
	});

	it('leaves Markdown links and code spans alone', () => {
		const html = renderMarkdown('See [1](https://example.org) and `[4]`.');
		expect(html).toContain(
			'<a href="https://example.org" target="_blank" rel="noopener noreferrer">1</a>'
		);
		expect(html).toContain('<code>[4]</code>');
		expect(html).not.toContain('data-cite');
	});

	it('strips scripts, images, event handlers and javascript: links', () => {
		const html = renderMarkdown(
			'<img src=x onerror=alert(1)><script>alert(2)</script>' +
				'<a href="javascript:alert(3)">x</a> <b onclick="alert(4)">bold</b>'
		);
		expect(html).not.toMatch(/<img|<script|onerror|onclick|javascript:/i);
		expect(html).toContain('<b>bold</b>');
	});

	it('drops attributes it does not need, like class and style', () => {
		expect(renderMarkdown('<span class="x" style="color:red" data-x="1">hi</span>')).toBe(
			'<p><span>hi</span></p>\n'
		);
	});

	it('opens links in a new tab without the opener', () => {
		expect(renderMarkdown('[policy](https://www.lpu.in/a.pdf)')).toBe(
			'<p><a href="https://www.lpu.in/a.pdf" target="_blank" rel="noopener noreferrer">policy</a></p>\n'
		);
	});

	it('renders tables with their markers', () => {
		const html = renderMarkdown('| Room | Fee |\n|---|---|\n| 4 seater [2] | ₹ 1 |');
		expect(html).toContain('<table>');
		expect(html).toContain('<td>4 seater <span data-cite="2"></span></td>');
	});

	it('returns an empty string for empty content', () => {
		expect(renderMarkdown('')).toBe('');
	});
});

describe('withCaret', () => {
	it('puts the caret inside the last paragraph', () => {
		expect(withCaret('<p>One</p>\n<p>Two</p>\n')).toBe(`<p>One</p>\n<p>Two${CARET}</p>\n`);
	});

	it('puts the caret inside the last list item', () => {
		expect(withCaret('<ul>\n<li>a</li>\n<li>b</li>\n</ul>\n')).toBe(
			`<ul>\n<li>a</li>\n<li>b${CARET}</li>\n</ul>\n`
		);
	});

	it('shows the caret alone before any text', () => {
		expect(withCaret('')).toBe(CARET);
	});
});

describe('renderAnswer', () => {
	it('adds the caret only while streaming', () => {
		expect(renderAnswer('Lab courses are', { streaming: true })).toBe(
			`<p>Lab courses are${CARET}</p>\n`
		);
		expect(renderAnswer('Lab courses are')).toBe('<p>Lab courses are</p>\n');
	});
});
