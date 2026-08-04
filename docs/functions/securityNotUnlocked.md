# securityNotUnlocked @ 0x541F0
_source: AI (Haiku) draft, unverified_

> AI-generated structural notes only. There is **no C lift** for this 0x541F0
> path in the repo (`c/` has no reference to 0x541F0), and this function is
> **not part of the SecurityAccess handler `0x584A0`** described in
> `docs/functions/security_access_handler.md` (that handler uses RAM @0xFFFFD2x,
> not 0xFFFFCFE4/0xFFFFD0F3). Treat the RAM cell semantics below as unverified.
> For the verified 0x27 handler and seed/key flow, see `security_access_handler.md`.

**Purpose:** Check if UDS/KWP2000 security access has been unlocked; compare session key/level against current unlock state.

**Inputs:**
- r4: expected security level or session key (e.g., 0x01 for level-1 unlock)

**Outputs / side effects:**
- r0: 0 if security level matches current unlock state (locked), 1 if mismatch (not unlocked)
- No global state changed; read-only access to security flag

**Calls:** none

**Behavior:**
1. Load global/RAM address 0xFFFFCFE4 into r1 (SecurityAccess state cell)
2. Zero-extend r4 (extu.b r4,r4) – compare only low byte
3. Load current unlock state from @r1 into r2, zero-extend (extu.b r2,r2)
4. Compare r4 == r2 (cmp/eq r4,r2)
5. If equal: branch to 0x54202 (set r4=1, meaning "not unlocked" / "security check failed")
6. Else: fall through to 0x54200 (set r4=0, meaning "security level matches" / "unlocked")
7. Return r0 = r4

_Note: Return semantics inverted: 0=secure/unlocked, 1=insecure/locked (double-negative naming)._

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

**Confidence:** high – boolean logic is straightforward; equinox name confirms UDS security context.

**Uncertainties:**
- exact semantics: whether 0xFFFFCFE4 stores active session level or "unlocked level" flag
- whether multiple levels (0x01, 0x02, 0x03) are supported or just one bit
- expected values (0x00=locked, 0x01=level-1, etc.?)
