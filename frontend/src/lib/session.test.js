import { beforeEach, describe, expect, it, vi } from 'vitest';

/** A fresh copy of the module, so its cached session ID starts empty. */
async function freshSession() {
	vi.resetModules();
	return import('./session.js');
}

beforeEach(() => {
	localStorage.clear();
});

describe('newUuid', () => {
	it('makes version 4 UUIDs', async () => {
		const { newUuid, isUuid } = await freshSession();
		const id = newUuid();
		expect(isUuid(id)).toBe(true);
		expect(id[14]).toBe('4');
	});

	it('falls back to getRandomValues without randomUUID (plain HTTP)', async () => {
		const { newUuid, isUuid } = await freshSession();
		vi.stubGlobal('crypto', { getRandomValues: (bytes) => bytes.fill(0xff) });
		const id = newUuid();
		expect(isUuid(id)).toBe(true);
		expect(id[14]).toBe('4');
		expect('89ab').toContain(id[19]);
	});
});

describe('getSessionId', () => {
	it('creates an ID once and keeps it in storage', async () => {
		const { getSessionId, SESSION_KEY, isUuid } = await freshSession();
		const first = await getSessionId();
		expect(isUuid(first)).toBe(true);
		expect(localStorage.getItem(SESSION_KEY)).toBe(first);
		expect(await getSessionId()).toBe(first);
	});

	it('reuses the stored ID after a reload', async () => {
		const stored = '0b6a1c2e-4f5d-4a3b-9c8d-7e6f5a4b3c2d';
		localStorage.setItem('lumen.session_id', stored);
		const { getSessionId } = await freshSession();
		expect(await getSessionId()).toBe(stored);
	});

	it('replaces a stored value that is not a UUID', async () => {
		localStorage.setItem('lumen.session_id', 'not-a-uuid');
		const { getSessionId, isUuid } = await freshSession();
		const id = await getSessionId();
		expect(id).not.toBe('not-a-uuid');
		expect(isUuid(id)).toBe(true);
	});

	it('gives concurrent callers the same ID', async () => {
		const { getSessionId } = await freshSession();
		const [a, b] = await Promise.all([getSessionId(), getSessionId()]);
		expect(a).toBe(b);
	});
});

describe('sessionHeaders', () => {
	it('sends the session ID, client and app version', async () => {
		const { sessionHeaders, getSessionId } = await freshSession();
		const headers = await sessionHeaders();
		expect(headers).toEqual({
			'X-Session-Id': await getSessionId(),
			'X-Client': 'web',
			'X-App-Version': expect.stringMatching(/^\d+\.\d+\.\d+/)
		});
	});
});

describe('resetSession', () => {
	it('forgets the session and the conversation', async () => {
		const { getSessionId, resetSession, setConversationId, getConversationId } =
			await freshSession();
		const before = await getSessionId();
		await setConversationId('11111111-2222-4333-8444-555555555555');
		await resetSession();
		expect(await getConversationId()).toBeNull();
		expect(await getSessionId()).not.toBe(before);
	});
});

describe('conversation ID', () => {
	it('stores, reads and clears it', async () => {
		const { setConversationId, getConversationId } = await freshSession();
		const id = '11111111-2222-4333-8444-555555555555';
		await setConversationId(id);
		expect(await getConversationId()).toBe(id);
		await setConversationId(null);
		expect(await getConversationId()).toBeNull();
	});

	it('ignores a stored value that is not a UUID', async () => {
		localStorage.setItem('lumen.conversation_id', '<script>');
		const { getConversationId } = await freshSession();
		expect(await getConversationId()).toBeNull();
	});
});
