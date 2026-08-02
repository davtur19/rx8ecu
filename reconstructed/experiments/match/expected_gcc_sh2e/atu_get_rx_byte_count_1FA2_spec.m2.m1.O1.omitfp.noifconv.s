	.file	"atu_get_rx_byte_count_1FA2_spec.c"
	.text
	.text
	.align 1
	.global	_atu_get_rx_byte_count
	.type	_atu_get_rx_byte_count, @function
_atu_get_rx_byte_count:
	extu.b	r4,r4
	mov	#32,r3
	cmp/ge	r3,r4
	bt	.L2
	bra	.L3
	mov	r5,r4
	.align 1
.L2:
	mov.w	.L4,r4
	add	r5,r4
.L3:
	rts	
	mov	r4,r0
	.align 1
.L4:
	.short	512
	.size	_atu_get_rx_byte_count, .-_atu_get_rx_byte_count
	.ident	"GCC: (GNU) 3.3.6"
