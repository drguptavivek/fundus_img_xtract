"""WebAuthn passkeys for mobile-token sessions.

Passkeys are the biometric re-authentication method for the grader: after a
password login, a user registers the platform authenticator (Touch ID, Face
ID, Windows Hello); after 30 idle minutes an assertion proves identity again
without the password. Both ceremonies are verified server-side with
``fido2``; the client never holds a secret the server trusts blindly.
"""
