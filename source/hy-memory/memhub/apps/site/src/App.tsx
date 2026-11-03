/** Every claim on this page has to be traceable to docs/NARRATIVE.md.
 *
 * That file holds one column the page cannot show: the entry point that proves
 * each line. Copy edited here without checking it there is how a site starts
 * promising the six sources that are still fixture-only.
 */

const REFUSALS: ReadonlyArray<{ name: string; note: string }> = [
  { name: "不截屏，不读屏幕内容", note: "没有屏幕录制，也没有截图权限" },
  { name: "不用辅助功能接口", note: "不借系统辅助功能读别的窗口里的内容" },
  { name: "不做 OCR", note: "不从图像里认字" },
  { name: "不记键盘和鼠标", note: "没有输入监听" },
  { name: "不读剪贴板", note: "复制的东西不会进记忆" },
  { name: "不后台录音", note: "没有麦克风采集" },
];

function Hero() {
  return (
    <header className="band hero">
      <div className="page">
        <p className="eyebrow">Local-first memory for your AI tools</p>
        <h1>一份可以核对的记忆</h1>
        <p className="lead">
          你已经在各个 AI 里把偏好、判断和踩过的坑说过一遍了。MemHub
          把这些话汇到本机的一份记忆里，让别的 AI 按你的授权取用 ——
          而每一条记忆都能翻回它出自的那句原话。
        </p>
        <div className="hero-actions">
          <a className="btn btn-primary" href="#download">
            下载 macOS 版
          </a>
          <a className="btn btn-quiet" href="#how">
            先看它怎么工作
          </a>
        </div>
      </div>
    </header>
  );
}

function Evidence() {
  return (
    <section className="band" id="how">
      <div className="page">
        <p className="eyebrow">为什么可以核对</p>
        <h2>抽取可以出错，原话不会丢</h2>
        <div className="prose">
          <p>
            记忆系统真正的失败方式不是没记住，是记错了还理直气壮，而你无从查证。
            模型总结你的时候会走形，而走形之后，原来那句话通常就没了 ——
            剩下的只有一句听起来很像你、但你从没说过的话。
          </p>
          <p>
            所以 MemHub 分两步走：先把原话原样存下来，再从里面抽取记忆。
            抽取归抽取，原话归原话。模型抽错了，你改的是抽取结果，
            不是重新回忆一遍；抽取彻底失败了，那句话也还在。
          </p>
          <p>
            这也是每条记忆都带出处的原因。它不是一句让你选择相信的总结，
            是一条你随时可以翻回去对照的记录。
          </p>
        </div>
      </div>
    </section>
  );
}

function Refusals() {
  return (
    <section className="band" id="privacy">
      <div className="page">
        <p className="eyebrow">我们不做的事</p>
        <h2>它只读你已经写下来的对话</h2>
        <p className="lead">
          能读到多少，取决于用什么方式读。下面这六种方式我们一种都不用，
          而且不是承诺，是每次提交都要过的一道门禁。
        </p>
        <div className="refusals">
          {REFUSALS.map((item) => (
            <div className="refusal" key={item.name}>
              <div className="refusal-name">{item.name}</div>
              <p className="refusal-note">{item.note}</p>
            </div>
          ))}
        </div>
        <p className="gate">
          <code>scripts/verify_zero_collection.py</code>
          <span>扫源码、依赖和系统权限三层；不通过就进不了主干。</span>
        </p>
      </div>
    </section>
  );
}

export function App() {
  return (
    <main>
      <Hero />
      <Evidence />
      <Refusals />
    </main>
  );
}
