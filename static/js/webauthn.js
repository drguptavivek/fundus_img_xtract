/* WebAuthn JSON helpers shared by the web login/account pages and the grader
 * PWA: parse server options into navigator.credentials arguments and turn a
 * credential back into the JSON the server verifies. Modern browsers have
 * parseCreationOptionsFromJSON / toJSON; older Safari gets a manual fallback. */
(function () {
  function b64urlToBytes(value) {
    const padded = value.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((value.length + 3) % 4);
    return Uint8Array.from(atob(padded), c => c.charCodeAt(0));
  }
  function bytesToB64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function unwrap(options) {
    return options && options.publicKey ? options.publicKey : options;
  }
  function decodeOptions(options, paths, listKey) {
    const copy = JSON.parse(JSON.stringify(options));
    paths.forEach(path => {
      const parts = path.split('.');
      let target = copy;
      for (let i = 0; i < parts.length - 1; i += 1) target = target[parts[i]];
      target[parts[parts.length - 1]] = b64urlToBytes(target[parts[parts.length - 1]]);
    });
    (copy[listKey] || []).forEach(item => { item.id = b64urlToBytes(item.id); });
    return copy;
  }
  function parseCreation(options) {
    const inner = unwrap(options);
    return window.PublicKeyCredential && PublicKeyCredential.parseCreationOptionsFromJSON
      ? PublicKeyCredential.parseCreationOptionsFromJSON(inner)
      : decodeOptions(inner, ['challenge', 'user.id'], 'excludeCredentials');
  }
  function parseRequest(options) {
    const inner = unwrap(options);
    return window.PublicKeyCredential && PublicKeyCredential.parseRequestOptionsFromJSON
      ? PublicKeyCredential.parseRequestOptionsFromJSON(inner)
      : decodeOptions(inner, ['challenge'], 'allowCredentials');
  }
  function credentialToJSON(credential) {
    if (credential.toJSON) return credential.toJSON();
    const response = credential.response;
    const out = { id: credential.id, rawId: bytesToB64url(credential.rawId), type: credential.type,
      response: { clientDataJSON: bytesToB64url(response.clientDataJSON) } };
    if (response.attestationObject) out.response.attestationObject = bytesToB64url(response.attestationObject);
    if (response.authenticatorData) out.response.authenticatorData = bytesToB64url(response.authenticatorData);
    if (response.signature) out.response.signature = bytesToB64url(response.signature);
    if (response.userHandle) out.response.userHandle = bytesToB64url(response.userHandle);
    if (response.getTransports) out.response.transports = response.getTransports();
    return out;
  }
  function supported() {
    return Boolean(window.PublicKeyCredential && navigator.credentials && window.isSecureContext);
  }
  async function platformAuthenticatorAvailable() {
    try { return supported() && await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable(); } catch (_) { return false; }
  }
  async function create(options) {
    return credentialToJSON(await navigator.credentials.create({ publicKey: parseCreation(options) }));
  }
  async function get(options) {
    return credentialToJSON(await navigator.credentials.get({ publicKey: parseRequest(options) }));
  }
  window.WebAuthnJSON = { parseCreation, parseRequest, credentialToJSON, supported, platformAuthenticatorAvailable, create, get };
})();
