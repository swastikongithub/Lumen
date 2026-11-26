/**
 * Public links the app shows. The GitHub issue tracker is the contact point for
 * document suggestions and privacy questions; nothing personal goes in these URLs.
 */

export const REPO_URL = 'https://github.com/swastikongithub/Lumen';

/** Opens a new issue with only a title filled in. */
export const SUGGEST_DOCUMENT_URL = `${REPO_URL}/issues/new?title=${encodeURIComponent('Document suggestion: ')}`;

export const CONTACT_URL = `${REPO_URL}/issues`;
