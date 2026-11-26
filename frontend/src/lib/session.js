/**
 * The anonymous session (SPEC §10): a random UUIDv4 made on first launch, kept in device
 * storage and sent as `X-Session-Id` on every request, with `X-Client` and `X-App-Version`.
 * No cookies: the web app, the API and the Android WebView are different sites.
 *
 * The ID identifies a device, not a person. "Clear my data" deletes the server-side rows
 * for it and then `resetSession()` starts a fresh one.
 *
 * The current conversation's ID is kept here too, so a reload can show it again.
 */

import { appVersion, clientName, storage } from './platform.js';

export const SESSION_KEY = 'lumen.session_id';
export const CONVERSATION_KEY = 'lumen.conversation_id';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** @type {Promise<string> | null} */
let sessionId = null;

/** @param {unknown} value */
export function isUuid(value) {
	return typeof value === 'string' && UUID.test(value);
}

/** A random UUIDv4. `crypto.randomUUID` needs a secure context, so plain HTTP gets a fallback. */
export function newUuid() {
	const crypto = globalThis.crypto;
	if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
	const bytes = crypto.getRandomValues(new Uint8Array(16));
	bytes[6] = (bytes[6] & 0x0f) | 0x40; // version 4
	bytes[8] = (bytes[8] & 0x3f) | 0x80; // RFC 4122 variant
	const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('');
	return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function loadOrCreateSessionId() {
	const stored = await storage.get(SESSION_KEY);
	if (isUuid(stored)) return /** @type {string} */ (stored).toLowerCase();
	const created = newUuid();
	await storage.set(SESSION_KEY, created);
	return created;
}

/** This device's session ID, created on first use. Concurrent callers share one lookup. */
export function getSessionId() {
	sessionId ??= loadOrCreateSessionId();
	return sessionId;
}

/** Headers for every API request. */
export async function sessionHeaders() {
	return {
		'X-Session-Id': await getSessionId(),
		'X-Client': clientName,
		'X-App-Version': appVersion
	};
}

/** Forget the session and the current conversation; the next request gets a new ID. */
export async function resetSession() {
	sessionId = null;
	await storage.remove(SESSION_KEY);
	await storage.remove(CONVERSATION_KEY);
}

/** The conversation to continue, or null to start a new one. */
export async function getConversationId() {
	const stored = await storage.get(CONVERSATION_KEY);
	return isUuid(stored) ? stored : null;
}

/** @param {string | null} id */
export async function setConversationId(id) {
	if (id) await storage.set(CONVERSATION_KEY, id);
	else await storage.remove(CONVERSATION_KEY);
}
