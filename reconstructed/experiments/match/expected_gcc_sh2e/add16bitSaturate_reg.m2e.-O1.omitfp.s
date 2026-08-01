	.file	"add16bitSaturate_reg.c"
	.text
	.text
	.align 1
	.global	_add16bitSaturate
	.type	_add16bitSaturate, @function
_add16bitSaturate:
	extu.w	r4,r4
	extu.w	r5,r5
	add	r5,r4
	mov.l	.L3,r5
	cmp/hs	r5,r4
	bf.s	.L2
	nop
	mov	r5,r4
.L2:
	rts	
	mov	r4,r0
.L4:
	.align 2
.L3:
	.long	65535
	.size	_add16bitSaturate, .-_add16bitSaturate
	.ident	"GCC: (GNU) 3.4.6"
