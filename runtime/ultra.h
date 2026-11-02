// The libultra declarations the runtime needs. The functions are the game's own; build/game_syms.ld
// gives their addresses.

#ifndef ULTRA_H
#define ULTRA_H

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef signed char s8;
typedef short s16;
typedef int s32;

typedef void* OSMesg;

typedef struct {
    void* mtqueue;
    void* fullqueue;
    s32 validCount;
    s32 first;
    s32 msgCount;
    OSMesg* msg;
} OSMesgQueue;

typedef struct {
    u16 type;
    u8 pri;
    u8 status;
    OSMesgQueue* retQueue;
} OSIoMesgHdr;

typedef struct {
    OSIoMesgHdr hdr;
    void* dramAddr;
    u32 devAddr;
    u32 size;
} OSIoMesg;

#define OS_MESG_NOBLOCK 0
#define OS_MESG_BLOCK 1
#define OS_MESG_PRI_NORMAL 0
#define OS_READ 0
#define OS_IM_NONE 0x00000001

// Set by the boot code, at a fixed address on every N64 game.
#define osMemSize (*(volatile u32*)0x80000318)

void osCreatePiManager(s32 pri, OSMesgQueue* cmdQ, OSMesg* cmdBuf, s32 cmdMsgCnt);
void osCreateMesgQueue(OSMesgQueue* mq, OSMesg* msg, s32 count);
s32 osRecvMesg(OSMesgQueue* mq, OSMesg* msg, s32 flag);
s32 osPiStartDma(OSIoMesg* mb, s32 priority, s32 direction, u32 devAddr, void* vAddr, u32 nbytes, OSMesgQueue* mq);
void osInvalDCache(void* vAddr, s32 nbytes);
void osInvalICache(void* vAddr, s32 nbytes);
void osWritebackDCache(void* vAddr, s32 nbytes);
void osWritebackDCacheAll(void);
u32 osSetIntMask(u32 mask);

#endif
