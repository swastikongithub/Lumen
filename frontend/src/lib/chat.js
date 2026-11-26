/**
 * The conversation: sends questions, streams answers into the message list, rates answers,
 * and restores the current conversation after a reload.
 *
 * A message is one of:
 *   { key, id, role: 'user', content }
 *   { key, id, role: 'assistant', content, citations, status, abstained, error,
 *     rating, reason, question, category }
 * `key` is stable for the UI; `id` becomes the server's message ID when `meta` arrives.
 * `status` is 'streaming', 'done', 'error' or 'stopped'.
 */

import { get, writable } from 'svelte/store';
import * as defaultApi from './api.js';
import * as defaultSession from './session.js';
import { busyUntil } from './stores.js';

/** Seconds to wait when a 429 comes without Retry-After. */
const DEFAULT_RETRY_AFTER = 30;

/** What to tell the student when an answer fails, by error code. */
const ERROR_TEXT = {
	rate_limited: 'Lumen is busy right now. Try again when the countdown ends.',
	unavailable: "Lumen can't answer right now. Please try again in a few minutes.",
	network: "Couldn't reach Lumen. Check your connection and try again.",
	interrupted: 'The answer was cut off. Please try again.'
};

/** @param {string | null | undefined} code */
export function errorText(code) {
	return (
		ERROR_TEXT[/** @type {keyof typeof ERROR_TEXT} */ (code)] ??
		'Something went wrong. Please try again.'
	);
}

/**
 * @param {{ api?: typeof defaultApi, session?: typeof defaultSession, now?: () => number }} [deps]
 */
export function createChat({ api = defaultApi, session = defaultSession, now = Date.now } = {}) {
	/** @type {import('svelte/store').Writable<any[]>} */
	const messages = writable([]);
	const sending = writable(false);

	/** @type {string | null} */
	let conversationId = null;
	/** @type {AbortController | null} */
	let controller = null;
	let nextKey = 0;
	/** Feedback requests per message, sent one after another so the last click wins. */
	const feedbackQueue = new Map();

	/** @param {string} key @param {object | ((message: any) => object)} patch */
	function update(key, patch) {
		messages.update((list) =>
			list.map((message) =>
				message.key === key
					? { ...message, ...(typeof patch === 'function' ? patch(message) : patch) }
					: message
			)
		);
	}

	const find = (/** @type {string} */ key) => get(messages).find((message) => message.key === key);
	const isBusy = () => get(busyUntil) > now();

	/** @param {string} key @param {string} code @param {number} [retryAfter] */
	function fail(key, code, retryAfter) {
		update(key, { status: 'error', error: { code, retryAfter: retryAfter ?? null } });
		if (code === 'rate_limited') {
			busyUntil.set(now() + (retryAfter ?? DEFAULT_RETRY_AFTER) * 1000);
		}
	}

	/** Stream one answer into the assistant message `key`. */
	async function streamInto(/** @type {string} */ key) {
		const { question, category } = find(key);
		controller = new AbortController();
		const { signal } = controller;

		// Two attempts: if the saved conversation is gone (cleared, or past the 30-day
		// retention), the server answers 404 and the question goes to a new conversation.
		for (let attempt = 0; attempt < 2; attempt++) {
			try {
				const events = api.streamChat({ message: question, conversationId, category, signal });
				for await (const { event, data } of events) {
					if (event === 'meta') {
						conversationId = data.conversation_id;
						await session.setConversationId(conversationId);
						update(key, { id: data.message_id });
					} else if (event === 'token') {
						update(key, (message) => ({ content: message.content + data.t }));
					} else if (event === 'citations') {
						update(key, { citations: Array.isArray(data) ? data : [] });
					} else if (event === 'done') {
						update(key, { status: 'done', abstained: Boolean(data.abstained) });
						return;
					} else if (event === 'error') {
						fail(key, data.code, data.retry_after);
						return;
					}
				}
				fail(key, 'interrupted');
				return;
			} catch (error) {
				const err = /** @type {any} */ (error);
				if (err?.name === 'AbortError') {
					update(key, { status: 'stopped' });
					return;
				}
				if (err?.code === 'not_found' && conversationId && attempt === 0) {
					conversationId = null;
					await session.setConversationId(null);
					continue;
				}
				fail(key, err?.code ?? 'internal', err?.retryAfter);
				return;
			}
		}
	}

	async function run(/** @type {string} */ key) {
		sending.set(true);
		try {
			await streamInto(key);
		} finally {
			controller = null;
			sending.set(false);
		}
	}

	/**
	 * Ask a question. Resolves to false when it wasn't sent (empty, already sending, or busy).
	 * @param {string} text
	 * @param {{ category?: string | null }} [options]
	 */
	async function ask(text, { category = null } = {}) {
		const question = text.trim();
		if (!question || get(sending) || isBusy()) return false;
		const answerKey = `m${++nextKey}`;
		messages.update((list) => [
			...list,
			{ key: `m${++nextKey}`, id: null, role: 'user', content: question },
			{
				key: answerKey,
				id: null,
				role: 'assistant',
				content: '',
				citations: [],
				status: 'streaming',
				abstained: false,
				error: null,
				rating: 0,
				reason: null,
				question,
				category
			}
		]);
		await run(answerKey);
		return true;
	}

	/** Ask a failed or stopped answer's question again, in the same place. */
	async function retry(/** @type {string} */ key) {
		const message = find(key);
		if (!message || message.status === 'done' || message.status === 'streaming') return false;
		if (get(sending) || isBusy()) return false;
		update(key, { content: '', citations: [], status: 'streaming', error: null, abstained: false });
		await run(key);
		return true;
	}

	/** Stop the answer that is streaming. */
	function stop() {
		controller?.abort();
	}

	/**
	 * Thumbs up (1) or down (-1), with an optional reason for thumbs down. The UI updates at
	 * once and goes back if the request fails. Rating again replaces the earlier rating.
	 * @param {string} key
	 * @param {1 | -1} rating
	 * @param {string | null} [reason]
	 */
	function rate(key, rating, reason = null) {
		const message = find(key);
		if (!message?.id || message.status !== 'done') return Promise.resolve(false);
		const previous = { rating: message.rating, reason: message.reason };
		const sentReason = rating === -1 ? reason : null;
		update(key, { rating, reason: sentReason, feedbackError: false });

		const send = async () => {
			try {
				await api.sendFeedback({ messageId: message.id, rating, reason: sentReason });
				return true;
			} catch {
				update(key, { ...previous, feedbackError: true });
				return false;
			}
		};
		const queued = (feedbackQueue.get(key) ?? Promise.resolve()).then(send);
		feedbackQueue.set(key, queued);
		return queued;
	}

	/** @param {any} message @param {any} previous */
	function fromApi(message, previous) {
		const base = {
			key: `m${++nextKey}`,
			id: message.id,
			role: message.role,
			content: message.content
		};
		if (message.role !== 'assistant') return base;
		return {
			...base,
			citations: message.citations ?? [],
			status: 'done',
			abstained: Boolean(message.abstained),
			error: null,
			rating: 0,
			reason: null,
			question: previous?.role === 'user' ? previous.content : '',
			category: null
		};
	}

	/** Show the saved conversation again after a reload. A missing one is forgotten. */
	async function restore() {
		const saved = await session.getConversationId();
		if (!saved || get(messages).length) return;
		try {
			const conversation = await api.getConversation(saved);
			conversationId = conversation.id;
			messages.set(
				conversation.messages.map((/** @type {any} */ message, /** @type {number} */ i) =>
					fromApi(message, conversation.messages[i - 1])
				)
			);
		} catch (error) {
			const code = /** @type {any} */ (error)?.code;
			if (code === 'not_found' || code === 'bad_request') await session.setConversationId(null);
		}
	}

	/** Start over: forget the conversation on this device (the server keeps it for 30 days). */
	async function clear() {
		stop();
		conversationId = null;
		feedbackQueue.clear();
		messages.set([]);
		await session.setConversationId(null);
	}

	return {
		messages: { subscribe: messages.subscribe },
		sending: { subscribe: sending.subscribe },
		ask,
		retry,
		stop,
		rate,
		restore,
		clear
	};
}

/** The app's conversation. */
export const chat = createChat();
