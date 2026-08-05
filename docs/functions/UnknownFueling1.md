# UnknownFueling1 @ 0xE458
**Purpose:** Floating-point fueling calculation that conditionally selects a scaling factor based on a load parameter, then computes a fuel delivery value using fused multiply-accumulate (fmac).
**Inputs:** @0xB594: load_parameter (float, e.g. engine load or air mass) ; @0xA440: output_fuel_value (destination) ; @0x0006D4A0: some_reference_float (used in branching logic)
**Out:** Writes computed float result to @0xA440
**Calls:** None (inline floating-point arithmetic).
Load constant 3000.0 into fr3 ; Load load_parameter from 0xB594 into fr2 ; Compare fr2 > 3000.0 ; If NOT greater: jump to return (early exit, no computation) ; Load 1.0 into fr1 ; Add fr1 + fr1 → fr1
(result: 2.0) ; Load constant 30.0 into fr6 ; Load reference float from 0x0006D4A0 into fr4 ; Compare fr1 > fr4 (test if 2.0 > reference) ; If true: load 12.0 into fr3 ; If false: load 24.0 into fr3 ;
Subtract fr3 = fr3 - fr4 (compute 12.0-ref or 24.0-ref) ; Move fr6 → fr0 (copy 30.0 to accumulator) ; Fused multiply-accumulate: fr5 = fr0*fr3 + fr5 (fr5 = 30.0 * (12-ref or 24-ref) + fr5) ; Store
result to @0xA440 ; Return
**Draft C:**
```c
void UnknownFueling1(void) {
    float load = *(float *)0xB594;
    float *output = (float *)0xA440;
    float reference = *(float *)0x0006D4A0;
    if (load <= 3000.0) return;  // Threshold gating
    float factor;
    if (2.0 > reference) {
        factor = 12.0 - reference;  // Low-load scaling
    } else {
        factor = 24.0 - reference;  // High-load scaling
    }
    *output = 30.0 * factor + *(float *)0xA440;  // Accumulate
}
```
**Status:** med — floating-point operations are clear, but lack of context makes semantic interpretation speculative. Name "UnknownFueling1" reflects uncertainty. Constants 3000, 12, 24, 30 suggest fuel calculation with load threshold and dual-mode scaling.
**Uncertainties:** What physical quantity is load_parameter? (manifold air pressure? fuel rail pressure?) ; Why threshold at 3000? (if load=bar, this is ~3 bar) ; What is reference value? (injector opening time? baseline fuel?) ; Why two scaling factors (12 vs 24)? (warm/cold, high/low speed?) ; Is 0xA440 both input and output (accumulator)?
