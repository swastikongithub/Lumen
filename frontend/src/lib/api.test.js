import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
	API_BASE,
	ApiError,
	clearSessionData,
	getConversation,
	getSources,
	parseSSE,
	sendFeedback,
	streamChat
} from './api.js';

/** A ReadableStream that yields the given strings as separate chunks. */
function streamOf(...chunks) {
	const encoder = new TextEncoder();
	return new ReadableStream({
		start(controller) {
			for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
			controller.close();
		}
	});
}

async function collect(iterable) {
	const items = [];
	for await (const item of iterable) items.push(item);
	return items;
}

/** @param {BodyInit | null} body @param {ResponseInit} [init] */
function mockFetch(body, init) {
	const fetch = vi.fn(async () => new Response(body, init));
	vi.stubGlobal('fetch', fetch);
	return fetch;
}

beforeEach(() => {
	localStorage.clear();
});

describe('parseSSE', () => {
	it('parses events with a type and JSON data', async () => {
		const events = await collect(
			parseSSE(streamOf('event: meta\ndata: {"a":1}\n\nevent: token\ndata: {"t":"Hi"}\n\n'))
		);
		expect(events).toEqual([
			{ event: 'meta', data: '{"a":1}' },
			{ event: 'token', data: '{"t":"Hi"}' }
		]);
	});

	it('joins an event split across chunks at any byte', async () => {
		const text = 'event: token\ndata: {"t":"Hello"}\n\n';
		const chunks = [...text]; // one character per chunk
		const events = await collect(parseSSE(streamOf(...chunks)));
		expect(events).toEqual([{ event: 'token', data: '{"t":"Hello"}' }]);
	});

	it('decodes a multi-byte character split between chunks', async () => {
		const bytes = new TextEncoder().encode('data: {"t":"₹ 500"}\n\n');
		const rupeeStart = bytes.indexOf(0xe2);
		const stream = new ReadableStream({
			start(controller) {
				controller.enqueue(bytes.slice(0, rupeeStart + 1));
				controller.enqueue(bytes.slice(rupeeStart + 1));
				controller.close();
			}
		});
		const [event] = await collect(parseSSE(stream));
		expect(JSON.parse(event.data).t).toBe('₹ 500');
	});

	it('accepts CRLF and CR line endings, even split between chunks', async () => {
		const events = await collect(
			parseSSE(streamOf('event: a\r', '\ndata: 1\r\n\r\n', 'event: b\rdata: 2\r\r'))
		);
		expect(events).toEqual([
			{ event: 'a', data: '1' },
			{ event: 'b', data: '2' }
		]);
	});

	it('ignores comments, id and retry, and joins multi-line data', async () => {
		const events = await collect(
			parseSSE(streamOf(': keep-alive\nid: 7\nretry: 100\ndata: line one\ndata: line two\n\n'))
		);
		expect(events).toEqual([{ event: 'message', data: 'line one\nline two' }]);
	});

	it('keeps a value without the space after the colon', async () => {
		const events = await collect(parseSSE(streamOf('event:done\ndata:{}\n\n')));
		expect(events).toEqual([{ event: 'done', data: '{}' }]);
	});

	it('drops an event the stream cut off before its blank line', async () => {
		const events = await collect(parseSSE(streamOf('data: 1\n\ndata: 2\n')));
		expect(events).toEqual([{ event: 'message', data: '1' }]);
	});

	it('cancels the stream when the caller stops early', async () => {
		const cancel = vi.fn();
		const stream = new ReadableStream({
			pull(controller) {
				controller.enqueue(new TextEncoder().encode('data: x\n\n'));
			},
			cancel
		});
		for await (const event of parseSSE(stream)) {
			expect(event.data).toBe('x');
			break;
		}
		expect(cancel).toHaveBeenCalled();
	});
});

describe('streamChat', () => {
	const sse = [
		'event: meta\ndata: {"conversation_id":"c1","message_id":"m1"}\n\n',
		'event: token\ndata: {"t":"You need 75% [1]."}\n\n',
		'event: citations\ndata: [{"n":1,"title":"Exam Policy","page":12}]\n\n',
		'event: done\ndata: {"abstained":false,"cache_hit":false,"latency_ms":900}\n\n'
	].join('');

	it('posts the question with session headers and yields parsed events', async () => {
		const fetch = mockFetch(sse, { headers: { 'Content-Type': 'text/event-stream' } });
		const events = await collect(
			streamChat({ message: 'Attendance?', conversationId: 'c1', category: 'exams' })
		);

		expect(events.map((e) => e.event)).toEqual(['meta', 'token', 'citations', 'done']);
		expect(events[2].data[0].title).toBe('Exam Policy');

		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe(`${API_BASE}/chat`);
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body)).toEqual({
			message: 'Attendance?',
			conversation_id: 'c1',
			category: 'exams'
		});
		expect(init.headers.Accept).toBe('text/event-stream');
		expect(init.headers['X-Session-Id']).toMatch(/^[0-9a-f-]{36}$/);
		expect(init.headers['X-Client']).toBe('web');
	});

	it('leaves out conversation_id and category when not given', async () => {
		const fetch = mockFetch(sse);
		await collect(streamChat({ message: 'Hi' }));
		expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ message: 'Hi' });
	});

	it('throws not_found for an unknown conversation', async () => {
		mockFetch(JSON.stringify({ detail: 'Conversation not found' }), { status: 404 });
		await expect(collect(streamChat({ message: 'Hi', conversationId: 'x' }))).rejects.toMatchObject(
			{ code: 'not_found', status: 404 }
		);
	});

	it('throws rate_limited with Retry-After from a 429', async () => {
		mockFetch('{}', { status: 429, headers: { 'Retry-After': '24' } });
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toMatchObject({
			code: 'rate_limited',
			retryAfter: 24
		});
	});

	it("throws too_many_requests with the body's retry_after for Lumen's own limit", async () => {
		const body = {
			detail: 'Too many questions from this device or network. Try again later.',
			code: 'too_many_requests',
			retry_after: 42
		};
		mockFetch(JSON.stringify(body), { status: 429, headers: { 'Retry-After': '41' } });
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toMatchObject({
			code: 'too_many_requests',
			status: 429,
			retryAfter: 42,
			message: body.detail
		});
	});

	it('falls back to Retry-After when the body has no usable wait', async () => {
		const body = JSON.stringify({ code: 'too_many_requests', retry_after: 'soon' });
		mockFetch(body, { status: 429, headers: { 'Retry-After': '7' } });
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toMatchObject({
			code: 'too_many_requests',
			retryAfter: 7
		});
	});

	it('leaves retryAfter unset for a 429 with no wait at all', async () => {
		mockFetch('<html>Too Many Requests</html>', { status: 429 });
		const error = await collect(streamChat({ message: 'Hi' })).catch((e) => e);
		expect(error).toMatchObject({ code: 'rate_limited', status: 429 });
		expect(error.retryAfter).toBeUndefined();
	});

	it('throws network when the server cannot be reached', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				throw new TypeError('Failed to fetch');
			})
		);
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toBeInstanceOf(ApiError);
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toMatchObject({
			code: 'network'
		});
	});

	it('rethrows an abort instead of calling it a network error', async () => {
		const controller = new AbortController();
		vi.stubGlobal(
			'fetch',
			vi.fn(async () => {
				controller.abort();
				throw new DOMException('Aborted', 'AbortError');
			})
		);
		await expect(
			collect(streamChat({ message: 'Hi', signal: controller.signal }))
		).rejects.toMatchObject({ name: 'AbortError' });
	});

	it('throws internal on malformed event data', async () => {
		mockFetch('event: token\ndata: {not json\n\n');
		await expect(collect(streamChat({ message: 'Hi' }))).rejects.toMatchObject({
			code: 'internal'
		});
	});
});

describe('JSON routes', () => {
	it('sends feedback in the API field names', async () => {
		const fetch = mockFetch(null, { status: 204 });
		expect(await sendFeedback({ messageId: 'm1', rating: -1, reason: 'offensive' })).toBeNull();
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe(`${API_BASE}/feedback`);
		expect(JSON.parse(init.body)).toEqual({ message_id: 'm1', rating: -1, reason: 'offensive' });
		expect(init.headers['Content-Type']).toBe('application/json');
	});

	it('leaves out an empty reason', async () => {
		const fetch = mockFetch(null, { status: 204 });
		await sendFeedback({ messageId: 'm1', rating: 1, reason: null });
		expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({ message_id: 'm1', rating: 1 });
	});

	it('loads a conversation with session headers', async () => {
		const fetch = mockFetch(JSON.stringify({ id: 'c1', messages: [] }));
		expect(await getConversation('c1')).toEqual({ id: 'c1', messages: [] });
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe(`${API_BASE}/conversations/c1`);
		expect(init.headers['X-Session-Id']).toBeDefined();
	});

	it('loads sources without session headers (public route)', async () => {
		const fetch = mockFetch('[]');
		expect(await getSources()).toEqual([]);
		expect(fetch.mock.calls[0][1].headers['X-Session-Id']).toBeUndefined();
	});

	it('clears session data with DELETE /session', async () => {
		const fetch = mockFetch(null, { status: 204 });
		await clearSessionData();
		const [url, init] = fetch.mock.calls[0];
		expect(url).toBe(`${API_BASE}/session`);
		expect(init.method).toBe('DELETE');
	});

	it('maps 5xx to unavailable and keeps the server detail', async () => {
		mockFetch(JSON.stringify({ detail: 'Database down' }), { status: 503 });
		await expect(getSources()).rejects.toMatchObject({
			code: 'unavailable',
			status: 503,
			message: 'Database down'
		});
	});

	it('maps other 4xx to bad_request', async () => {
		mockFetch('not json', { status: 400 });
		await expect(getConversation('c1')).rejects.toMatchObject({ code: 'bad_request' });
	});
});
