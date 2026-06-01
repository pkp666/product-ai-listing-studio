// Remotion 入口：注册视频组件并挂载模板。
import { Composition, registerRoot } from 'remotion';
import { Template1, TEMPLATE1_FRAMES } from './templates/Template1';

export const RemotionRoot = () => (
  <>
    <Composition
      id="MyVideo"
      component={Template1}
      durationInFrames={TEMPLATE1_FRAMES}
      fps={30}
      width={1920}
      height={1080}
    />
    {/* 之后新增模板在这里继续添加，例如：
    <Composition
      id="Template2"
      component={Template2}
      durationInFrames={TEMPLATE2_FRAMES}
      fps={30}
      width={1920}
      height={1080}
    />
    */}
  </>
);

registerRoot(RemotionRoot);
// Remotion 入口：注册视频 composition 并挂载模板组件。