struct rEffectList::EFL_GENERATOR
{
int GroupFlag;
int MaterialFlag;
undefined member_0x8;
undefined member_0x9;
undefined member_0xa;
byte member_0xb;
undefined member_0xc;
undefined member_0xd;
undefined member_0xe;
undefined member_0xf;
uint member_0x10;
undefined member_0x14;
undefined member_0x15;
undefined member_0x16;
undefined member_0x17;
undefined member_0x18;
undefined member_0x19;
undefined member_0x1a;
undefined member_0x1b;
undefined member_0x1c;
undefined member_0x1d;
undefined member_0x1e;
undefined member_0x1f;
undefined member_0x20;
undefined member_0x21;
undefined member_0x22;
undefined member_0x23;
undefined member_0x24;
undefined member_0x25;
undefined member_0x26;
undefined member_0x27;
undefined member_0x28;
undefined member_0x29;
undefined member_0x2a;
undefined member_0x2b;
undefined member_0x2c;
undefined member_0x2d;
undefined member_0x2e;
undefined member_0x2f;
MtFloat3 Pos;
int ParentNo;
MtVector4 Quat;
MtFloat3 member_0x50;
int someJointIdx;
MtVector4 member_0x60;
__int32 Order : 4;
__int32 AxisType : 4;
__int32 RelationType : 4;
undefined member_0x74;
undefined member_0x75;
MtRangeU16 WaitFrame;
MtRangeF Scale[3];
MtRangeF Range[3];
MtRangeU16 SetNum;
MtRangeU16 LoopNum;
MtRangeU16 SetFrame;
ushort SetInterval;
ushort LoopInterval;
float SetFrameDist;
MtRangeF member_0xc0; ///< {base,range} read by initGeneratorParam (addss +0xC0 / mulss +0xC4) -> Gen.mParticleScaleBase. Was IntervalFrameDist float + MtRangeF@0xC4 (4-byte overlay error).
unsigned __int8 RangeType; ///< spawn-range shape selector: switch in sub_999640 (byte @0xC8). Moved from 0xCC (2026-10-05)
unsigned __int8 RangeDirType; ///< read as byte by uEffectVFR::Funcx90. Moved from 0xCD
unsigned __int8 RangeOptionFlags; ///< initGeneratorParam reads word @0xCA. Moved from 0xCE
unsigned __int8 uknRangeFlag; ///< byte cmp in initGeneratorParam / uknGenBehaviorFunc2. Moved from 0xCF
unsigned __int8 RangeStripType; ///< dword-tested @0xCC by sub_9774B0/sub_99A8A0. Moved from 0xD0
unsigned __int8 RangeStripFlag; ///< byte read by sub_99B270. Moved from 0xD1
__int16 RangeStripPartsNo; ///< word read by sub_99A8A0/sub_99AFD0/sub_99B270. Moved from 0xD2
char RangeStripPath[64]; ///< inline .efs path; createGeneratorResources: cmp byte [edi+0D0h] / lea -> rEffectStrip -> ResourceInfo.mpRangeStrip. Moved from 0xD4
MtRangeF UknRangeThing[4]; ///< [0] = {base@0x110, range@0x114} (initParticleMoveNone, movevel_transform addss/mulss). Moved from 0x114
unsigned int RangeDivideNum; ///< dword; modulus divisor in sub_999640 (param % (n+1)). Moved from 0x134
float member_0x134; ///< (was member_0x138 float; shifted with the block) - no reader found
unsigned int member_0x138; ///< no reader found; padding/unknown before mVibReqType
rEffectList::VIB_REQ_TYPE mVibReqType; ///<  | DX9-verified: setRequest switch 0 NONE / 1 DEFAULT (req_simple) / 2 VIEWPORT_POS (req_at_pos) / 3 VIEWPORT_PARENT (req_with_parent)
unsigned __int8 member_0x13d;
unsigned __int8 mVibReqArg0;
unsigned __int8 mVibReqArg1;
char ExtVibrationPath[64]; ///< inline .vib path -> rVibration -> ResourceInfo.mpExtVibration (createGeneratorResources; fail Status|=0x200). SE stores a u16 offset instead.
char SoundRequestPath[64]; ///< inline .srq path -> rSoundRequest -> ResourceInfo.mpSoundRequest (createGeneratorResources; fail Status|=0x400). SE stores a u16 offset instead.
unsigned __int16 VibReqNo; ///< vibration request no (u16), arg1 to sVibrator::req_* in Generator::setRequest. Mirrors SeReqNo@0x1C8.
rEffectList::VIB_OPTION_FLAG VibOptionFlag; ///< vibration option flags (u16). bit0 = stop vib when generator finishes (Generator::finish_requests). Mirrors SeOptionFlag@0x1CA (bit0 tested as dword&0x10000). Was mis-named ExtVibrationPathOffset. | DX9-verified: bit0 SYNCHRO_STOP (finish_requests stops the vib)
unsigned int VibPriority;
unsigned __int32 SeReqNo : 16;
unsigned __int32 SeOptionFlag : 16;
__int32 member_0x1cc; ///< int self-relative byte offset to an embedded sub-block (0=absent); sibling of Keyframe*ParamOffset @0x1D0+. Read as DWORD by Generator::updateWorldMatrix @0x96BE38 when pGen->mStatus&0x10. Was SE-pasted 'SoundPathOffset' int16 + member_0x1ce - no DX9 reader supports that split.
int KeyframeScaleParamOffset;
int KeyframeSetNumParamOffset;
int KeyframeRangeParamOffset;
int KeyframeOfsParamOffset;
int member_0x1e0;
}
