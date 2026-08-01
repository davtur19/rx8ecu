/*
 * getFromGPIO.c  —  RX-8 ECU GPIO port read with parametric routing
 *
 * Address: 0x0070D0  |  Size: 170 bytes
 *
 * Reads a GPIO port and routes the value to different output channels
 * based on an input parameter.  This is a demultiplexer for GPIO input
 * to multiple functional subsystems (e.g., fan control, A/C compressor,
 * auxiliary outputs).
 *
 * The input parameter (0, 1, or other) selects which output channels
 * receive the GPIO port value.
 *
 * Algorithm:
 *   1. Call system dispatch (0x3920) with function index
 *   2. Read GPIO port data register (0xF002)
 *   3. Write control register to select input pin
 *   4. Based on input parameter:
 *      - 0:      Call output A with (port, 0, 0)
 *                Call output B with (port, 0, 0)
 *      - 1:      Call output A with (port, 1, 0)
 *      - other:  Call output A with (port, 0, 0)
 *                Call output B with (port, 1, 0)
 *   5. Call cleanup dispatch and return
 *
 * Verified against ROM: c/tests/test_getFromGPIO.py
 */
#include <stdint.h>

/* External functions (indirect dispatch) */
extern uint32_t dispatch_3920(uint32_t r4);
extern void     gpio_output_a(uint32_t port, uint32_t data, uint32_t flags);
extern void     gpio_output_b(uint32_t port, uint32_t data, uint32_t flags);
extern uint32_t cleanup_3920(uint32_t r4);

/* 0x0070D0 — read GPIO and route to selected outputs */
uint8_t getFromGPIO(uint8_t input_sel)
{
    volatile uint8_t *gpio_port  = (volatile uint8_t *)0x0000F002;
    volatile uint8_t *ctrl_reg   = (volatile uint8_t *)0x0000F000;
    volatile uint8_t *ctrl_reg2  = (volatile uint8_t *)0x0000F001;
    volatile uint8_t *ctrl_reg3  = (volatile uint8_t *)0x0000F006;
    uint8_t port_val;

    dispatch_3920(input_sel);

    /* Select GPIO input pin via control registers */
    *ctrl_reg  = 0x00;          /* set direction to input */
    port_val   = *gpio_port;    /* read port */
    *ctrl_reg  = port_val;      /* re-latch */
    *ctrl_reg  = 0x00;          /* clear */

    /* Set alternate function register */
    *ctrl_reg2 = 0x00;          /* AF mode */
    port_val   = *gpio_port;    /* re-read */
    *ctrl_reg2 = port_val;

    /* Additional control setup */
    *ctrl_reg3 = 0x00;          /* set AF2 */

    /* Write output data to port */
    *ctrl_reg3 = 0x04;          /* set data */

    /* Route based on input selector */
    switch (input_sel) {
        case 0:
            gpio_output_a((uint32_t)-1, 0, 0);  /* all bits */
            gpio_output_b((uint32_t)-1, 0, 0);
            break;
        case 1:
            gpio_output_a((uint32_t)-1, 1, 0);
            break;
        default:
            gpio_output_a((uint32_t)-1, 0, 0);
            gpio_output_b((uint32_t)-1, 1, 0);
            break;
    }

    /* Cleanup and return */
    port_val = *gpio_port;  /* final read */
    /* reset port state */
    *gpio_port = 0xFF;
    /* call with saved data */
    dispatch_3920(cleanup_3920(0));

    return port_val;
}
