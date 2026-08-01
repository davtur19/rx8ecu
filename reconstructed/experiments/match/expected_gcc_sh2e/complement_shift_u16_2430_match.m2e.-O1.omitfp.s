	.file	"complement_shift_u16_2430_match.c"
	.text
	.text
	.align 1
	.global	_complement_shift_u16
	.type	_complement_shift_u16, @function
_complement_shift_u16:
	extu.w r4,r3
	shll16	r3
	not	r4,r2
	extu.w	r2,r2
	mov	r3,r4
	add	r2,r4
	rts	
	mov	r4,r0
	.size	_complement_shift_u16, .-_complement_shift_u16
	.ident	"GCC: (GNU) 3.4.6"
