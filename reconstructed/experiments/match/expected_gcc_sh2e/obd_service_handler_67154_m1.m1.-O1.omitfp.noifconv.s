	.file	"obd_service_handler_67154_m1.c"
	.text
	.text
	.align 1
	.global	_obd_service_handler_67154
	.type	_obd_service_handler_67154, @function
_obd_service_handler_67154:
	mov	r4,r0
	and	#31,r0
	tst	r0,r0
	bf	.L2
	bra	.L3
	mov	#0,r4
	.align 1
.L2:
	mov	#1,r4
.L3:
	rts	
	mov	r4,r0
	.size	_obd_service_handler_67154, .-_obd_service_handler_67154
	.ident	"GCC: (GNU) 3.4.6"
