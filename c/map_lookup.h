/*
 * map_lookup.h  —  RX-8 PCM 1-D calibration-map shared declaration.
 *
 * Single canonical declaration of the Map1D descriptor (20 bytes, big-endian
 * on the SH-2E; layout documented in c/2DLookup.c) and of TwoDLookup @0x2068.
 *
 * Rationale: iat_sensor.c, coolant_temperature_sensor.c, maf_sensor_value.c
 * (and throttle_position_sensor.c) carried a stale local prototype
 *   `extern float TwoDLookup(uint32_t table_addr, float input);`
 * which does NOT match the definition in c/2DLookup.c:
 *   `float TwoDLookup(const Map1D *m, float x)`
 * (pointer vs integer first argument — ABI mismatch on callers that pass a
 * descriptor address). All users now include this header instead of
 * redeclaring the prototype; call sites cast the ROM descriptor address with
 * (const Map1D *)(uintptr_t)ADDR.
 */
#ifndef MAP_LOOKUP_H
#define MAP_LOOKUP_H

#include <stdint.h>

typedef struct {
    uint16_t     count;   /* +0  number of axis breakpoints */
    uint8_t      type;    /* +2  cell encoding + scale/offset select */
    uint8_t      _pad;    /* +3 */
    const float *axis;    /* +4  ascending breakpoints (count floats) */
    const void  *values;  /* +8  count cells, width/sign per `type` */
    float        scale;   /* +12 } result units: result = scale*interp + offset */
    float        offset;  /* +16 } (skipped when type == 0) */
} Map1D;

/* 0x2068  1-D piecewise-linear calibration-map read (see c/2DLookup.c) */
float TwoDLookup(const Map1D *m, float x);

/*
 * Map2D  —  2-D bilinear calibration-map descriptor (28 bytes, big-endian
 * on the SH-2E; layout documented in c/3dLookup.c). Shared so that 3-D
 * lookup users (e.g. c/get_ignition_dwell_time_0x94C8.c) and their callers
 * agree on one type instead of redeclaring it per file.
 */
typedef struct {
    uint16_t     count_x;   /* +0  X-axis breakpoints */
    uint16_t     count_y;   /* +2  Y-axis breakpoints */
    const float *axis_x;    /* +4 */
    const float *axis_y;    /* +8 */
    const void  *values;    /* +12 row-major [count_y][count_x] cells */
    uint8_t      type;      /* +16 0->f32 | 4->u8 | 8->u16 | 12->s8 | 16->s16 */
    uint8_t      _pad[3];
    float        scale;     /* +20 } result = interp (type 0) or scale*interp+offset */
    float        offset;    /* +24 } */
} Map2D;

/* 0x213C  u16-cell FP-input 2-D lookup, no scale/offset (see c/3dLookup.c) */
uint16_t ThreeDLookup_FP_16bit(const Map2D *m, float x, float y);

#endif /* MAP_LOOKUP_H */
