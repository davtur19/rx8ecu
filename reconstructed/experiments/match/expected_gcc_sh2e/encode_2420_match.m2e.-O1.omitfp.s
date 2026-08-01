	.file	"encode_2420_match.c"
	.text
	.text
	.align 1
	.global	_encode_2420
	.type	_encode_2420, @function
_encode_2420:
	extu.b	r4,r3
	shll8	r3
	not	r4,r2
	extu.b	r2,r2
	mov	r3,r4
	add	r2,r4
	rts	
	mov	r4,r0
	.size	_encode_2420, .-_encode_2420
	.ident	"GCC: (GNU) 3.4.6"
