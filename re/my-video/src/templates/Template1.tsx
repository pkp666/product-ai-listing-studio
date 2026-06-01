// 带货轮播视频模板：负责主视觉转盘和分镜动画。
/**
 * Template1.tsx - 剪映草稿还原
 *
 * Track 结构：
 * [Phase1] 0-2792000μs        圆盘居中旋转 0°→180°→0°
 * [Phase2] 2792000-5594000μs  圆盘从中心滑到左侧
 * [Phase3] 5594000-16222000μs 左侧圆盘旋转 + 右侧主图轮播 + 颜色文字
 *
 * 坐标系：transform.x/y 是归一化值，×(width/2 或 height/2) 得像素偏移（相对画面中心）
 */

import {
  AbsoluteFill,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Img,
  Audio,
  staticFile,
  Sequence,
} from 'remotion';

// ─── 工具 ──────────────────────────────────────────────────────
const f = (us: number) => us / (1000000 / 30); // 微秒 → 帧

// ─── 时间常量 ──────────────────────────────────────────────────
const T_P1_END    = f(2792000);   // 83.76  Phase1结束
const T_P3_START  = f(5594000);   // 167.82 Phase3开始
const T_SEG_DUR   = f(1328375);   // 39.85  每个颜色段时长
const T_FADE_DUR  = f(664187.5);  // 19.93  左侧淡出时长
const T_ANIM_DUR  = f(500000);    // 15.0   文字动画时长
export const TEMPLATE1_FRAMES = Math.ceil(f(16222000)); // 487

// ─── 素材配置（修改这里换图）──────────────────────────────────
const YUANPAN = 'yuanpan.png';  // 圆盘图（始终不变）
const IMGS = [
  'zhutu_20260501_020214_01.png',
  'zhutu_20260501_020215_02.png',
  'zhutu_20260501_020217_04.png',
];
const BGM = 'bgm.mp3';

// 8段右侧主图索引（对应 IMGS 数组）
const RIGHT_IMGS = [0, 1, 2, 0, 1, 2, 0, 1];
// 8段左侧淡出图索引（每段开始时消失的"前一张"）
const LEFT_IMGS  = [2, 0, 1, 2, 0, 1, 2, 0];

// ─── 颜色标签 ──────────────────────────────────────────────────
const LABELS = ['Red', 'Orange', 'Yellow', 'Green', 'Cyan', 'Blue', 'Purple', 'Pink'];
const LABEL_HEX: Record<string, string> = {
  Red: '#ff3333', Orange: '#ff8800', Yellow: '#ffcc00', Green: '#33cc33',
  Cyan: '#00cccc', Blue: '#3366ff', Purple: '#9933ff', Pink: '#ff66aa',
};

// ─── 轮盘旋转关键帧（track 29746246）──────────────────────────
// 分8步各45°，每步先停约744ms再线性过渡约637ms
const WHEEL_KF = [
  { t: f(0),         v: 0   }, { t: f(743890),   v: 0   },
  { t: f(1381510),   v: 45  }, { t: f(2125400),  v: 45  },
  { t: f(2763020),   v: 90  }, { t: f(3506910),  v: 90  },
  { t: f(4144530),   v: 135 }, { t: f(4888420),  v: 135 },
  { t: f(5526040),   v: 180 }, { t: f(6269930),  v: 180 },
  { t: f(6907550),   v: 225 }, { t: f(7651440),  v: 225 },
  { t: f(8289060),   v: 270 }, { t: f(9032950),  v: 270 },
  { t: f(9670570),   v: 315 }, { t: f(10414460), v: 315 },
  { t: f(10627000),  v: 360 },
];

function getWheelRot(localFrame: number): number {
  if (localFrame <= 0) return 0;
  if (localFrame >= WHEEL_KF[WHEEL_KF.length - 1].t) return 360;
  for (let i = 0; i < WHEEL_KF.length - 1; i++) {
    const a = WHEEL_KF[i], b = WHEEL_KF[i + 1];
    if (localFrame >= a.t && localFrame <= b.t) {
      return interpolate(localFrame, [a.t, b.t], [a.v, b.v]);
    }
  }
  return 0;
}

// ─── 背景 ──────────────────────────────────────────────────────
const BG = () => (
  <AbsoluteFill style={{
    background: 'linear-gradient(135deg, #0d0d1a 0%, #1a1a2e 50%, #0d1a2e 100%)',
  }} />
);

// ─── Phase1: 圆盘居中旋转（0→84帧）────────────────────────────
function Phase1() {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();
  const half = f(1396000);
  const rot = frame <= half
    ? interpolate(frame, [0, half], [0, 180])
    : interpolate(frame, [half, T_P1_END], [180, 0]);
  const size = Math.min(width, height) * 0.5;
  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute', left: '50%', top: '50%',
        width: size, height: size,
        marginLeft: -size / 2, marginTop: -size / 2,
        transform: `rotate(${rot}deg)`,
        borderRadius: 24, overflow: 'hidden',
        boxShadow: '0 0 60px rgba(255,255,255,0.15)',
      }}>
        <Img src={staticFile(YUANPAN)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
    </AbsoluteFill>
  );
}

// ─── Phase1静止：Phase2期间圆盘保持最终状态（rot=0°）──────────
function Phase1Still() {
  const { width, height } = useVideoConfig();
  const size = Math.min(width, height) * 0.5;
  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute', left: '50%', top: '50%',
        width: size, height: size,
        marginLeft: -size / 2, marginTop: -size / 2,
        borderRadius: 24, overflow: 'hidden',
        boxShadow: '0 0 40px rgba(255,255,255,0.1)',
      }}>
        <Img src={staticFile(YUANPAN)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
    </AbsoluteFill>
  );
}

// ─── Phase2: 圆盘从中心滑到左侧（84→168帧）────────────────────
function Phase2() {
  const frame = useCurrentFrame(); // 相对 Phase2 起点
  const { width, height } = useVideoConfig();
  const moveStart = f(1401000);
  const dur = f(2802000);
  const targetX = -0.9135416666666667 * (width / 2);
  const size = Math.min(width, height) * 0.5;
  const xOffset = frame < moveStart
    ? 0
    : interpolate(frame, [moveStart, dur], [0, targetX], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute', left: '50%', top: '50%',
        width: size, height: size,
        marginLeft: xOffset - size / 2,
        marginTop: -size / 2,
        borderRadius: 24, overflow: 'hidden',
        boxShadow: '0 0 40px rgba(255,255,255,0.1)',
      }}>
        <Img src={staticFile(YUANPAN)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>
    </AbsoluteFill>
  );
}

// ─── Phase3: 轮盘旋转 + 右侧主图轮播 + 颜色文字（168→487帧）──
function Phase3() {
  const frame = useCurrentFrame(); // 相对 Phase3 起点
  const { width, height } = useVideoConfig();

  const segIdx   = Math.min(Math.floor(frame / T_SEG_DUR), 7);
  const segFrame = frame - segIdx * T_SEG_DUR;

  const leftCX   = -0.9135416666666667 * (width / 2);
  const rightCX  =  0.43697916666666664 * (width / 2);
  const wheelSize = Math.min(width, height) * 0.5;

  const rot = getWheelRot(frame);

  // 右侧主图
  const rightImg = IMGS[RIGHT_IMGS[segIdx]];

  // 左侧淡出旧图
  const fadeAlpha = segFrame < T_FADE_DUR
    ? interpolate(segFrame, [0, T_FADE_DUR], [0.5, 0]) : 0;
  const fadeScale = segFrame < T_FADE_DUR
    ? interpolate(segFrame, [0, T_FADE_DUR], [0.5, 0.8]) : 0;
  const fadeImg = IMGS[LEFT_IMGS[segIdx]];

  // 文字动画
  const outStart = T_SEG_DUR - T_ANIM_DUR;
  let txtScale = 1, txtAlpha = 1;
  if (segFrame < T_ANIM_DUR) {
    txtScale = interpolate(segFrame, [0, T_ANIM_DUR], [0.5, 1]);
  }
  if (segFrame > outStart) {
    txtAlpha = interpolate(segFrame, [outStart, T_SEG_DUR], [1, 0]);
    txtScale = interpolate(segFrame, [outStart, T_SEG_DUR], [1, 0.8]);
  }

  const label = LABELS[segIdx];
  const color = LABEL_HEX[label];

  return (
    <AbsoluteFill>

      {/* 左侧轮盘旋转 */}
      <div style={{
        position: 'absolute', left: '50%', top: '50%',
        width: wheelSize, height: wheelSize,
        marginLeft: leftCX - wheelSize / 2,
        marginTop: -wheelSize / 2,
        transform: `rotate(${rot}deg)`,
        borderRadius: 24, overflow: 'hidden',
        boxShadow: '0 0 50px rgba(255,255,255,0.2)',
      }}>
        <Img src={staticFile(YUANPAN)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>

      {/* 小指示点（scale=0.05，y=0.4333）*/}
      {(() => {
        const dw = width * 0.05, dh = height * 0.05;
        const dy = 0.43333 * (height / 2);
        return (
          <div style={{
            position: 'absolute', left: '50%', top: '50%',
            width: dw, height: dh,
            marginLeft: leftCX - dw / 2,
            marginTop: dy - dh / 2,
            borderRadius: '50%', overflow: 'hidden',
            border: '2px solid rgba(255,255,255,0.4)',
          }}>
            <Img src={staticFile(YUANPAN)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          </div>
        );
      })()}

      {/* 左侧淡出旧图 */}
      {fadeAlpha > 0.001 && (
        <div style={{
          position: 'absolute', left: '50%', top: '50%',
          width: wheelSize * fadeScale / 0.5,
          height: wheelSize * fadeScale / 0.5,
          marginLeft: leftCX - (wheelSize * fadeScale / 0.5) / 2,
          marginTop: -(wheelSize * fadeScale / 0.5) / 2,
          opacity: fadeAlpha,
          borderRadius: 24, overflow: 'hidden',
        }}>
          <Img src={staticFile(fadeImg)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        </div>
      )}

      {/* 右侧主图（1024×1024，中心在 rightCX）*/}
      <div style={{
        position: 'absolute', left: '50%', top: '50%',
        width: 1024, height: 1024,
        marginLeft: rightCX - 512,
        marginTop: -512,
        borderRadius: 24, overflow: 'hidden',
        boxShadow: `0 0 60px ${color}44, 0 20px 80px rgba(0,0,0,0.5)`,
      }}>
        <Img src={staticFile(rightImg)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
      </div>

      {/* 颜色文字标签 */}
      <div style={{
        position: 'absolute', left: 0, right: 0,
        bottom: height * 0.06,
        display: 'flex', justifyContent: 'center', alignItems: 'center',
        opacity: txtAlpha,
        transform: `scale(${txtScale})`,
        transformOrigin: 'center bottom',
      }}>
        <div style={{
          color: '#ffffff',
          fontSize: 96,
          fontWeight: '900',
          fontFamily: '"Arial Black", Impact, sans-serif',
          letterSpacing: 8,
          padding: '12px 60px',
          borderRadius: 16,
          background: `${color}22`,
          border: `4px solid ${color}cc`,
          boxShadow: `0 0 40px ${color}66, inset 0 0 20px ${color}11`,
          textShadow: `-4px -4px 0 #000, 4px -4px 0 #000, -4px 4px 0 #000, 4px 4px 0 #000, 0 0 30px ${color}`,
        }}>
          {label}
        </div>
      </div>

    </AbsoluteFill>
  );
}

// ─── 主组件（导出）─────────────────────────────────────────────
export function Template1() {
  const p1End    = Math.round(T_P1_END);           // 84
  const p2Dur    = Math.round(f(2802000));          // 84
  const p3Start  = Math.round(T_P3_START);          // 168
  const p3Dur    = TEMPLATE1_FRAMES - p3Start;

  return (
    <AbsoluteFill>
      <BG />
      <Audio src={staticFile(BGM)} volume={1} />

      {/* Phase1: 圆盘旋转 */}
      <Sequence from={0} durationInFrames={p1End}>
        <Phase1 />
      </Sequence>

      {/* Phase2: 圆盘静止 + 滑向左侧 */}
      <Sequence from={p1End} durationInFrames={p2Dur}>
        <Phase1Still />
        <Phase2 />
      </Sequence>

      {/* Phase3: 轮盘 + 右图 + 文字 */}
      <Sequence from={p3Start} durationInFrames={p3Dur}>
        <Phase3 />
      </Sequence>
    </AbsoluteFill>
  );
}
/**
 * Template1.tsx - 带货轮播视频模板，负责主视觉转盘和分镜动画。