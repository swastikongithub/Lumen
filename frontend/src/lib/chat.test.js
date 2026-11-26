import { get } from 'svelte/store';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from './api.js';
import { createChat, errorText } from './chat.js';
import { busyUntil } from './stores.js';

const NOW = 1_800_000_000_000;

const citation = { n: 1, title: 'Examination Policy', page: 12, url: 'https://x.org/a.pdf' };

/** An async generator over the given events, optionally throwing at the end. */
async function* events(list, error) {
	for (const event of list) yield event;
	if (error) throw error;
}

const answered = [
	{ event: 'meta', data: { conversation_id: 'c1', message_id: 'a1' } },
	{ event: 'token', data: { t: 'You need ' } },
	{ event: 'token', data: { t: '75% [1].' } },
	{ event: 'citations', data: [citation] },
	{ event: 'done', data: { abstained: false, cache_hit: false, latency_ms: 900 } }
];

function setup({ streams = [answered], api = {}, savedConversation = null } = {}) {
	const streamChat = vi.fn(() => {
		const next = streams.shift();
		return next instanceof Error ? events([], next) : events(next ?? []);
	});
	const fakeApi = {
		streamChat,
		sendFeedback: vi.fn(async () => null),
		getConversation: vi.fn(),
		...api
	};
	let stored = savedConversation;
	const session = {
		getConversationId: vi.fn(async () => stored),
		setConversationId: vi.fn(async (id) => {
			stored = id;
		})
	};
	const chat = createChat({ api: fakeApi, session, now: () => NOW });
	return { chat, api: fakeApi, session, stored: () => stored };
}

const assistant = (chat) => get(chat.messages).filter((m) => m.role === 'assistant');

beforeEach(() => busyUntil.set(0));
afterEach(() => busyUntil.set(0));

describe('ask', () => {
	it('streams an answer into the message list', async () => {
		const { chat, api, stored } = setup();
		expect(await chat.ask('  Minimum attendance?  ', { category: 'exams' })).toBe(true);

		const [user, answer] = get(chat.messages);
		expect(user).toMatchObject({ role: 'user', content: 'Minimum attendance?' });
		expect(answer).toMatchObject({
			role: 'assistant',
			id: 'a1',
			content: 'You need 75% [1].',
			citations: [citation],
			status: 'done',
			abstained: false,
			question: 'Minimum attendance?',
			category: 'exams'
		});
		expect(api.streamChat).toHaveBeenCalledWith(
			expect.objectContaining({
				message: 'Minimum attendance?',
				conversationId: null,
				category: 'exams'
			})
		);
		expect(stored()).toBe('c1');
		expect(get(chat.sending)).toBe(false);
	});

	it('continues the same conversation for the next question', async () => {
		const { chat, api } = setup({ streams: [answered, answered] });
		await chat.ask('First?');
		await chat.ask('Second?');
		expect(api.streamChat.mock.calls[1][0].conversationId).toBe('c1');
		expect(get(chat.messages)).toHaveLength(4);
	});

	it('shows the answer while it streams', async () => {
		let release;
		const gate = new Promise((resolve) => (release = resolve));
		const { chat } = setup({
			api: {
				streamChat: async function* () {
					yield answered[0];
					yield answered[1];
					await gate;
					yield* answered.slice(2);
				}
			}
		});
		const done = chat.ask('Q?');
		await vi.waitFor(() => expect(assistant(chat)[0].content).toBe('You need '));
		expect(assistant(chat)[0].status).toBe('streaming');
		expect(get(chat.sending)).toBe(true);
		release();
		await done;
		expect(assistant(chat)[0].status).toBe('done');
	});

	it('ignores empty questions and questions sent while busy', async () => {
		const { chat, api } = setup();
		expect(await chat.ask('   ')).toBe(false);
		busyUntil.set(NOW + 5000);
		expect(await chat.ask('Q?')).toBe(false);
		expect(api.streamChat).not.toHaveBeenCalled();
	});

	it('marks abstained answers', async () => {
		const { chat } = setup({
			streams: [
				[
					answered[0],
					{ event: 'token', data: { t: "I couldn't find this in the indexed documents." } },
					{ event: 'citations', data: [citation] },
					{ event: 'done', data: { abstained: true } }
				]
			]
		});
		await chat.ask('Hostel refund deadline?');
		expect(assistant(chat)[0]).toMatchObject({
			status: 'done',
			abstained: true,
			citations: [citation]
		});
	});
});

describe('errors', () => {
	it('starts the busy countdown on a rate_limited event', async () => {
		const { chat } = setup({
			streams: [[answered[0], { event: 'error', data: { code: 'rate_limited', retry_after: 24 } }]]
		});
		await chat.ask('Q?');
		expect(assistant(chat)[0]).toMatchObject({
			status: 'error',
			error: { code: 'rate_limited', retryAfter: 24 }
		});
		expect(get(busyUntil)).toBe(NOW + 24_000);
	});

	it('uses 30 s when a 429 has no Retry-After', async () => {
		const { chat } = setup({ streams: [new ApiError('rate_limited', { status: 429 })] });
		await chat.ask('Q?');
		expect(get(busyUntil)).toBe(NOW + 30_000);
	});

	it('reports a stream that ends before done', async () => {
		const { chat } = setup({ streams: [answered.slice(0, 2)] });
		await chat.ask('Q?');
		expect(assistant(chat)[0]).toMatchObject({
			status: 'error',
			error: { code: 'interrupted' },
			content: 'You need '
		});
	});

	it('reports network failures', async () => {
		const { chat } = setup({ streams: [new ApiError('network')] });
		await chat.ask('Q?');
		expect(assistant(chat)[0].error.code).toBe('network');
	});

	it('starts a new conversation when the saved one is gone', async () => {
		const { chat, api, stored } = setup({
			savedConversation: 'old',
			api: {
				getConversation: vi.fn(async () => ({ id: 'old', messages: [] }))
			},
			streams: [new ApiError('not_found', { status: 404 }), answered]
		});
		await chat.restore();
		await chat.ask('Q?');
		expect(api.streamChat).toHaveBeenCalledTimes(2);
		expect(api.streamChat.mock.calls[0][0].conversationId).toBe('old');
		expect(api.streamChat.mock.calls[1][0].conversationId).toBeNull();
		expect(assistant(chat)[0].status).toBe('done');
		expect(stored()).toBe('c1');
	});

	it('retries a failed answer in place', async () => {
		const { chat } = setup({ streams: [new ApiError('network'), answered] });
		await chat.ask('Q?');
		const [failed] = assistant(chat);
		expect(await chat.retry(failed.key)).toBe(true);
		expect(assistant(chat)).toHaveLength(1);
		expect(assistant(chat)[0]).toMatchObject({ status: 'done', error: null, id: 'a1' });
	});

	it('gives readable error text', () => {
		expect(errorText('network')).toMatch(/connection/);
		expect(errorText('internal')).toBe('Something went wrong. Please try again.');
		expect(errorText(undefined)).toBe('Something went wrong. Please try again.');
	});
});

describe('stop', () => {
	it('aborts the stream and keeps what arrived', async () => {
		const { chat } = setup({
			api: {
				streamChat: async function* ({ signal }) {
					yield answered[0];
					yield answered[1];
					await new Promise((_, reject) =>
						signal.addEventListener('abort', () =>
							reject(new DOMException('Aborted', 'AbortError'))
						)
					);
				}
			}
		});
		const done = chat.ask('Q?');
		await vi.waitFor(() => expect(assistant(chat)[0].content).toBe('You need '));
		chat.stop();
		await done;
		expect(assistant(chat)[0]).toMatchObject({ status: 'stopped', content: 'You need ' });
		expect(get(chat.sending)).toBe(false);
	});
});

describe('rate', () => {
	it('sends thumbs up and then a thumbs-down reason, in order', async () => {
		const { chat, api } = setup();
		await chat.ask('Q?');
		const { key } = assistant(chat)[0];

		await chat.rate(key, 1);
		expect(assistant(chat)[0]).toMatchObject({ rating: 1, reason: null });
		chat.rate(key, -1);
		await chat.rate(key, -1, 'offensive');

		expect(api.sendFeedback.mock.calls.map(([body]) => body)).toEqual([
			{ messageId: 'a1', rating: 1, reason: null },
			{ messageId: 'a1', rating: -1, reason: null },
			{ messageId: 'a1', rating: -1, reason: 'offensive' }
		]);
		expect(assistant(chat)[0]).toMatchObject({ rating: -1, reason: 'offensive' });
	});

	it('goes back to the earlier rating when the request fails', async () => {
		const { chat } = setup({
			api: { sendFeedback: vi.fn(async () => Promise.reject(new ApiError('network'))) }
		});
		await chat.ask('Q?');
		const { key } = assistant(chat)[0];
		expect(await chat.rate(key, -1, 'wrong')).toBe(false);
		expect(assistant(chat)[0]).toMatchObject({ rating: 0, reason: null, feedbackError: true });
	});

	it('does not rate an answer that has no server ID yet or failed', async () => {
		const { chat, api } = setup({ streams: [new ApiError('network')] });
		await chat.ask('Q?');
		expect(await chat.rate(assistant(chat)[0].key, 1)).toBe(false);
		expect(api.sendFeedback).not.toHaveBeenCalled();
	});
});

describe('restore and clear', () => {
	const saved = {
		id: 'c9',
		messages: [
			{ id: 'u1', role: 'user', content: 'Library hours?', citations: [], abstained: false },
			{
				id: 'a9',
				role: 'assistant',
				content: 'Till 10 pm [1].',
				citations: [citation],
				abstained: false
			}
		]
	};

	it('shows the saved conversation and continues it', async () => {
		const { chat, api } = setup({
			savedConversation: 'c9',
			api: { getConversation: vi.fn(async () => saved) }
		});
		await chat.restore();
		const [user, answer] = get(chat.messages);
		expect(user).toMatchObject({ role: 'user', content: 'Library hours?' });
		expect(answer).toMatchObject({
			id: 'a9',
			status: 'done',
			citations: [citation],
			question: 'Library hours?'
		});
		await chat.ask('And on Sundays?');
		expect(api.streamChat.mock.calls[0][0].conversationId).toBe('c9');
	});

	it('forgets a conversation the server no longer has', async () => {
		const { chat, stored } = setup({
			savedConversation: 'gone',
			api: { getConversation: vi.fn(async () => Promise.reject(new ApiError('not_found'))) }
		});
		await chat.restore();
		expect(get(chat.messages)).toEqual([]);
		expect(stored()).toBeNull();
	});

	it('keeps the saved ID when the server is unreachable', async () => {
		const { chat, stored } = setup({
			savedConversation: 'c9',
			api: { getConversation: vi.fn(async () => Promise.reject(new ApiError('network'))) }
		});
		await chat.restore();
		expect(stored()).toBe('c9');
	});

	it('does nothing without a saved conversation', async () => {
		const { chat, api } = setup();
		await chat.restore();
		expect(api.getConversation).not.toHaveBeenCalled();
	});

	it('clear empties the list and forgets the conversation', async () => {
		const { chat, api, stored } = setup({ streams: [answered, answered] });
		await chat.ask('Q?');
		await chat.clear();
		expect(get(chat.messages)).toEqual([]);
		expect(stored()).toBeNull();
		await chat.ask('New?');
		expect(api.streamChat.mock.calls[1][0].conversationId).toBeNull();
	});
});
