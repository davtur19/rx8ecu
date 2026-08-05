# securityNotUnlocked @ 0x541F0
**Purpose:** Check if UDS/KWP2000 security access has been unlocked; compare session key/level against current unlock state.
**Inputs:** r4: expected security level or session key (e.g., 0x01 for level-1 unlock)
**Out:** r0: 0 if security level matches current unlock state (locked), 1 if mismatch (not unlocked) ; No global state changed; read-only access to security flag
**Calls:** none
Load global/RAM address 0xFFFFCFE4 into r1 (SecurityAccess state cell) ; Zero-extend r4 (extu.b r4,r4) – compare only low byte ; Load current unlock state from @r1 into r2, zero-extend (extu.b r2,r2)
; Compare r4 == r2 (cmp/eq r4,r2) ; If equal: branch to 0x54202 (set r4=1, meaning "not unlocked" / "security check failed") ; Else: fall through to 0x54200 (set r4=0, meaning "security level matches"
/ "unlocked") ; Return r0 = r4 ; _Note: Return semantics inverted: 0=secure/unlocked, 1=insecure/locked (double-negative naming)._
**Draft C:**
```c
uint8_t securityNotUnlocked(uint8_t session_level) {
  extern uint8_t security_access_state;  // @ 0xFFFFCFE4
  session_level = (uint8_t)session_level;
  uint8_t current = (uint8_t)security_access_state;
  if (session_level == current) {
    return 0;  // locked (security check passed)
  }
  return 1;   // not unlocked (mismatch)
}
```
**Status:** high – boolean logic is straightforward; equinox name confirms UDS security context.
**Uncertainties:** exact semantics: whether 0xFFFFCFE4 stores active session level or "unlocked level" flag ; whether multiple levels (0x01, 0x02, 0x03) are supported or just one bit ; expected values (0x00=locked, 0x01=level-1, etc.?)
> AI-generated structural notes only. There is **no C lift** for this 0x541F0
> path in the repo (`c/` has no reference to 0x541F0), and this function is
> **not part of the SecurityAccess handler `0x584A0`** described in
> `docs/functions/security_access_handler.md` (that handler uses RAM @0xFFFFD2x,
> not 0xFFFFCFE4/0xFFFFD0F3). Treat the RAM cell semantics below as unverified.
> For the verified 0x27 handler and seed/key flow, see `security_access_handler.md`.
