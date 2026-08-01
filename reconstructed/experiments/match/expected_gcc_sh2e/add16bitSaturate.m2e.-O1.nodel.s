	.file	"add16bitSaturate.c"
	.text
	.text
	.align 1
	.global	_add16bitSaturate
	.type	_add16bitSaturate, @function
_add16bitSaturate:
	extu.w	r4,r4
	extu.w	r5,r5
	mov	r4,r2
	add	r5,r2
	mov.l	.L4,r1
	cmp/hi	r1,r2
	bt	.L3
	extu.w	r2,r0
	rts	
	nop
	.align 1
.L3:
	mov.l	.L5,r0
	rts	
	nop
.L6:
	.align 2
.L4:
	.long	65534
.L5:
	.long	65535
	.size	_add16bitSaturate, .-_add16bitSaturate
	.ident	"GCC: (GNU) 14.2.0"
