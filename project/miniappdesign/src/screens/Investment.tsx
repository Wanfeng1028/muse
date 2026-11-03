import { HomeBar, Screen, StatusBar } from '../components/Phone'
import { Ico } from '../components/Icons'

function Mastercard() {
  return (
    <span className="iv-mc" aria-hidden="true">
      <i />
      <i />
    </span>
  )
}

function DebitCard({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`iv-card${compact ? ' iv-card--compact' : ''}`}>
      <div className="iv-card__texture" aria-hidden="true" />
      <div className="iv-card__number">8763 2736 9873 0329</div>
      <div className="iv-card__meta">
        <div>
          <span>Card Holder Name</span>
          <strong>HILLERY NEVELIN</strong>
        </div>
        <div>
          <span>Expired Date</span>
          <strong>10/28</strong>
        </div>
        <Mastercard />
      </div>
    </div>
  )
}

const tabs = [
  { icon: 'home' as const, label: 'Home' },
  { icon: 'refresh' as const, label: 'Payments' },
  { icon: 'wallet' as const, label: 'Wallets', active: true },
  { icon: 'globe' as const, label: 'Loans' },
  { icon: 'settings' as const, label: 'Settings' },
]

export function InvestmentPage() {
  return (
    <Screen className="iv-page">
      <StatusBar island />
      <div className="iv-body">
        <header className="iv-header">
          <button className="iv-round" type="button" aria-label="返回">
            <Ico name="arrow-left" size={17} />
          </button>
          <span>Investment</span>
          <button className="iv-round" type="button" aria-label="帮助">
            <Ico name="help" size={17} />
          </button>
        </header>

        <div className="iv-amount">
          <strong>$1,658.46</strong>
          <button className="iv-account" type="button">
            2818 1233 9919 <Ico name="copy" size={12} />
          </button>
        </div>

        <div className="iv-actions">
          {[
            { icon: 'plus' as const, label: 'Add Balance' },
            { icon: 'arrow-up' as const, label: 'Move Balance' },
            { icon: 'arrow-right' as const, label: 'Pay & Transfer' },
          ].map((action) => (
            <button key={action.label} type="button" className="iv-action">
              <span>
                <Ico name={action.icon} size={19} />
              </span>
              {action.label}
            </button>
          ))}
        </div>

        <h2 className="iv-label">Connected Card</h2>
        <DebitCard />

        <div className="iv-section-head">
          <h2>Activity</h2>
          <button type="button">View All</button>
        </div>

        <div className="iv-activity">
          <span className="iv-apple">
            <Ico name="apple" size={19} />
          </span>
          <div>
            <strong>Apple iClouds</strong>
            <span>5 mins ago</span>
          </div>
          <div className="iv-activity__amount">
            <strong>-$12,923.00</strong>
            <span>Transfer</span>
          </div>
        </div>
      </div>

      <nav className="iv-tabbar" aria-label="底部导航">
        {tabs.map((tab) => (
          <button key={tab.label} type="button" className={tab.active ? 'is-active' : ''}>
            <Ico name={tab.icon} size={18} />
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
      <HomeBar />
    </Screen>
  )
}

export function MyCardsPage() {
  return (
    <Screen className="iv-sheet-page">
      <div className="iv-backdrop">
        <StatusBar island />
        <header className="iv-header iv-header--muted">
          <span className="iv-round">
            <Ico name="arrow-left" size={17} />
          </span>
          <span>Investment</span>
          <span className="iv-round">
            <Ico name="help" size={17} />
          </span>
        </header>
      </div>
      <div className="iv-scrim" aria-hidden="true" />
      <section className="iv-sheet">
        <div className="iv-sheet__handle" aria-hidden="true" />
        <header className="iv-sheet__head">
          <h1>My Cards</h1>
          <button className="iv-close" type="button" aria-label="关闭">
            <Ico name="close" size={15} />
          </button>
        </header>

        <div className="iv-sheet__card">
          <DebitCard compact />
        </div>

        <div className="iv-sheet__actions">
          {[
            { icon: 'lock' as const, label: 'Lock Card' },
            { icon: 'refresh' as const, label: 'History' },
            { icon: 'settings' as const, label: 'Settings' },
          ].map((action) => (
            <button key={action.label} type="button">
              <span>
                <Ico name={action.icon} size={17} />
              </span>
              {action.label}
            </button>
          ))}
        </div>

        <div className="iv-settings">
          {[
            { icon: 'bulb' as const, title: 'Card Information', sub: 'Your card information' },
            { icon: 'grid' as const, title: 'Change Card Pin', sub: 'For payments and withdrawals' },
          ].map((row) => (
            <button key={row.title} type="button" className="iv-setting-row">
              <span className="iv-setting-row__icon">
                <Ico name={row.icon} size={16} />
              </span>
              <span className="iv-setting-row__body">
                <strong>{row.title}</strong>
                <i>{row.sub}</i>
              </span>
              <Ico name="chevron-right" size={16} />
            </button>
          ))}

          <div className="iv-setting-row iv-setting-row--static">
            <span className="iv-setting-row__icon">
              <Ico name="globe" size={16} />
            </span>
            <span className="iv-setting-row__body">
              <strong>Limit Online</strong>
              <i>$1000.000</i>
            </span>
            <span className="iv-toggle is-on" aria-label="Limit Online 已开启">
              <i />
            </span>
          </div>

          <div className="iv-setting-row iv-setting-row--static">
            <span className="iv-setting-row__icon">
              <Ico name="arrow-up" size={16} />
            </span>
            <span className="iv-setting-row__body">
              <strong>Withdrawal Limit</strong>
              <i>$100.00</i>
              <span className="iv-slider">
                <b />
              </span>
            </span>
            <span className="iv-toggle is-on" aria-label="Withdrawal Limit 已开启">
              <i />
            </span>
          </div>
        </div>
      </section>
      <HomeBar />
    </Screen>
  )
}
