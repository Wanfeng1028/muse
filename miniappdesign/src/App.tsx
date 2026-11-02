import { useEffect, useState } from 'react'
import { Ico } from './components/Icons'
import { LivingOnboarding, LivingDashboard } from './screens/HomeLiving'
import { HealthChat, HealthDashboard } from './screens/HealthAI'
import { StakeHome, StakeDetail } from './screens/Stake'
import { InvestmentPage, MyCardsPage } from './screens/Investment'
import { LuxuryPromo, BalanceDetail } from './screens/Luxury'

type Collection = {
  id: string
  no: string
  title: string
  subtitle: string
  summary: string
  source: string
  note: string
  screens: { name: string; component: () => JSX.Element; caption: string }[]
}

const collections: Collection[] = [
  {
    id: 'living',
    no: '01',
    title: '智能家居',
    subtitle: 'Smart Home',
    summary: '冷调蓝色渐变上的设备总览，用骨架卡片与大留白替代高密度信息。',
    source: './assets/reference/note-1.webp',
    note: '01 / 5 · 智能家居 App：引导页 + 首页',
    screens: [
      { name: 'Onboarding', component: LivingOnboarding, caption: '引导页 · Experience Smarter Living Every Day' },
      { name: 'Dashboard', component: LivingDashboard, caption: '首页 · Favourites 与设备卡片' },
    ],
  },
  {
    id: 'health',
    no: '02',
    title: '医疗 AI',
    subtitle: 'Health Assistant',
    summary: '云层柔光背景与白卡，图表用单色高亮，功能入口以胶囊 chip 聚合。',
    source: './assets/reference/note-2.webp',
    note: '02 / 5 · 医疗 AI App：对话页 + 健康看板',
    screens: [
      { name: 'Assistant', component: HealthChat, caption: '对话页 · How Can I Help You?' },
      { name: 'Health Logs', component: HealthDashboard, caption: '看板 · 心率、血值与预约' },
    ],
  },
  {
    id: 'stake',
    no: '03',
    title: 'Stake 钱包',
    subtitle: 'Crypto Wallet',
    summary: '玻璃拟态承载数字资产，暖金与灰蓝两色只做趋势与强调。',
    source: './assets/reference/note-3.webp',
    note: '03 / 5 · Stake App：资产首页 + 币种详情',
    screens: [
      { name: 'Wallet', component: StakeHome, caption: '资产首页 · 余额与历史' },
      { name: 'Crypto Balance', component: StakeDetail, caption: '详情 · 周趋势与币种列表' },
    ],
  },
  {
    id: 'investment',
    no: '04',
    title: '银行卡管理',
    subtitle: 'Investment',
    summary: '纯白页面与黑色实体卡形成强对比，底部弹层延续同一套浅灰控件。',
    source: './assets/reference/note-4.webp',
    note: '04 / 5 · Investment App：资产页 + My Cards 弹层',
    screens: [
      { name: 'Investment', component: InvestmentPage, caption: '资产页 · Connected Card 与 Activity' },
      { name: 'My Cards', component: MyCardsPage, caption: '弹层 · 卡管理与限额' },
    ],
  },
  {
    id: 'luxury',
    no: '05',
    title: '奢侈品养护',
    subtitle: 'Care & Balance',
    summary: '中文宋体与金色细线构成东方克制感，深色余额卡只保留一块重色。',
    source: './assets/reference/note-5.webp',
    note: '05 / 5 · 养护宣传页 + 余额详情',
    screens: [
      { name: 'Care Story', component: LuxuryPromo, caption: '宣传页 · 奢侈品养护 TIPS' },
      { name: 'Balance', component: BalanceDetail, caption: '余额详情 · 交易明细' },
    ],
  },
]

const fallback = collections[0]

function readHash(): string {
  const id = window.location.hash.replace(/^#\//, '')
  return collections.some((item) => item.id === id) ? id : fallback.id
}

export default function App() {
  const [activeId, setActiveId] = useState<string>(readHash)
  const [referenceOpen, setReferenceOpen] = useState(false)
  const active = collections.find((item) => item.id === activeId) ?? fallback

  useEffect(() => {
    const onHashChange = () => setActiveId(readHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  useEffect(() => {
    if (!referenceOpen) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setReferenceOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [referenceOpen])

  const go = (id: string) => {
    setActiveId(id)
    window.history.replaceState(null, '', `#/${id}`)
    setReferenceOpen(false)
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand__mark">
            <Ico name="grid" size={16} />
          </span>
          <div>
            <strong>简约高级 UI</strong>
            <span>UI Recreation · 2026</span>
          </div>
        </div>

        <p className="sidebar__label">复刻目录 / 5 张原图</p>
        <nav className="nav" aria-label="页面导航">
          {collections.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav__item${item.id === activeId ? ' is-active' : ''}`}
              onClick={() => go(item.id)}
            >
              <span className="nav__no">{item.no}</span>
              <span className="nav__text">
                <strong>{item.title}</strong>
                <i>{item.subtitle}</i>
              </span>
              <Ico name="chevron-right" size={14} />
            </button>
          ))}
        </nav>

        <div className="sidebar__foot">
          <p>素材来源</p>
          <span>小红书 @芥末设计</span>
          <span>「✨简约高级 UI，克制耐看界面设计」</span>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="topbar__crumbs">
            <span>复刻目录</span>
            <i>/</i>
            <strong>{active.no} · {active.title}</strong>
          </div>
          <div className="topbar__actions">
            <span className="topbar__count">2 屏 / 图</span>
            <button type="button" className="ghost-btn" onClick={() => setReferenceOpen(true)}>
              <Ico name="search" size={14} />
              对照原图
            </button>
          </div>
        </header>

        <section className="intro">
          <p className="intro__eyebrow">{active.subtitle} · {active.no}</p>
          <h1>{active.title}</h1>
          <p className="intro__summary">{active.summary}</p>
        </section>

        <section className="stage" aria-label={`${active.title} 界面复刻`}>
          {active.screens.map((screen, index) => {
            const View = screen.component
            return (
              <figure className="device" key={screen.name}>
                <div className="device__frame">
                  <View />
                </div>
                <figcaption>
                  <span className="device__index">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{screen.name}</strong>
                    <span>{screen.caption}</span>
                  </div>
                </figcaption>
              </figure>
            )
          })}
        </section>

        <footer className="pagefoot">
          <span>克制留白 · 低饱和配色 · 轻量组件</span>
          <span>React + Vite 复刻，仅作设计学习</span>
        </footer>
      </main>

      {referenceOpen && (
        <div className="refmodal" role="dialog" aria-modal="true" aria-label="原图对照" onClick={() => setReferenceOpen(false)}>
          <div className="refmodal__panel" onClick={(event) => event.stopPropagation()}>
            <header>
              <div>
                <strong>{active.note}</strong>
                <span>原图仅作对照，界面为 React 重绘</span>
              </div>
              <button type="button" onClick={() => setReferenceOpen(false)} aria-label="关闭原图">
                <Ico name="close" size={17} />
              </button>
            </header>
            <div className="refmodal__image">
              <img src={active.source} alt={`${active.title} 小红书原图`} />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
