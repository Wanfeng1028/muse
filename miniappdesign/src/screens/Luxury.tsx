import { HomeBar, Screen, StatusBar } from '../components/Phone'
import { Ico, type IconName } from '../components/Icons'

const tips: { icon: IconName; title: string; desc: string }[] = [
  { icon: 'umbrella', title: '防潮防水', desc: '避免接触水渍、雨水，潮湿环境易导致发霉或变形' },
  { icon: 'sun', title: '避免暴晒', desc: '长时间阳光直射会使皮革褪色、老化' },
  { icon: 'droplet', title: '定期清洁', desc: '使用专业产品轻柔擦拭，去除污渍' },
  { icon: 'box', title: '妥善存放', desc: '不使用时请放入防尘袋，置于通风干燥处' },
  { icon: 'flask', title: '远离化学品', desc: '避免接触香水、化妆品等化学物品' },
  { icon: 'clock', title: '定期护理', desc: '定期送到专业机构护理，保持最佳状态' },
]

const guarantees: { icon: IconName; label: string }[] = [
  { icon: 'users', label: '专业团队' },
  { icon: 'shield', label: '专属护理' },
  { icon: 'leaf', label: '安全环保' },
  { icon: 'box', label: '品质保障' },
]

export function LuxuryPromo() {
  return (
    <Screen className="lx-promo">
      <StatusBar />
      <header className="lx-header">
        <button type="button" aria-label="返回">
          <Ico name="arrow-left" size={16} />
        </button>
        <span>宣传页面</span>
        <button type="button" className="lx-header__spacer" aria-hidden="true" tabIndex={-1} />
      </header>

      <section className="lx-hero">
        <div className="lx-hero__panel">
          <h1>
            奢侈品 <i>✦</i>
            <br />
            <span>养护</span> TIPS
          </h1>
          <p>精心养护·让美好历久弥新</p>
          <div className="lx-hero__line" aria-hidden="true" />
        </div>
        <img className="lx-hero__photo" src="./assets/luxury-bag.webp" alt="黑色菱格纹奢侈品包" />
        <div className="lx-hero__veil" aria-hidden="true" />
      </section>

      <div className="lx-tips-title">
        <span>日常养护小贴士</span>
        <i />
      </div>

      <div className="lx-grid">
        {tips.map((tip) => (
          <article className="lx-tip" key={tip.title}>
            <span className="lx-tip__icon">
              <Ico name={tip.icon} size={17} />
            </span>
            <h3>{tip.title}</h3>
            <p>{tip.desc}</p>
          </article>
        ))}
      </div>

      <section className="lx-guarantee">
        <img src="./assets/leather-care.webp" alt="皮革护理" />
        <div className="lx-guarantee__shade" aria-hidden="true" />
        <div className="lx-guarantee__content">
          <h2>
            让每一件珍贵
            <br />
            都值得被悉心对待
          </h2>
          <div className="lx-guarantee__row">
            {guarantees.map((item) => (
              <span key={item.label}>
                <Ico name={item.icon} size={13} />
                {item.label}
              </span>
            ))}
          </div>
        </div>
      </section>

      <footer className="lx-footer">
        <p>精心呵护·让每一件衣物历久如新</p>
        <span>感谢您选择蔓吗</span>
      </footer>
      <HomeBar />
    </Screen>
  )
}

const records = [
  { type: 'in', title: '存入', time: '2026-05-20 10:30:45', amount: '+ ¥1256.00', left: '余额 ¥1256.00' },
  { type: 'out', title: '消费', time: '2026-05-15 10:30:45', amount: '- ¥1500.00', left: '余额 ¥100.00' },
  { type: 'in', title: '存入', time: '2026-05-20 10:30:45', amount: '+ ¥1256.00', left: '余额 ¥1256.00' },
  { type: 'out', title: '消费', time: '2026-05-15 10:30:45', amount: '- ¥1500.00', left: '余额 ¥100.00' },
  { type: 'in', title: '存入', time: '2026-05-20 10:30:45', amount: '+ ¥1256.00', left: '余额 ¥1256.00' },
  { type: 'out', title: '消费', time: '2026-05-15 10:30:45', amount: '- ¥1500.00', left: '余额 ¥100.00' },
]

export function BalanceDetail() {
  return (
    <Screen className="lx-balance">
      <StatusBar />
      <header className="lx-balance__header">
        <button type="button" aria-label="返回">
          <Ico name="arrow-left" size={16} />
        </button>
        <span>余额详情</span>
        <div className="lx-balance__tools">
          <button type="button" aria-label="更多">
            <Ico name="more" size={15} />
          </button>
          <button type="button" aria-label="定位">
            <Ico name="target" size={15} />
          </button>
        </div>
      </header>

      <section className="lx-balance-card">
        <span>账户余额（人民币元）</span>
        <strong>¥ 1256.00</strong>
        <p>可用余额 ¥1256.00</p>
      </section>

      <div className="lx-ledger">
        <h2>交易明细</h2>
        {records.map((record, index) => (
          <article className="lx-record" key={index}>
            <span className={`lx-record__sign lx-record__sign--${record.type}`}>
              <Ico name={record.type === 'in' ? 'plus' : 'minus'} size={12} stroke={2.4} />
            </span>
            <div className="lx-record__body">
              <strong>{record.title}</strong>
              <span>{record.time}</span>
            </div>
            <div className="lx-record__right">
              <strong>{record.amount}</strong>
              <span>{record.left}</span>
            </div>
          </article>
        ))}
      </div>
      <HomeBar />
    </Screen>
  )
}
