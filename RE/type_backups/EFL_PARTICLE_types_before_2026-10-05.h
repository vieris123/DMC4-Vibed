struct __unaligned __declspec(align(2)) rEffectList::EFL_PARTICLE_COMMON
{
byte TransMode;
byte EntryType;
rEffectList::CULLING_FLAG CullingFlag; ///< DX9-verified: bit0 ON -> culling draw variant (initGeneratorParam remap); SE: 0x40 GENERATOR -> culling block init
rEffectList::PARTICLE_OPTION_FLAG ParticleOptionFlag; ///< DX9-verified: 0x80000 EDGE_ALPHA_OFF (PrimModel builders zero border alpha)
uint LightGroupFlag;
uint zOfs;
ushort FixOtDepth;
}
;

struct rEffectList::EFL_PARTICLE_DRAW_COMMON
{
rEffectList::EFL_PARTICLE_COMMON base;
ushort PrimMaterialFlags; ///< 0x14..0x17. NOTE: IDB previously had an SE-derived 'ScaleAddCoef' float @0x18 which does not exist in DX9 - it pushed everything +4 (verified: Keyframe*ParamOffset self-relative tests at 0x30/0x34, Intensity range multiplier read @0x1C, colors lea @0x48, AnimFlag @0x50 across all particle inits).
MtRangeF Intensity;
MtRangeF Scale;
MtRangeF ScaleAdd;
int KeyframeIntensityParamOffset;
int KeyframeScaleParamOffset;
int member_0x38;
int member_0x3c;
byte ColorFlag;
byte uknFlagOrBool; ///< SE PDB: bit0 = KeyframePatSpeedParamFlag, bits1-7 padding
ushort KeyframeColorParamOffset;
ushort KeyframePatNoParamOffset; ///< SE PDB name at the same offset (SE DRAW_COMMON layout matches DX9 0x40-0x4F)
ushort CullingParamOffset; ///<  | SE PDB marks 0x46 as padding ('PDrawCommon1646'); DX9 actively uses it - engine difference.
MtColor colors;
MtColor colors2;
}
;

struct rEffectList::EFL_PARTICLE_PRIM_COMMON
{
rEffectList::EFL_PARTICLE_DRAW_COMMON DrawBase;
ushort AnimFlag;
uchar SeqNoMin;
uchar SeqNoRange;
ushort PatNoMin;
ushort PatNoRange;
float PatSpeed;
float PatNoMax;
MtPoint PatCenter;
float TextureInvW;
float TextureInvH;
char BaseMapPath[64];
char NormalMapPath[64];
char MaskMapPath[64];
char AnimPath[64];
}
;

struct rEffectList::EFL_PARTICLE_BILLBOARD
{
rEffectList::EFL_PARTICLE_PRIM_COMMON member_0x0;
MtRangeF Angle;
MtRangeF AngleAdd;
MtRangeF AspectRatio;
MtRangeF AspectRatioAdd;
undefined1 KeyframeAngleParamOffset;
undefined member_0x191;
undefined member_0x192;
undefined member_0x193;
undefined member_0x194;
undefined member_0x195;
undefined member_0x196;
undefined member_0x197;
undefined member_0x198;
undefined member_0x199;
undefined member_0x19a;
undefined member_0x19b;
undefined member_0x19c;
undefined member_0x19d;
undefined member_0x19e;
undefined member_0x19f;
}
;

struct rEffectList::EFL_PARTICLE_POLYGON
{
rEffectList::EFL_PARTICLE_PRIM_COMMON member_0x0;
MtRangeF Rot[3];
MtRangeF RotAdd[3];
__int32 RotAxisType : 4;
__int32 RotOrder : 4;
__int32 DirAxisType : 4;
__int32 UknPolygonFields : 4;
__int32 PolygonFixType : 4;
__int32 PolygonBillBoardType : 4;
__int32 CullingRotAxisType : 4;
__int32 CullingRotOrder : 4;
uint KeyframeRotParamOffset;
uint uknKeyframeOffset;
undefined member_0x1ac;
undefined member_0x1ad;
undefined member_0x1ae;
undefined member_0x1af;
MtRangeF Width;
MtRangeF Height;
MtRangeF WidthAdd;
MtRangeF HeightAdd;
float DistortRate[4];
}
;

struct rEffectList::EFL_PARTICLE_POLYLINE
{
rEffectList::EFL_PARTICLE_PRIM_COMMON member_0x0;
__int32 LineType : 8;
__int32 LineOfsNum : 8;
__int32 ColorPlaceType : 4;
__int32 ColorPlaceInpType : 4;
__int32 ColorPlaceNo : 8;
undefined member_0x174;
undefined member_0x175;
undefined member_0x176;
undefined member_0x177;
MtColor PlaceColor[2];
MtRangeF HeadSize;
MtRangeF HeadSizeAdd;
MtRangeF PlaceSize;
MtRangeF PlaceSizeAdd;
undefined member_0x1a0;
undefined member_0x1a1;
undefined member_0x1a2;
undefined member_0x1a3;
uint KeyframeHeadSizeParamOffset;
uint KeyframePlaceSizeParamOffset;
undefined member_0x1ac;
undefined member_0x1ad;
undefined member_0x1ae;
undefined member_0x1af;
undefined member_0x1b0;
undefined member_0x1b1;
undefined member_0x1b2;
undefined member_0x1b3;
undefined member_0x1b4;
undefined member_0x1b5;
undefined member_0x1b6;
undefined member_0x1b7;
undefined member_0x1b8;
undefined member_0x1b9;
undefined member_0x1ba;
undefined member_0x1bb;
undefined member_0x1bc;
undefined member_0x1bd;
undefined member_0x1be;
undefined member_0x1bf;
undefined member_0x1c0;
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
undefined member_0x1d0;
undefined member_0x1d1;
undefined member_0x1d2;
undefined member_0x1d3;
undefined member_0x1d4;
undefined member_0x1d5;
undefined member_0x1d6;
undefined member_0x1d7;
undefined member_0x1d8;
undefined member_0x1d9;
undefined member_0x1da;
undefined member_0x1db;
undefined member_0x1dc;
undefined member_0x1dd;
undefined member_0x1de;
undefined member_0x1df;
}
;

struct rEffectList::EFL_PARTICLE_PRIM_MODEL
{
rEffectList::EFL_PARTICLE_PRIM_COMMON base;
unsigned int PrimFlags; ///< SE PDB nibbles: [0-3] PrimModelType (0 Ring,1 TexRing,2 Sphere,3 TexSphere,4 Grid,5 TexGrid), [4-7] PrimModelAxis, [8-11] RotOrder, [12-15] DirAxisType, [16-19] ColorPlaceType, [20-23] SE padding 'PPrimModel04172' (DX9 builders still extract it - consumer untraced), [24-27] ModelBillboardType (build_view_basis), [28-31] NormAttenuateFlag (Attenuate builders; bit 29 one-sided)
unsigned __int16 HoriColorPlaceNo; ///< colour-gradient split (calc_color_gradient)
unsigned __int16 Ukn; ///< SE PDB: RotResetFlag:4, ModelBillboardOrder:1, ModelBillboardLookAt:1, pad:2 @0x176; ProjectionType u8 @0x177. No DX9 reader confirmed yet.
MtColor PlaceColor1; ///< init reads dword @0x178
MtColor PlaceColor2;
unsigned __int16 RotDivNum; ///< N segments (builders read @0x180)
unsigned __int16 RotTexDivNum; ///< U repeat
unsigned __int16 RotDrawStart;
unsigned __int16 RotDrawEnd;
unsigned __int16 HoriDivNum; ///< M stacks/rows
unsigned __int16 HoriTexDivNum; ///< V repeat
unsigned __int16 HoriDrawStart;
unsigned __int16 HoriDrawEnd;
MtRangeF ModelScale[3]; ///< DX9-confirmed by initParticlePrimModel: ModelScale->mScaleVec, ModelScaleAdd->mScaleVecVel, Rot->mRot, RotAdd->mRotVel, Radius[0/1]->mShape.x/.y, Height[0/1]->mShape.z/.w, *Add->mShapeVel
MtRangeF ModelScaleAdd[3];
MtRangeF Rot[3];
MtRangeF RotAdd[3];
MtRangeF Radius[2];
MtRangeF RadiusAdd[2];
MtRangeF Height[2];
MtRangeF HeightAdd[2];
float NormAttenuateAngleStart; ///< _rimFade builders
float NormAttenuateAngleEnd; ///< _rimFade builders
MtEaseCurve NormAttenuateCurve; ///< SE PDB name/type; DX9 Attenuate builders feed it to MtEaseCurve::easeIn
int KeyframePlaceColorParamOffset; ///< SE has TexScrollParamOffset here and KeyframePlaceColorParamOffset @0x244 - DX9 has no tex-scroll slot (verified by init reads), so DX9 offsets sit 4 lower
int KeyframeRotParamOffset; ///< self-relative keyframe block -> mRot / mRotVel
int KeyframeModelScaleParamOffset; ///< self-relative keyframe block -> mScaleVec / mScaleVecVel
int KeyframeRadius0ParamOffset; ///< SE: KeyframeUpperRadiusParamOffset (u16 in SE; dword in DX9)
int KeyframeRadius1ParamOffset; ///< SE: KeyframeLowerRadiusParamOffset
int KeyframeHeight0ParamOffset; ///< SE: KeyframeUpperHeightParamOffset
int KeyframeHeight1ParamOffset; ///< SE: KeyframeLowerHeightParamOffset
}
;
