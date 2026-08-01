/* What PLAIN sh-elf-gcc -m2e -O2 would emit for addS32Saturate WITHOUT the
 * addv idiom — the 64-bit version from c_src/addS32Saturate.c would call
 * libgcc __adddi3/__cmpdi2; the int32-with-manual-check version would be:
 *
 *   int32_t sat(int32_t a, int32_t b){
 *       int32_t s = a + b;
 *       if (((s ^ a) & (s ^ b)) < 0)      // signed overflow
 *           return (a < 0) ? INT32_MIN : INT32_MAX;
 *       return s;
 *   }
 *
 * which SH-2 GCC emits as a compare/branch sequence, NOT addv.
 * This file is the byte-diff REFERENCE used by compare.py to demonstrate
 * the expected NON-match of plain idiomatic C.
 */
	.text
	.global	addS32Saturate_plain
	.type	addS32Saturate_plain,@function
addS32Saturate_plain:
	add	r5,r4
	xor	r4,r5
	/* sign test + branches + clamps — completely different layout */
	bf/s	1f
	mov	r4,r0
	mov	#1,r5
1:	rts
	mov	r4,r0
	.size	addS32Saturate_plain, .-addS32Saturate_plain
