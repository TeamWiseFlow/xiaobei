// Observe the fixed X transport without modifying business or signing code.
export function xPublicationObserver() {
  const state = { stage: 'preparing', submission_attempted: false };
  return {
    state,
    request(input) {
      const url = new URL(input.url);
      const method = (input.method || 'GET').toUpperCase();
      if (['upload.x.com', 'upload.twitter.com'].includes(url.hostname) && url.pathname === '/i/media/upload.json') {
        state.stage = 'media_upload';
      } else if (['x.com', 'twitter.com'].includes(url.hostname) && url.pathname === '/i/api/1.1/media/metadata/create.json') {
        state.stage = 'media_metadata';
      } else if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        // Includes unknown mutations and Articles: once a possible post was
        // sent, a later thread upload failure must never reset this flag.
        state.stage = 'post_submit';
        state.submission_attempted = true;
      } else {
        state.stage = state.submission_attempted ? 'post_response' : 'preparing';
      }
    },
  };
}

export function xPublicationFailure(diagnostic) {
  const observation = diagnostic?.detail?.publication;
  const stage = observation?.stage || 'unknown';
  const submission_attempted = observation?.submission_attempted !== false;
  const cause = Number(diagnostic?.detail?.code) === 64 ? 'ACCOUNT_SUSPENDED'
    : ['AUTH_REQUIRED', 'AUTH_EXPIRED'].includes(diagnostic?.code) ? diagnostic.code
    : ['media_upload', 'media_metadata'].includes(stage) ? 'MEDIA_UPLOAD_FAILED'
    : submission_attempted ? 'SUBMISSION_UNKNOWN' : 'PRE_SUBMISSION_FAILED';
  return { stage, submission_attempted, failure_reason: cause,
    error: submission_attempted ? 'PUBLISH_UNKNOWN' : cause,
    state: submission_attempted ? 'unknown' : 'failed' };
}
