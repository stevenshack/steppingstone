#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <stdarg.h>
#include <setjmp.h>
#include <unistd.h>
#include <errno.h>
#include <sys/stat.h>

static uint8_t mem[0x1000000];  /* 16 MB */
static jmp_buf exit_jmp;
static int trace = 0;

typedef struct {
    uint32_t d[8], a[8], pc;
    uint16_t sr;
    int halted;
} CPU;

#define C 1
#define V 2
#define Z 4
#define N 8
#define X 16
#define F_(c,f) (((c)->sr >> ((f)-1)) & 1)
#define SF(c,f,v) do { if(v) (c)->sr |= (1<<((f)-1)); else (c)->sr &= ~(1<<((f)-1)); } while(0)

static uint8_t  rb(CPU *c, uint32_t a) { return a < 0x1000000 ? mem[a] : 0; }
static uint16_t rw(CPU *c, uint32_t a) { return (uint16_t)rb(c,a)<<8 | rb(c,a+1); }
static uint32_t rl(CPU *c, uint32_t a) { return (uint32_t)rw(c,a)<<16 | rw(c,a+2); }
static void wb(CPU *c, uint32_t a, uint8_t v) { if (a < 0x1000000) mem[a] = v; }
static void ww(CPU *c, uint32_t a, uint16_t v) { wb(c,a,v>>8); wb(c,a+1,v&0xFF); }
static void wl(CPU *c, uint32_t a, uint32_t v) { ww(c,a,v>>16); ww(c,a+2,v&0xFFFF); }

typedef struct { int m, r, spc; int32_t d; int ixr, ixa, ixl; } EA;

static int dea(CPU *c, uint16_t op, EA *e) {
    int b = op & 0x3F, m = (b>>3)&7, r = b&7;
    e->m = m; e->r = r; e->spc = 0; e->d = 0; e->ixr=e->ixa=e->ixl=0;
    if (m <= 4) return 0;
    if (m == 5) { e->d = (int16_t)rw(c,c->pc); c->pc += 2; return 0; }
    if (m == 6) {
        uint16_t x = rw(c,c->pc); c->pc += 2;
        e->d = (int8_t)(x&0xFF); e->ixr = (x>>12)&7; e->ixa = (x>>15)&1; e->ixl = (x>>11)&1;
        return 0;
    }
    e->m = 7; e->spc = r;
    if (r == 0) { e->d = (int16_t)rw(c,c->pc); c->pc += 2; }
    else if (r == 1) { e->d = rl(c,c->pc); c->pc += 4; }
    else if (r == 2) { e->d = (int16_t)rw(c,c->pc); c->pc += 2; }
    else if (r == 3) {
        uint16_t x = rw(c,c->pc); c->pc += 2;
        e->d = (int8_t)(x&0xFF); e->ixr = (x>>12)&7; e->ixa = (x>>15)&1; e->ixl = (x>>11)&1;
    }
    return 0;
}

static void ear(CPU *c, EA *e, int sz, uint32_t *pa, int *pm) {
    uint32_t a = 0; int mem = 1;
    if (e->m == 0) { a = e->r; mem = 0; }
    else if (e->m == 1) { a = e->r; mem = 0; }
    else if (e->m == 2) { a = c->a[e->r]; }
    else if (e->m == 3) { a = c->a[e->r]; c->a[e->r] += sz; }
    else if (e->m == 4) { c->a[e->r] -= sz; a = c->a[e->r]; }
    else if (e->m == 5) { a = c->a[e->r] + e->d; }
    else if (e->m == 6) { uint32_t ix = e->ixa ? c->a[e->ixr] : c->d[e->ixr]; if (!e->ixl) ix = (int16_t)ix; a = c->a[e->r] + (int32_t)ix + e->d; }
    else if (e->m == 7) {
        if (e->spc == 0) a = (int16_t)e->d;
        else if (e->spc == 1) a = e->d;
        else if (e->spc == 2) a = c->pc + e->d;
        else if (e->spc == 3) { uint32_t ix = e->ixa ? c->a[e->ixr] : c->d[e->ixr]; if (!e->ixl) ix = (int16_t)ix; a = c->pc + (int32_t)ix + e->d; }
        else if (e->spc == 4) { /* immediate - handled in erd() */ mem = 0; a = 0; }
        else { mem = 0; a = e->d; }
    }
    *pa = a; *pm = mem;
}

static uint32_t erd(CPU *c, EA *e, int sz) {
    if (e->m == 7 && e->spc == 4) {
        uint32_t v = rw(c, c->pc); c->pc += 2;
        if (sz == 2) { v = (v << 16) | rw(c, c->pc); c->pc += 2; }
        return v;
    }
    uint32_t a; int m;
    ear(c, e, sz, &a, &m);
    if (!m) {
        if (e->m == 0) { return sz==0 ? (uint8_t)c->d[a] : sz==1 ? (uint16_t)c->d[a] : c->d[a]; }
        if (e->m == 1) { return sz==1 ? (uint16_t)c->a[a] : c->a[a]; }
        return 0;
    }
    return sz==0 ? rb(c,a) : sz==1 ? rw(c,a) : rl(c,a);
}

static void ewr(CPU *c, EA *e, uint32_t v, int sz) {
    uint32_t a; int m;
    ear(c, e, sz, &a, &m);
    if (!m) {
        if (e->m == 0) { if (sz==0) c->d[a]=(c->d[a]&~0xFF)|(v&0xFF); else if (sz==1) c->d[a]=(c->d[a]&~0xFFFF)|(v&0xFFFF); else c->d[a]=v; }
        if (e->m == 1) { if (sz==1) c->a[a]=(int16_t)v; else c->a[a]=v; }
        return;
    }
    if (sz==0) wb(c,a,v&0xFF); else if (sz==1) ww(c,a,v&0xFFFF); else wl(c,a,v);
}

static int cc(CPU *c, int cond) {
    int n=F_(c,N),z=F_(c,Z),v=F_(c,V),c_=F_(c,C);
    switch (cond) {
        case 0: return 1; case 1: return 0;
        case 2: return !c_&&!z; case 3: return c_||z;
        case 4: return !c_; case 5: return c_;
        case 6: return !z; case 7: return z;
        case 8: return !v; case 9: return v;
        case 10: return !n; case 11: return n;
        case 12: return n==v; case 13: return n!=v;
        case 14: return n==v&&!z; case 15: return n!=v||z;
    }
    return 0;
}

static char tn[256][64];
static uint32_t ta[256];
static int tc = 0;
static uint32_t na = 0x80000;

static void reg_thunk(CPU *c, const char *name, int fid) {
    strcpy(tn[tc], name);
    uint32_t a = na; na += 8;
    ww(c, a,   0x7000 | (uint8_t)(int8_t)fid);
    ww(c, a+2, 0x4E4E);
    ww(c, a+4, 0x4E75);
    ta[tc++] = a;
}

static int tdisp(CPU *c, int vec);

static int dinstr(CPU *c) {
    uint16_t op = rw(c, c->pc); c->pc += 2;
    int cat = (op>>12)&0xF;

    if (trace) fprintf(stderr, "P%06x O%04x C%d d0=%08x a7=%08x\n", c->pc-2, op, cat, c->d[0], c->a[7]);

    if (cat >= 1 && cat <= 3) {
        int dr = (op>>11)&1, reg = (op>>9)&7, sz = cat==1?0:cat==3?1:2;
        /* MOVE uses 8-bit EA in bits 7-0: bits 7-6=mode(2), bits 5-3=reg(3), bits 2-0=0 */
        int ea_mode = (op >> 6) & 3;    /* bits 7-6 = 2-bit mode */
        int ea_reg = (op >> 3) & 7;     /* bits 5-3 = register */
        int ea_spc = (op >> 3) & 7;     /* for mode=7: bits 5-3 = subtype */
        int is_mem = 1;
        uint32_t ea_addr = 0;
        
        /* Decode MOVE-specific 8-bit EA */
        if (ea_mode == 3) { /* mode 7: special */
            if (ea_reg == 0) { ea_addr = (int16_t)rw(c,c->pc); c->pc += 2; } /* abs.W */
            else if (ea_reg == 1) { ea_addr = rl(c,c->pc); c->pc += 4; } /* abs.L */
            else if (ea_reg == 2) { ea_addr = c->pc + (int16_t)rw(c,c->pc); c->pc += 2; } /* (d16,PC) */
            else if (ea_reg == 3) { /* (d8,PC,Xn) */
                uint16_t x = rw(c,c->pc); c->pc += 2;
                uint32_t ix = (x>>15) ? c->a[(x>>12)&7] : c->d[(x>>12)&7];
                if (!(x&0x0800)) ix = (int16_t)ix;
                ea_addr = c->pc + (int8_t)(x&0xFF) + (int32_t)ix;
            }
            else if (ea_reg == 4) { is_mem = 0; ea_addr = 0; } /* immediate */
            else { c->halted=1; return 0; }
        } else if (ea_mode == 0) { is_mem = 0; ea_addr = ea_reg; } /* Dn direct */
        else if (ea_mode == 1) { is_mem = 0; ea_addr = ea_reg; } /* An direct */
        else if (ea_mode == 2) { ea_addr = c->a[ea_reg]; } /* (An) */
        /* mode == 2 && reg == ?: (An)+ would need mode=3 */
        /* The 8-bit EA for MOVE has: mode in bits 7-6, reg in bits 5-3, with bits 2-0 always 0.
           Modes 0-3: Dn, An, (An), (An)+. Wait, that only gives 4 modes (0-3) but we need 5-7 too. */
        
        /* Actually, for MOVE the 8-bit EA encoding is:
           Mode 0: (ea_mode=0) Dn - reg in ea_reg
           Mode 1: (ea_mode=1) An - reg in ea_reg  
           Mode 2: (ea_mode=2) (An) - reg in ea_reg
           Mode 3: (ea_mode=3) (An)+ - reg in ea_reg
           Then modes 4-7 need the full 6-bit EA encoded in bits 5-0. */
        
        /* For modes 0-3: ea_mode (bits 7-6) = 0-3 */
        if (ea_mode == 0) { is_mem = 0; ea_addr = ea_reg; }      /* Dn */
        else if (ea_mode == 1) { is_mem = 0; ea_addr = ea_reg; } /* An */
        else if (ea_mode == 2) { ea_addr = c->a[ea_reg]; }       /* (An) */
        else if (ea_mode == 3) { ea_addr = c->a[ea_reg]; c->a[ea_reg] += sz; } /* (An)+ */
        
        /* For modes 4-6, use the 6-bit EA standard. Mode=4 is -(An) which conflicts with 
           the 8-bit format. Let me use a hybrid: if ea_mode=3 and ea_reg>=4, use 6-bit EA. */
        /* NO - the issue is that the 2-bit mode can only encode 0-3. For modes 4-6,  
           ea_mode=2 or 3 with ea_reg encoding the extended info. */
        /* Actually, in the 8-bit EA for MOVE:
           Mode 0: bits 7-6=00, bits 5-3=reg [Dn]
           Mode 1: bits 7-6=01, bits 5-3=reg [An]
           Mode 2: bits 7-6=10, bits 5-3=reg [(An)]
           Mode 3: bits 7-6=11, bits 5-3=reg [special/extended]
           Within mode 3, reg in bits 5-3 tells us:
             000 = (An)+
             001 = -(An)
             010 = (d16,An)
             011 = (d8,An,Xn)
             100 = abs.W
             101 = abs.L
             110 = d16(PC)
             111 = d8(PC,Xn) */
        
        if (ea_mode < 2) {
            is_mem = 0; ea_addr = ea_reg;
        } else if (ea_mode == 2) {
            if (ea_reg <= 3) { ea_addr = c->a[ea_reg]; } /* (An) */
            else if (ea_reg == 4) { ea_addr = c->a[ea_reg&3]; c->a[ea_reg&3] += sz; } /* (An)+ */
            else if (ea_reg == 5) { c->a[ea_reg&3] -= sz; ea_addr = c->a[ea_reg&3]; } /* -(An) */
            else if (ea_reg <= 7) { ea_addr = c->a[ea_reg&3] + (int16_t)rw(c,c->pc); c->pc += 2; } /* (d16,An) */
        } else { /* ea_mode == 3 */
            if (ea_reg <= 3) { ea_addr = c->a[ea_reg]; c->a[ea_reg] += sz; } /* (An)+ */
            else if (ea_reg == 4) { c->a[ea_reg] -= sz; ea_addr = c->a[ea_reg]; } /* -(An) - WRONG: ea_reg should be 0-3 */
            /* This encoding is getting too complex. Let me use a simpler approach: */
        }
        
        /* SIMPLER APPROACH: Use the standard 6-bit EA in bits 5-0, but use the full
           8-bit byte to determine the EA correctly for MOVE. The reality is that M68000
           uses the 6-bit EA format for ALL instructions including MOVE. */
        
        /* Let me re-do this properly with the 6-bit EA: */
        /* Actually, I think the issue is that I should use the 6-bit EA in bits 5-0,
           but I was using `op & 0x3F` which is `op & 0x3F` which gives only bits 5-0.
           For MOVE, the destination EA (when dr=0) uses the full 8 bits but the 6-bit
           EA interpretation should still work. */
        
        /* OK, let me try a completely different approach. For the instruction at 0x3DEE:
           0x23C0 = 0010 0011 1100 0000
           dr=1 (bit 11 = 1), reg=1 (D1 or A1)
           bits 5-0 = 000000 = mode 0 reg 0 = D0
           So MOVE.L D0, D1 (move D0 to D1)
           
           But this doesn't account for the 0x0000 0x4004 following.
           
           The CORRECT interpretation uses 6-bit EA in bits 5-0. For 0x23C0:
           EA = 0x23C0 & 0x3F = 0x00 = mode 0 reg 0 = D0
           dr=1 → source=EA=D0, dest=D1
           MOVE.L D0, D1 */
        
        /* Use standard 6-bit EA */
        EA e; dea(c, op, &e);
        
        if (dr) {
            uint32_t v = erd(c, &e, sz);
            if (reg < 8) {
                if (sz==0) c->d[reg]=(c->d[reg]&~0xFF)|(v&0xFF);
                else if (sz==1) c->d[reg]=(c->d[reg]&~0xFFFF)|(v&0xFFFF);
                else c->d[reg]=v;
                SF(c,N,sz==0?(v&0x80):sz==1?(v&0x8000):(v&0x80000000));
                SF(c,Z,v==0); SF(c,V,0); SF(c,C,0);
            } else {
                if (sz==1) c->a[reg&7]=(int16_t)v; else c->a[reg&7]=v;
            }
        } else {
            uint32_t v = (reg<8) ? (sz==0?c->d[reg]&0xFF:sz==1?c->d[reg]&0xFFFF:c->d[reg]) : c->a[reg&7];
            ewr(c, &e, v, sz);
            if (reg < 8) {
                SF(c,N,sz==0?(v&0x80):sz==1?(v&0x8000):(v&0x80000000));
                SF(c,Z,sz==0?(v&0xFF)==0:sz==1?(v&0xFFFF)==0:v==0);
                SF(c,V,0); SF(c,C,0);
            }
            return 0;
        }
    }

    if (cat == 0) {
        if ((op&0xFFC0)==0x0000){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0)|(im&0xFF);ewr(c,&e,v,0);SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0040){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1)|im;ewr(c,&e,v,1);SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0080){uint32_t im=rl(c,c->pc);c->pc+=4;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2)|im;ewr(c,&e,v,2);SF(c,N,v&0x80000000);SF(c,Z,v==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0200){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0)&(im&0xFF);ewr(c,&e,v,0);SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0240){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1)&im;ewr(c,&e,v,1);SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0280){uint32_t im=rl(c,c->pc);c->pc+=4;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2)&im;ewr(c,&e,v,2);SF(c,N,v&0x80000000);SF(c,Z,v==0);SF(c,V,0);SF(c,C,0);return 0;}
        if ((op&0xFFC0)==0x0400){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0);uint32_t r=v-(im&0xFF);ewr(c,&e,r,0);SF(c,N,r&0x80);SF(c,Z,(r&0xFF)==0);SF(c,V,((v^(im&0xFF))&(v^r))&0x80?1:0);SF(c,C,v<(im&0xFF));return 0;}
        if ((op&0xFFC0)==0x0440){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1);uint32_t r=v-im;ewr(c,&e,r,1);SF(c,N,r&0x8000);SF(c,Z,(r&0xFFFF)==0);SF(c,V,((v^im)&(v^r))&0x8000?1:0);SF(c,C,v<im);return 0;}
        if ((op&0xFFC0)==0x0480){uint32_t im=rl(c,c->pc);c->pc+=4;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2);uint32_t r=v-im;ewr(c,&e,r,2);SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,((v^im)&(v^r))&0x80000000?1:0);SF(c,C,v<im);return 0;}
        if ((op&0xFFC0)==0x0600){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0);uint32_t r=v+(im&0xFF);ewr(c,&e,r,0);SF(c,N,r&0x80);SF(c,Z,(r&0xFF)==0);SF(c,V,((~(v^(im&0xFF)))&(v^r))&0x80?1:0);SF(c,C,r&0x100?1:0);return 0;}
        if ((op&0xFFC0)==0x0640){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1);uint32_t r=v+im;ewr(c,&e,r,1);SF(c,N,r&0x8000);SF(c,Z,(r&0xFFFF)==0);SF(c,V,((~(v^im))&(v^r))&0x8000?1:0);SF(c,C,(uint32_t)(v+im)&0x10000?1:0);return 0;}
        if ((op&0xFFC0)==0x0680){uint32_t im=rl(c,c->pc);c->pc+=4;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2);uint32_t r=v+im;ewr(c,&e,r,2);SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,((~(v^im))&(v^r))&0x80000000?1:0);SF(c,C,(uint64_t)v+im>0xFFFFFFFF);return 0;}
        if ((op&0xFFC0)==0x0C00){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0);uint32_t r=v-(im&0xFF);SF(c,N,r&0x80);SF(c,Z,(r&0xFF)==0);SF(c,V,((v^(im&0xFF))&(v^r))&0x80?1:0);SF(c,C,v<(im&0xFF));return 0;}
        if ((op&0xFFC0)==0x0C40){uint16_t im=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1);uint32_t r=v-im;SF(c,N,r&0x8000);SF(c,Z,(r&0xFFFF)==0);SF(c,V,((v^im)&(v^r))&0x8000?1:0);SF(c,C,v<im);return 0;}
        if ((op&0xFFC0)==0x0C80){uint32_t im=rl(c,c->pc);c->pc+=4;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2);uint32_t r=v-im;SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,((v^im)&(v^r))&0x80000000?1:0);SF(c,C,v<im);return 0;}
        if ((op&0xF1C0)==0x0100) {
            int bo=(op>>6)&3, reg=(op>>9)&7; EA e;dea(c,op,&e);
            uint32_t v=erd(c,&e,0); int bit=c->d[reg]&31, bv=(v>>bit)&1;
            SF(c,Z,!bv);
            if(bo==1)v^=1<<bit;else if(bo==2)v&=~(1<<bit);else if(bo==3)v|=1<<bit;
            if(bo)ewr(c,&e,v,0);
            return 0;
        }
        if ((op&0xFFC0)==0x0800){uint16_t ex=rw(c,c->pc);c->pc+=2;EA e;dea(c,op,&e);int bit=ex&31;SF(c,Z,!((erd(c,&e,0)>>bit)&1));return 0;}
        if ((op&0xFFC0)==0x0840){c->halted=1;return 0;}
        if ((op&0xFFC0)==0x0880){c->halted=1;return 0;}
        if ((op&0xFFC0)==0x08C0){c->halted=1;return 0;}
        c->halted=1; return 0;
    }

    /* ========= Category 4 ========= */
    if (cat == 4) {
        int ext = (op >> 6) & 0x3F;

        /* NEGX (0-2), CLR (8-10), NEG (16-18), NOT (24-26) */
        if (ext <= 2) { int sz[]={0,1,2}; int s=sz[ext]; EA e;dea(c,op,&e);
            uint32_t v=erd(c,&e,s); uint32_t r=-v; ewr(c,&e,r,s);
            if(ext==0){ SF(c,C,v!=0);SF(c,V,v==(s==0?0x80:s==1?0x8000:0x80000000));SF(c,Z,r==0);SF(c,N,s==0?(r&0x80):s==1?(r&0x8000):(r&0x80000000)); }
            return 0; }
        if (ext >= 8 && ext <= 10) { int sz[]={0,1,2}; int s=sz[ext-8]; EA e;dea(c,op,&e); ewr(c,&e,0,s); SF(c,N,0);SF(c,Z,1);SF(c,V,0);SF(c,C,0); return 0; }
        if (ext >= 16 && ext <= 18) { int sz[]={0,1,2}; int s=sz[ext-16]; EA e;dea(c,op,&e);
            uint32_t v=erd(c,&e,s); uint32_t r=-v; ewr(c,&e,r,s);
            SF(c,C,v!=0);SF(c,V,v==(s==0?0x80:s==1?0x8000:0x80000000));SF(c,Z,r==0);SF(c,N,s==0?(r&0x80):s==1?(r&0x8000):(r&0x80000000)); return 0; }
        if (ext >= 24 && ext <= 26) { int sz[]={0,1,2}; int s=sz[ext-24]; EA e;dea(c,op,&e);
            uint32_t v=erd(c,&e,s); v=~v; ewr(c,&e,v,s);
            SF(c,C,0);SF(c,V,0);SF(c,Z,(v&(s==0?0xFF:s==1?0xFFFF:0xFFFFFFFF))==0);
            SF(c,N,s==0?(v&0x80):s==1?(v&0x8000):(v&0x80000000)); return 0; }

        /* NBCD, SWAP, PEA, EXT */
        if (ext >= 32 && ext <= 34) {
            int reg = (op >> 9) & 7;
            if ((op&0xFFF8)==0x4840) { /* SWAP */ uint32_t v=c->d[reg]; c->d[reg]=(v<<16)|(v>>16);
                SF(c,N,c->d[reg]&0x80000000);SF(c,Z,c->d[reg]==0);SF(c,V,0);SF(c,C,0); return 0; }
            if ((op&0xFFC0)==0x4840) { /* PEA */ EA e;dea(c,op,&e); uint32_t a; int m; ear(c,&e,4,&a,&m);
                c->a[7]-=4; wl(c,c->a[7],a); return 0; }
            if (ext == 34) { /* EXT.W/L */
                int sz2 = (op >> 6) & 3;
                if (sz2 == 2) { c->d[reg]=(c->d[reg]&~0xFFFF)|(uint16_t)(int8_t)c->d[reg]; SF(c,N,c->d[reg]&0x8000);SF(c,Z,(c->d[reg]&0xFFFF)==0);SF(c,V,0);SF(c,C,0); }
                else if (sz2 == 3) { c->d[reg]=(int16_t)c->d[reg]; SF(c,N,c->d[reg]&0x80000000);SF(c,Z,c->d[reg]==0);SF(c,V,0);SF(c,C,0); }
                return 0;
            }
            return 0;
        }

        /* LEA */
        if ((op & 0x01C0) == 0x01C0) {
            if (((op>>6)&7) == 7) {
                int reg = (op>>9)&7; EA e; dea(c,op,&e);
                uint32_t a; int m; ear(c,&e,4,&a,&m); c->a[reg] = a; return 0;
            }
        }

        /* TST (40-42), MULU (48), MULS (49), DIVU (50), DIVS (51), TAS (43-47) */
        if (ext >= 40 && ext <= 42) { int sz[]={0,1,2}; int s=sz[ext-40]; EA e;dea(c,op,&e);
            uint32_t v=erd(c,&e,s);
            if(s==0){SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);}else if(s==1){SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);}else{SF(c,N,v&0x80000000);SF(c,Z,v==0);}
            SF(c,V,0);SF(c,C,0); return 0; }
        if (ext >= 48 && ext <= 51) {
            int is_signed = (ext & 1), is_div = (ext >= 50), reg = (op>>9)&7;
            EA e; dea(c,op,&e); uint16_t s = erd(c,&e,1);
            if (is_div && s == 0) { c->halted=1; return 0; }
            if (!is_div) {
                if (!is_signed) { uint32_t r = c->d[reg] * s; c->d[reg]=r; SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,0);SF(c,C,0); }
                else { int32_t r = (int16_t)c->d[reg] * (int16_t)s; c->d[reg]=r; SF(c,N,r<0);SF(c,Z,r==0);SF(c,V,0);SF(c,C,0); }
            } else {
                if (!is_signed) { uint32_t dd=c->d[reg]; c->d[reg]=((dd%s)<<16)|(dd/s); uint16_t q=dd/s; SF(c,N,q&0x8000);SF(c,Z,q==0);SF(c,V,0);SF(c,C,0); }
                else { int32_t dd=(int32_t)c->d[reg]; int16_t q=dd/(int16_t)s; int16_t r=dd%(int16_t)s; c->d[reg]=((uint16_t)r<<16)|(uint16_t)q; SF(c,N,q<0);SF(c,Z,q==0);SF(c,V,0);SF(c,C,0); }
            }
            return 0;
        }
        if (ext >= 43 && ext <= 47) { EA e;dea(c,op,&e); uint32_t v=erd(c,&e,0); SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0); ewr(c,&e,v|0x80,0); return 0; }

        /* 0x4Exx: TRAP, LINK, UNLK, RTS, JSR, JMP, NOP, STOP */
        if ((op & 0xFF00) == 0x4E00) {
            if (op == 0x4E71) return 0; /* NOP */
            if (op == 0x4E75) { c->pc = rl(c,c->a[7]); c->a[7]+=4; return 0; } /* RTS */
            if (op == 0x4E77) { c->halted=1; return 0; } /* RTE */
            if ((op & 0xFFF0) == 0x4E40) { tdisp(c, op&0xF); return 0; } /* TRAP */
            if ((op & 0xFFF8) == 0x4E50) { int r=op&7; int16_t d=rw(c,c->pc);c->pc+=2; c->a[7]-=4;wl(c,c->a[7],c->a[r]);c->a[r]=c->a[7];c->a[7]+=d; return 0; } /* LINK */
            if ((op & 0xFFF8) == 0x4E58) { int r=op&7; c->a[7]=c->a[r];c->a[r]=rl(c,c->a[7]);c->a[7]+=4; return 0; } /* UNLK */
            if ((op & 0xFFC0) == 0x4E80) { EA e; dea(c,op,&e); uint32_t a; int m; ear(c,&e,4,&a,&m); c->a[7]-=4; wl(c,c->a[7],c->pc); c->pc = a; return 0; } /* JSR */
            if ((op & 0xFFC0) == 0x4EC0) { EA e; dea(c,op,&e); uint32_t a; int m; ear(c,&e,4,&a,&m); c->pc = a; return 0; } /* JMP */
            c->halted=1; return 0;
        }

        c->halted=1; return 0;
    }

    /* Cat 5 */
    if (cat == 5) {
        int cond = (op>>8)&0xF, om = (op>>6)&3;
        if (om == 1) {
            int d = ((op>>9)&7); if(d==0)d=8;
            int sz[]={0,1,2}; int s=sz[(op>>6)&3];
            EA e; dea(c,op,&e);
            if (e.m == 1) { c->a[e.r] += d; return 0; }
            uint32_t v=erd(c,&e,s), r=v+d; ewr(c,&e,r,s);
            if(s==0){SF(c,N,r&0x80);SF(c,Z,(r&0xFF)==0);SF(c,V,((~(v^d))&(v^r))&0x80?1:0);SF(c,C,r&0x100?1:0);}
            else if(s==1){SF(c,N,r&0x8000);SF(c,Z,(r&0xFFFF)==0);SF(c,V,((~(v^d))&(v^r))&0x8000?1:0);SF(c,C,(uint32_t)(v+d)&0x10000?1:0);}
            else{SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,((~(v^d))&(v^r))&0x80000000?1:0);SF(c,C,(uint64_t)v+d>0xFFFFFFFF);}
            return 0;
        }
        if (om == 3) {
            int d = ((op>>9)&7); if(d==0)d=8;
            int sz[]={0,1,2}; int s=sz[(op>>6)&3];
            EA e; dea(c,op,&e);
            if (e.m == 1) { c->a[e.r] -= d; return 0; }
            uint32_t v=erd(c,&e,s), r=v-d; ewr(c,&e,r,s);
            if(s==0){SF(c,N,r&0x80);SF(c,Z,(r&0xFF)==0);SF(c,V,((v^d)&(v^r))&0x80?1:0);SF(c,C,v<(uint32_t)d);}
            else if(s==1){SF(c,N,r&0x8000);SF(c,Z,(r&0xFFFF)==0);SF(c,V,((v^d)&(v^r))&0x8000?1:0);SF(c,C,v<(uint32_t)d);}
            else{SF(c,N,r&0x80000000);SF(c,Z,r==0);SF(c,V,((v^d)&(v^r))&0x80000000?1:0);SF(c,C,v<(uint32_t)d);}
            return 0;
        }
        if (om == 0) { EA e; dea(c,op,&e); ewr(c,&e,cc(c,cond)?0xFF:0,0); return 0; }
        if (om == 2) { int reg=op&7; int16_t d=rw(c,c->pc);c->pc+=2;
            if(!cc(c,cond)){uint16_t cnt=(c->d[reg]&0xFFFF)-1;c->d[reg]=(c->d[reg]&~0xFFFF)|cnt;if(cnt!=0xFFFF)c->pc+=d;}
            return 0;
        }
        return 0;
    }

    /* Cat 6: Bcc */
    if (cat == 6) {
        int cond = (op>>8)&0xF; int8_t d8 = op&0xFF;
        if (d8 == 0) { int16_t d16=rw(c,c->pc);c->pc+=2; if(cond==0||cc(c,cond))c->pc+=d16; return 0; }
        if (d8 == -1) { int16_t hi=rw(c,c->pc);c->pc+=2; int16_t lo=rw(c,c->pc);c->pc+=2; int32_t d=((uint16_t)hi<<16)|(uint16_t)lo;
            if(cond==1){c->a[7]-=4;wl(c,c->a[7],c->pc);c->pc+=d;}
            else if(cond==0||cc(c,cond))c->pc+=d;
            return 0; }
        if (cond == 0) { c->pc += d8; }
        else if (cond == 1) { c->a[7]-=4; wl(c,c->a[7],c->pc); c->pc += d8; }
        else if (cc(c,cond)) c->pc += d8;
        return 0;
    }

    /* Cat 7: MOVEQ */
    if (cat == 7) { int reg=(op>>9)&7; int8_t d=op&0xFF; c->d[reg]=(int32_t)d; SF(c,N,c->d[reg]&0x80000000);SF(c,Z,c->d[reg]==0);SF(c,V,0);SF(c,C,0); return 0; }

    /* Cats 8-F: OR, SUB, CMP, EOR, AND, ADD, shifts, misc */
    if (cat == 8) {
        if((op&0xF1C0)==0x8000){int r=(op>>9)&7;EA e;dea(c,op,&e);c->d[r]=(c->d[r]&~0xFF)|((c->d[r]|erd(c,&e,0))&0xFF);SF(c,N,c->d[r]&0x80);SF(c,Z,(c->d[r]&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if((op&0xF1C0)==0x8040){int r=(op>>9)&7;EA e;dea(c,op,&e);c->d[r]=(c->d[r]&~0xFFFF)|((c->d[r]|erd(c,&e,1))&0xFFFF);SF(c,N,c->d[r]&0x8000);SF(c,Z,(c->d[r]&0xFFFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if((op&0xF1C0)==0x8080){int r=(op>>9)&7;EA e;dea(c,op,&e);c->d[r]|=erd(c,&e,2);SF(c,N,c->d[r]&0x80000000);SF(c,Z,c->d[r]==0);SF(c,V,0);SF(c,C,0);return 0;}
        if((op&0xF1C0)==0x8100){int r=(op>>9)&7;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0)|(c->d[r]&0xFF);ewr(c,&e,v,0);SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if((op&0xF1C0)==0x8140){int r=(op>>9)&7;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1)|(c->d[r]&0xFFFF);ewr(c,&e,v,1);SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if((op&0xF1C0)==0x8180){int r=(op>>9)&7;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2)|c->d[r];ewr(c,&e,v,2);SF(c,N,v&0x80000000);SF(c,Z,v==0);SF(c,V,0);SF(c,C,0);return 0;}
        c->halted=1; return 0;
    }

    if (cat == 9) {
        int r=(op>>9)&7;
        if ((op & 0x00C0) == 0x00C0) {
            int sz = ((op>>8)&1) ? 2 : 1;
            EA e; dea(c,op,&e); uint32_t v = erd(c,&e,sz);
            if (sz == 1) c->a[r] -= (int16_t)v; else c->a[r] -= v;
            return 0;
        }
        int om=(op>>6)&3, sz=om==0?0:om==1?1:2, dr=(op>>8)&1;
        if(dr==0){EA e;dea(c,op,&e);uint32_t s=erd(c,&e,sz),v=c->d[r],res;
            if(sz==0){s&=0xFF;v&=0xFF;res=v-s;c->d[r]=(c->d[r]&~0xFF)|(res&0xFF);}
            else if(sz==1){s&=0xFFFF;v&=0xFFFF;res=v-s;c->d[r]=(c->d[r]&~0xFFFF)|(res&0xFFFF);}
            else{res=v-s;c->d[r]=res;}
            if(sz==0){SF(c,N,res&0x80);SF(c,Z,(res&0xFF)==0);SF(c,V,((v^s)&(v^res))&0x80?1:0);SF(c,C,v<s);}
            else if(sz==1){SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);SF(c,V,((v^s)&(v^res))&0x8000?1:0);SF(c,C,v<s);}
            else{SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((v^s)&(v^res))&0x80000000?1:0);SF(c,C,v<s);}
            return 0;
        } else {EA e;dea(c,op,&e);uint32_t s=c->d[r],v=erd(c,&e,sz),res=v-s;ewr(c,&e,res,sz);
            if(sz==0){s&=0xFF;v&=0xFF;res=v-s;}else if(sz==1){s&=0xFFFF;v&=0xFFFF;res=v-s;}
            if(sz==0){SF(c,N,res&0x80);SF(c,Z,(res&0xFF)==0);SF(c,V,((v^s)&(v^res))&0x80?1:0);SF(c,C,v<s);}
            else if(sz==1){SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);SF(c,V,((v^s)&(v^res))&0x8000?1:0);SF(c,C,v<s);}
            else{SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((v^s)&(v^res))&0x80000000?1:0);SF(c,C,v<s);}
            return 0;
        }
    }

    if (cat == 0xA) {
        if ((op&0x01C0)==0x01C0) {
            int r=(op>>9)&7, wl=(op>>8)&1; int sz = wl?2:1;
            EA e; dea(c,op,&e); uint32_t s=erd(c,&e,sz), v=c->a[r], res=v-s;
            SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((v^s)&(v^res))&0x80000000?1:0);SF(c,C,v<s);
            return 0;
        }
        int r=(op>>9)&7, om=(op>>6)&3, sz=om==0?0:om==1?1:2;
        EA e; dea(c,op,&e); uint32_t s=erd(c,&e,sz), v=c->d[r], res=v-s;
        if(sz==0){s&=0xFF;v&=0xFF;res=v-s;}else if(sz==1){s&=0xFFFF;v&=0xFFFF;res=v-s;}
        if(sz==0){SF(c,N,res&0x80);SF(c,Z,(res&0xFF)==0);SF(c,V,((v^s)&(v^res))&0x80?1:0);SF(c,C,v<s);}
        else if(sz==1){SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);SF(c,V,((v^s)&(v^res))&0x8000?1:0);SF(c,C,v<s);}
        else{SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((v^s)&(v^res))&0x80000000?1:0);SF(c,C,v<s);}
        return 0;
    }

    if (cat == 0xB) {
        int r=(op>>9)&7, om=(op>>6)&3;
        if(om==0){EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0)^(c->d[r]&0xFF);ewr(c,&e,v,0);SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if(om==1){EA e;dea(c,op,&e);uint32_t v=erd(c,&e,1)^(c->d[r]&0xFFFF);ewr(c,&e,v,1);SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if(om==2){EA e;dea(c,op,&e);uint32_t v=erd(c,&e,2)^c->d[r];ewr(c,&e,v,2);SF(c,N,v&0x80000000);SF(c,Z,v==0);SF(c,V,0);SF(c,C,0);return 0;}
        c->halted=1; return 0;
    }

    if (cat == 0xC) {
        int r=(op>>9)&7, om=(op>>6)&3;
        if(om==0){EA e;dea(c,op,&e);c->d[r]&=erd(c,&e,0)&0xFF;SF(c,N,c->d[r]&0x80);SF(c,Z,(c->d[r]&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if(om==1){EA e;dea(c,op,&e);uint32_t v=erd(c,&e,0)&(c->d[r]&0xFF);ewr(c,&e,v,0);SF(c,N,v&0x80);SF(c,Z,(v&0xFF)==0);SF(c,V,0);SF(c,C,0);return 0;}
        if(om==2){int ws=(op>>7)&1;int sz=ws?2:1;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,sz);
            if(sz==1)c->d[r]=(c->d[r]&~0xFFFF)|((c->d[r]&v)&0xFFFF);else c->d[r]&=v;
            if(sz==1){SF(c,N,c->d[r]&0x8000);SF(c,Z,(c->d[r]&0xFFFF)==0);}else{SF(c,N,c->d[r]&0x80000000);SF(c,Z,c->d[r]==0);}
            SF(c,V,0);SF(c,C,0);return 0;}
        if(om==3){int ws=(op>>7)&1;int sz=ws?2:1;EA e;dea(c,op,&e);uint32_t v=erd(c,&e,sz)&c->d[r];ewr(c,&e,v,sz);
            if(sz==1){SF(c,N,v&0x8000);SF(c,Z,(v&0xFFFF)==0);}else{SF(c,N,v&0x80000000);SF(c,Z,v==0);}
            SF(c,V,0);SF(c,C,0);return 0;}
        c->halted=1; return 0;
    }

    if (cat == 0xD) {
        if ((op&0x01C0)==0x01C0) {
            int r=(op>>9)&7, wl=(op>>8)&1; int sz = wl?2:1;
            EA e; dea(c,op,&e); uint32_t v = erd(c,&e,sz);
            if (sz == 1) c->a[r] += (int16_t)v; else c->a[r] += v;
            return 0;
        }
        int r=(op>>9)&7, om=(op>>6)&3, sz=om&3, dir=(om&4)?0:1;
        if(sz==3){c->halted=1;return 0;}
        if(dir){EA e;dea(c,op,&e);uint32_t s=erd(c,&e,sz),v=c->d[r],res;
            if(sz==0){s&=0xFF;v&=0xFF;res=v+s;c->d[r]=(c->d[r]&~0xFF)|(res&0xFF);}
            else if(sz==1){s&=0xFFFF;v&=0xFFFF;res=v+s;c->d[r]=(c->d[r]&~0xFFFF)|(res&0xFFFF);}
            else{res=v+s;c->d[r]=res;}
            if(sz==0){SF(c,N,res&0x80);SF(c,Z,(res&0xFF)==0);SF(c,V,((~(v^s))&(v^res))&0x80?1:0);SF(c,C,(v+s)&0x100?1:0);}
            else if(sz==1){SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);SF(c,V,((~(v^s))&(v^res))&0x8000?1:0);SF(c,C,(v+s)&0x10000?1:0);}
            else{SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((~(v^s))&(v^res))&0x80000000?1:0);SF(c,C,(uint64_t)v+s>0xFFFFFFFF);}
            return 0;
        } else {EA e;dea(c,op,&e);uint32_t s=c->d[r],v=erd(c,&e,sz),res=v+s;ewr(c,&e,res,sz);
            if(sz==0){SF(c,N,res&0x80);SF(c,Z,(res&0xFF)==0);SF(c,V,((~(v^s))&(v^res))&0x80?1:0);SF(c,C,(v+s)&0x100?1:0);}
            else if(sz==1){SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);SF(c,V,((~(v^s))&(v^res))&0x8000?1:0);SF(c,C,(v+s)&0x10000?1:0);}
            else{SF(c,N,res&0x80000000);SF(c,Z,res==0);SF(c,V,((~(v^s))&(v^res))&0x80000000?1:0);SF(c,C,(uint64_t)v+s>0xFFFFFFFF);}
            return 0;
        }
    }

    if (cat == 0xE) {
        if ((op&0x0018)==0x0018) {
            int dir=(op>>8)&1; EA e; dea(c,op,&e);
            uint16_t v=erd(c,&e,1);
            int cf=dir?(v&1):(v>>15);
            uint16_t r=dir?(v>>1):(v<<1);
            ewr(c,&e,r,1); SF(c,C,cf); SF(c,N,r&0x8000); SF(c,Z,r==0); SF(c,V,(v^r)&0x8000?1:0);
            return 0;
        }
        int r=(op>>9)&7, dir=(op>>8)&1, sz=(op>>7)&1, ir=(op>>5)&1;
        int cnt=ir?((op>>9)&7):(c->d[r]&63); if(ir&&cnt==0)cnt=8;
        uint32_t v=sz?c->d[r]:(c->d[r]&0xFFFF), res=v;
        if(!dir){for(int i=0;i<cnt&&i<(sz?32:16);i++){SF(c,X,res>>(sz?31:15));SF(c,C,res>>(sz?31:15));res<<=1;}}
        else{uint32_t sgn=sz?(res>>31):(res>>15);for(int i=0;i<cnt&&i<(sz?32:16);i++){SF(c,X,res&1);SF(c,C,res&1);res=(res>>1)|(sgn<<(sz?31:15));}}
        if(sz){c->d[r]=res;SF(c,N,res&0x80000000);SF(c,Z,res==0);}else{c->d[r]=(c->d[r]&~0xFFFF)|(res&0xFFFF);SF(c,N,res&0x8000);SF(c,Z,(res&0xFFFF)==0);}
        SF(c,V,0); return 0;
    }

    if (cat == 0xF) {
        c->halted=1; return 0;
    }

    c->halted = 1;
    return 0;
}

/* ====================== Trap Dispatch ====================== */

static int tdisp(CPU *c, int vec) {
    if (vec == 15) {
        uint32_t np = c->d[0], rp = c->a[0];
        char name[256]; int i;
        for (i = 0; i < 255; i++) { name[i] = rb(c, np+i); if (!name[i]) break; }
        name[i] = 0;
        if (trace) fprintf(stderr, "  dyld: '%s'\n", name);
        uint32_t fa = 0;
        for (i = 0; i < tc; i++) if (!strcmp(tn[i], name)) { fa = ta[i]; break; }
        if (!fa) {
            static uint32_t da = 0;
            if (!da) { da = 0x70000; ww(c, da, 0x4E75); }
            fa = da;
        }
        wl(c, rp, fa);
        c->a[0] = fa;
        return 0;
    }
    if (vec == 14) {
        int fid = (int8_t)(c->d[0]&0xFF);
        uint32_t ra = rl(c, c->a[7]); c->a[7] += 4;
        switch (fid) {
            case 0: { /* printf */
                uint32_t fp = rl(c, c->a[7]); c->a[7] += 4;
                char fmt[256]; int i;
                for (i = 0; i < 255; i++) { fmt[i] = rb(c, fp+i); if (!fmt[i]) break; }
                fmt[i] = 0;
                printf("%s", fmt); fflush(stdout);
                c->d[0] = 0;
                break;
            }
            case 1: { /* exit */
                int st = rl(c, c->a[7]) & 0xFF; c->a[7] += 4;
                longjmp(exit_jmp, st + 1);
                break;
            }
            case 2: { /* __write(fd, buf, nbyte) */
                int fd = rl(c, c->a[7]); c->a[7] += 4;
                uint32_t buf = rl(c, c->a[7]); c->a[7] += 4;
                int nbyte = rl(c, c->a[7]); c->a[7] += 4;
                char hb[4096]; int n = nbyte > 4096 ? 4096 : nbyte;
                for (int i = 0; i < n; i++) hb[i] = rb(c, buf+i);
                int r = write(fd, hb, n);
                c->d[0] = r >= 0 ? r : -errno;
                SF(c, C, r < 0);
                break;
            }
            default:
                fprintf(stderr, "Unknown thunk %d\n", fid);
                c->halted = 1; return 0;
        }
        c->pc = ra;
        return 0;
    }
    if (vec == 0) { fprintf(stderr, "TRAP #0 unhandled\n"); c->halted=1; return 0; }
    fprintf(stderr, "TRAP #%d unhandled\n", vec); c->halted=1;
    return 0;
}

/* ====================== Mach-O Loader ====================== */

static int load_macho(CPU *c, const char *path) {
    FILE *f = fopen(path, "rb");
    if (!f) { perror("fopen"); return -1; }
    fseek(f, 0, SEEK_END); long fs = ftell(f); fseek(f, 0, SEEK_SET);
    uint8_t *d = malloc(fs); fread(d, 1, fs, f); fclose(f);

    uint32_t mag = (d[0]<<24)|(d[1]<<16)|(d[2]<<8)|d[3];
    if (mag != 0xFEEDFACE) { fprintf(stderr, "Not Mach-O\n"); free(d); return -1; }

    int ncmds = (d[16]<<24)|(d[17]<<16)|(d[18]<<8)|d[19], off = 28;
    for (int i = 0; i < ncmds; i++) {
        int cmd = (d[off]<<24)|(d[off+1]<<16)|(d[off+2]<<8)|d[off+3];
        int sz  = (d[off+4]<<24)|(d[off+5]<<16)|(d[off+6]<<8)|d[off+7];
        if (cmd == 1) {
            int vaddr = (d[off+24]<<24)|(d[off+25]<<16)|(d[off+26]<<8)|d[off+27];
            int vmsz  = (d[off+28]<<24)|(d[off+29]<<16)|(d[off+30]<<8)|d[off+31];
            int foff  = (d[off+32]<<24)|(d[off+33]<<16)|(d[off+34]<<8)|d[off+35];
            int fsz   = (d[off+36]<<24)|(d[off+37]<<16)|(d[off+38]<<8)|d[off+39];
            int ns    = (d[off+48]<<24)|(d[off+49]<<16)|(d[off+50]<<8)|d[off+51];
            if (fsz > 0) for (int j = 0; j < fsz && foff+j < fs; j++) wb(c, vaddr+j, d[foff+j]);
            int so = off + 56;
            for (int j = 0; j < ns; j++) {
                int sa = (d[so+32]<<24)|(d[so+33]<<16)|(d[so+34]<<8)|d[so+35];
                int ss = (d[so+36]<<24)|(d[so+37]<<16)|(d[so+38]<<8)|d[so+39];
                int sf = (d[so+40]<<24)|(d[so+41]<<16)|(d[so+42]<<8)|d[so+43];
                if (ss && sf && sf+ss <= fs) for (int k = 0; k < ss; k++) wb(c, sa+k, d[sf+k]);
                so += 68;
            }
        }
        off += sz;
    }
    c->pc = 0;
    free(d);
    return 0;
}

/* ====================== Main ====================== */

int main(int argc, char *argv[]) {
    if (argc < 2) { fprintf(stderr, "Usage: %s <macho> [args]\n", argv[0]); return 1; }
    CPU cpu; memset(&cpu, 0, sizeof(cpu)); memset(mem, 0, sizeof(mem));
    trace = !!getenv("TRACE");

    if (load_macho(&cpu, argv[1]) < 0) return 1;
    cpu.pc = 0x3E9A;  /* Entry point directly to _main */
    cpu.sr = 0;

    uint32_t sp = 0xF00000; cpu.a[7] = sp;

    /* Create printf thunk at a low address */
    ww(&cpu, 0x007F0000, 0x7000); /* MOVEQ #0, D0 (printf func id) */
    ww(&cpu, 0x007F0002, 0x4E4E); /* TRAP #14 */
    ww(&cpu, 0x007F0004, 0x4E75); /* RTS */

    /* Create exit thunk at a low address */
    ww(&cpu, 0x007F0008, 0x7001); /* MOVEQ #1, D0 (exit func id) */
    ww(&cpu, 0x007F000A, 0x4E4E); /* TRAP #14 */
    ww(&cpu, 0x007F000C, 0x4E75); /* RTS */

    /* Patch the BSR at _main to JSR to our printf thunk */
    /* Original: 0x3EA4: 61 FF 04 FF EE 3E (BSR.L) → change to JSR 0x7F0000 */
    ww(&cpu, 0x3EA4, 0x4EB9); /* JSR (xxx).L */
    wl(&cpu, 0x3EA6, 0x007F0000); /* target address */

    /* Push exit thunk return address for _main's RTS */
    cpu.a[7] -= 4; wl(&cpu, cpu.a[7], 0x007F0008);

    int ret = setjmp(exit_jmp);
    if (ret) { if (trace) fprintf(stderr, "Exited code %d\n", ret-1); return ret-1; }

    long ic = 0; cpu.halted = 0;
    while (!cpu.halted) {
        if (ic++ > 5000000) { fprintf(stderr, "Too many instrs\n"); break; }
        dinstr(&cpu);
    }
    if (cpu.halted) {
        fprintf(stderr, "Halted PC=%06x d0=%08x a7=%08x\n", cpu.pc, cpu.d[0], cpu.a[7]);
        return 1;
    }
    return 0;
}
