struct __cppobj uEffectVFR : uCoord
{
uint mMode;
vadefs_h::uintptr_t mpRandom;
vadefs_h::uintptr_t mRandCtr;
vadefs_h::uintptr_t mpRandCtr;
float mBaseFps;
float mDeltaTimeRate;
float mDeltaTimeCoef;
float mTimeInterpolationRate;
float mTimeRestorationRate;
float mTimer;
unsigned int mFrameStep;
byte mAxisType;
unsigned __int8 mStateFlags; ///< state flag byte. 0x01 (dword-view 0x100) = generators built (createGenerator sets; move gate keeps alive). 0x04 (dword-view 0x400) = fractional time remainder this frame (set in move) -> renderGenerators selects the *_interp (sub-frame interpolated) render leaves. Accessed as dword ops on +0x10C by the compiler.
unsigned __int16 stepCount; ///< u16 (word accesses in move/moveEffectArray/doClear); was mis-typed int
unsigned __int8 member_0x110;
unsigned __int8 member_0x111; ///< byte read by checkEnd
unsigned __int16 loopLimit; ///< u16 (movzx word in move); was mis-typed int overlapping 0x114
unsigned __int16 member_0x114; ///< u16 added to stepCount in move; read/written in moveUnitGenerator
word mLifeFrame;
word mWaitFrame;
word mKillNo;
undefined member_0x11c;
undefined member_0x11d;
undefined member_0x11e;
undefined member_0x11f;
MtMatrix mWmatBase;
MtVector3 mOfs;
MtVector3 mDir;
MtVector3 mParticle3DScale;
rEffectList *mpEffectList;
undefined4 mSetNo;
uint mGroupFlag;
void *mpParamBlock;
uEffectVFR *mpParent;
undefined member_0x1a4;
undefined member_0x1a5;
undefined member_0x1a6;
undefined member_0x1a7;
undefined member_0x1a8;
undefined member_0x1a9;
word mChildLoopFrame;
word mChildLifeFrame;
word mChildWaitFrame;
word mGeneratorNum;
word mGeneratorMoveNum;
word mChildUnitGeneratorNum;
word member_0x1b6; ///< RESERVED/dead in DX9: only writer in effect cluster is ctor (=0); getEfxFlag reads it as a buffer-size addend but it is always 0. Do not rename to an active field without a confirmed non-zero writer.
int mGeneratorBuffSize;
uEffectVFR::Generator *EffectArr;
undefined mpMoveParticleArr; ///< Pointer into the EffectArr arena tail (move/extended particle records). Written only by setFlags loader (=EffectArr+EffectListNum+round16(544*survivors)) and zeroed by ctor/teardown; moveEffectArray derefs it and zeroes [+0]/[+4] which align with Generator.mpMoveTopParticle/mpMoveBotParticle. Target class unconfirmed - role name only.
undefined member_0x1c1;
undefined member_0x1c2;
undefined member_0x1c3;
undefined member_0x1c4;
undefined member_0x1c5;
undefined member_0x1c6;
undefined member_0x1c7;
undefined member_0x1c8;
undefined member_0x1c9;
undefined member_0x1ca;
undefined member_0x1cb;
undefined member_0x1cc;
undefined member_0x1cd;
undefined member_0x1ce;
undefined member_0x1cf;
};
