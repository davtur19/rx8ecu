# floatDivideDiv0errCheck_SIG_DIVISOR @ 0x3E0AC
**Purpose:** Perform floating-point division with guard against division by zero and overflow/underflow saturation.
**Inputs:** `fr4`: numerator/significand (SIG) ; `fr5`: divisor
**Out:** `fr0`: result of division, or saturated value if divisor is zero or result overflows ; If divisor == 0 and numerator == 0: return 0.0 ; If divisor == 0 and numerator > 0: return +3.40282e+38 (FLT_MAX) ; If divisor == 0 and numerator < 0: return -3.40282e+38 (-FLT_MAX) ; Otherwise: return fr4 / fr5
**Calls:** (none)
Load 0.0 into fr3: fldi0 fr3 ; Check if divisor (fr5) == 0.0: fcmp/eq fr3, fr5 ; If divisor != 0.0, jump to normal division (step 9) ; Check if numerator (fr4) == 0.0: fcmp/eq fr3, fr4 ; If numerator
!= 0.0, check sign of numerator (step 8) ; If numerator == 0.0, return 0.0 (both zero case) → load 0.0 into fr6, jump to return ; Load 0.0 into fr3 (for next check) ; Check if numerator > 0.0: fcmp/gt
fr3, fr4 ; If numerator > 0.0, load FLT_MAX (+3.40282e+38) into fr6 from pool at 0x3E318 ; If numerator <= 0.0, load -FLT_MAX (-3.40282e+38) into fr6 from pool at 0x3E31C ; Normal division path: copy
numerator fr4 → fr6 ; Perform division: fr6 = fr6 / fr5: fdiv fr5, fr6 ; NaN passthrough**: fmov fr6, fr6 (test fr6 for NaN) ; Return result in fr0: fmov fr6, fr0
**Draft C:**
```c
float floatDivideDiv0errCheck_SIG_DIVISOR(float sig, float divisor)
{
    if (divisor == 0.0f) {
        if (sig == 0.0f) {
            return 0.0f;
        } else if (sig > 0.0f) {
            return 3.40282e+38f;  // FLT_MAX
        } else {
            return -3.40282e+38f;  // -FLT_MAX
        }
    }
    float result = sig / divisor;
    // fmov fr6, fr6 serves as NaN passthrough / status check
    return result;
}
```
**Status:** high (guard logic is clear and standard; FLT_MAX constants are confirmed by pool references; division by zero handling is explicit)
**Uncertainties:** Purpose of the NaN test at the end (fmov fr6, fr6) is unclear—may be (a) defensive NaN propagation, (b) status register manipulation, or (c) debug/trap setup ; Whether the result could be NaN from a valid division (e.g., 0/0 handled by hardware) and if so, what the caller expects
