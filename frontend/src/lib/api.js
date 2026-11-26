/**
 * The Lumen API client (SPEC §10). Every request carries the session headers.
 *
 * POST /chat answers with Server-Sent Events. `EventSource` only does GET, so the stream
 * is read with fetch() and a ReadableStream, and `parseSSE` turns its bytes into events:
 *
 *   meta       {conversation_id, message_id}            always first
 *   token      {t}                                       many, as the answer is written
 *   citations  [{n, title, url, page, page_end, section, category, text, ...}]
 *   done       {abstained, cache_hit, latency_ms}
 *   error      {code: "rate_limited" | "unavailable" | "internal", retry_after?}
 *
 * `error` replaces `citations` and `done`.
 */

import { sessionHeaders } from './session.js';

const DEFAULT_API_URL = 'http://localhost:8000';

/** Base URL of the versioned API, e.g. "http://localhost:8000/api/v1". */
export const API_BASE = `${(import.meta.env.VITE_API_URL || DEFAULT_API_URL).replace(/\/+$/, '')}/api/v1`;

/**
 * A failed request. `code` is one of the SSE error codes, or:
 * "not_found" (404), "bad_request" (4xx), "network" (no response) or "interrupted"
 * (the stream ended before `done`).
 */
export class ApiError extends Error {
	/**
	 * @param {string} code
	 * @param {{ status?: number, retryAfter?: number, detail?: string }} [extra]
	 */
	constructor(code, { status, retryAfter, detail } = {}) {
		super(detail || code);
		this.name = 'ApiError';
		this.code = code;
		this.status = status;
		this.retryAfter = retryAfter;
	}
}

/** @param {Response} response */
async function errorFrom(response) {
	let detail;
	try {
		const body = await response.json();
		detail = typeof body?.detail === 'string' ? body.detail : undefined;
	} catch {
		// Not JSON (a proxy's error page): the status code is enough.
	}
	const { status } = response;
	if (status === 429) {
		const retryAfter = Number.parseInt(response.headers.get('Retry-After') ?? '', 10);
		return new ApiError('rate_limited', {
			status,
			detail,
			retryAfter: Number.isFinite(retryAfter) ? retryAfter : undefined
		});
	}
	if (status === 404) return new ApiError('not_found', { status, detail });
	if (status >= 500) return new ApiError('unavailable', { status, detail });
	return new ApiError('bad_request', { status, detail });
}

/**
 * fetch() with the session headers. Network failures become ApiError("network");
 * an aborted request rethrows the AbortError. Public routes skip the session headers,
 * which also spares the browser a CORS preflight.
 * @param {string} path
 * @param {{ method?: string, body?: unknown, signal?: AbortSignal, accept?: string, session?: boolean }} [options]
 */
async function send(
	path,
	{ method = 'GET', body, signal, accept = 'application/json', session = true } = {}
) {
	/** @type {Record<string, string>} */
	const headers = { Accept: accept, ...(session ? await sessionHeaders() : {}) };
	if (body !== undefined) headers['Content-Type'] = 'application/json';
	let response;
	try {
		response = await fetch(`${API_BASE}${path}`, {
			method,
			headers,
			body: body === undefined ? undefined : JSON.stringify(body),
			signal
		});
	} catch (error) {
		if (signal?.aborted) throw error;
		throw new ApiError('network', { detail: String(error) });
	}
	if (!response.ok) throw await errorFrom(response);
	return response;
}

/** @param {string} path @param {Parameters<typeof send>[1]} [options] */
async function request(path, options) {
	const response = await send(path, options);
	return response.status === 204 ? null : response.json();
}

const LINE_END = /\r\n|\r|\n/;

/**
 * Parse a Server-Sent Events byte stream (the WHATWG EventSource rules) into
 * `{event, data}` objects. Comment lines (":...") and the id/retry fields are ignored.
 * An event is dispatched at the blank line that ends it, so a cut-off event is dropped.
 * @param {ReadableStream<Uint8Array>} stream
 * @returns {AsyncGenerator<{ event: string, data: string }>}
 */
export async function* parseSSE(stream) {
	const reader = stream.getReader();
	const decoder = new TextDecoder();
	let buffer = '';
	let type = '';
	/** @type {string[]} */
	let data = [];
	let finished = false;

	try {
		while (!finished) {
			const { value, done } = await reader.read();
			finished = done;
			buffer += done ? decoder.decode() : decoder.decode(value, { stream: true });

			let match;
			while ((match = LINE_END.exec(buffer))) {
				// A chunk can end between "\r" and "\n": wait for the next one.
				if (!finished && match[0] === '\r' && match.index === buffer.length - 1) break;
				const line = buffer.slice(0, match.index);
				buffer = buffer.slice(match.index + match[0].length);

				if (line === '') {
					if (data.length) yield { event: type || 'message', data: data.join('\n') };
					type = '';
					data = [];
					continue;
				}
				if (line.startsWith(':')) continue;
				const colon = line.indexOf(':');
				const field = colon === -1 ? line : line.slice(0, colon);
				let fieldValue = colon === -1 ? '' : line.slice(colon + 1);
				if (fieldValue.startsWith(' ')) fieldValue = fieldValue.slice(1);
				if (field === 'event') type = fieldValue;
				else if (field === 'data') data.push(fieldValue);
			}
		}
	} finally {
		// The caller stopped early (or the stream failed): stop downloading.
		if (!finished) await reader.cancel().catch(() => {});
		reader.releaseLock();
	}
}

/**
 * Ask a question. Yields the SSE events with their JSON data parsed.
 * Throws ApiError("not_found") for an unknown conversation (a plain 404, no stream).
 * @param {{ message: string, conversationId?: string | null, category?: string | null, signal?: AbortSignal }} params
 * @returns {AsyncGenerator<{ event: string, data: any }>}
 */
export async function* streamChat({ message, conversationId, category, signal }) {
	/** @type {Record<string, string>} */
	const body = { message };
	if (conversationId) body.conversation_id = conversationId;
	if (category) body.category = category;

	const response = await send('/chat', {
		method: 'POST',
		body,
		signal,
		accept: 'text/event-stream'
	});
	if (!response.body) throw new ApiError('interrupted');

	for await (const { event, data } of parseSSE(response.body)) {
		let parsed;
		try {
			parsed = JSON.parse(data);
		} catch {
			throw new ApiError('internal', { detail: `Malformed ${event} event` });
		}
		yield { event, data: parsed };
	}
}

/** @param {string} conversationId */
export function getConversation(conversationId) {
	return request(`/conversations/${encodeURIComponent(conversationId)}`);
}

/**
 * Thumbs up (1) or down (-1) on an answer. Rating it again replaces the earlier rating.
 * `reason` (thumbs-down only): wrong | outdated | not_found | unclear | offensive | other.
 * @param {{ messageId: string, rating: 1 | -1, reason?: string | null, comment?: string | null }} feedback
 */
export function sendFeedback({ messageId, rating, reason, comment }) {
	/** @type {Record<string, unknown>} */
	const body = { message_id: messageId, rating };
	if (reason) body.reason = reason;
	if (comment) body.comment = comment;
	return request('/feedback', { method: 'POST', body });
}

/** Every active indexed document: source_id, title, category, source_url, academic_year, ingested_at. */
export function getSources() {
	return request('/sources', { session: false });
}

/** {min_app_version, latest_app_version, notice, corpus_version} */
export function getMeta() {
	return request('/meta', { session: false });
}

/** "Clear my data": deletes this session's conversations, messages and feedback on the server. */
export function clearSessionData() {
	return request('/session', { method: 'DELETE' });
}
