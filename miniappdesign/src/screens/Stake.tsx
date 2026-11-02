import { Avatar, HomeBar, Screen, StatusBar } from '../components/Phone'
import { Ico } from '../components/Icons'

const miniBlue = '0,34 20,40 40,26 60,38 80,28 100,36 120,20 140,32 160,24 180,30 200,26 210,14'
const miniAmber = '0,42 20,42 40,32 60,36 80,32 100,28 120,36 140,28 160,12 180,22 200,10 210,24'

const transactions = [
  { name: 'Elena Barova', date: 'Yesterday', delta: '+5.98%', amount: '+$987', tone: 'sand' as const },
  { name: 'Tifan Oliv', date: '11.10.2026', delta: '-5.98%', amount: '-$568', tone: 'sky' as const },
  { name: 'Barbara Lin', date: '12.10.2026', delta: '+2.23%', amount: '+$154', tone: 'clay' as const },
]

export function StakeHome() {
  return (
    <Screen className="st-home">
      <div className="st-bg" aria-hidden="true" />
      <StatusBar />
      <div className="st-home__body">
        <header className="st-home__header">
          <p>Hi Nixtio! Welcome to<br />Stake App</p>
          <div className="st-home__head-actions">
            <button className="st-bell" type="button" aria-label="通知">
              <Ico name="bell" size={16} />
              <i>6</i>
            </button>
            <span className="st-logo">N</span>
          </div>
        </header>

        <section className="st-balance">
          <div className="st-balance__top">
            <span className="st-delta">+0.60%</span>
            <strong>$12,356</strong>
          </div>
          <div className="st-spend-pill">
            <span>Daily Expenses</span>
            <b>$3, 103</b>
          </div>
        </section>

        <div className="st-actions">
          <button className="st-action" type="button">
            <span className="st-action__glyph">
              <Ico name="send" size={16} />
            </span>
            Send
          </button>
          <button className="st-swap" type="button" aria-label="兑换">
            <Ico name="swap" size={20} />
          </button>
          <button className="st-action" type="button">
            <span className="st-action__glyph">
              <Ico name="plus-circle" size={16} />
            </span>
            Request
          </button>
        </div>

        <div className="st-history-pill">Your History</div>

        <section className="st-history">
          <div className="st-history__top">
            <div className="st-coin-grid">
              <span className="st-coin">₿</span>
              <span className="st-coin">Ξ</span>
              <span className="st-coin st-coin--bnb">
                <i />
              </span>
              <span className="st-coin st-coin--tether">T</span>
            </div>
            <div className="st-mini">
              <span className="st-mini__label">Crypto Balance</span>
              <svg viewBox="0 0 210 56" preserveAspectRatio="none" className="st-mini__chart" aria-hidden="true">
                <polyline points={miniBlue} fill="none" stroke="#A9C4DA" strokeWidth="1.6" />
                <polyline points={miniAmber} fill="none" stroke="#E8A33D" strokeWidth="1.7" />
              </svg>
              <div className="st-mini__foot">
                <strong>$4,596</strong>
                <span className="st-delta st-delta--inline">+0.10%</span>
              </div>
            </div>
          </div>

          <div className="st-rows">
            {transactions.map((tx) => (
              <div className="st-row" key={tx.name}>
                <Avatar name={tx.name} size={38} tone={tx.tone} />
                <div className="st-row__who">
                  <strong>{tx.name}</strong>
                  <span>
                    {tx.date} <em className={tx.delta.startsWith('+') ? 'up' : 'down'}>{tx.delta}</em>
                  </span>
                </div>
                <b className={tx.amount.startsWith('+') ? 'up' : 'down'}>{tx.amount}</b>
              </div>
            ))}
          </div>
        </section>
      </div>
      <HomeBar />
    </Screen>
  )
}

const bars = [40, 62, 34, 76, 52, 88, 44, 70, 36, 60, 92, 48, 74, 40, 58, 84, 46, 66, 96, 52, 78, 42, 62, 90, 50, 72, 38, 58]
const lineBlue = '0,120 18,114 36,128 54,110 72,122 90,96 108,118 126,102 144,126 162,112 180,100 198,112 216,104 234,110 252,96 270,104'
const lineAmber = '0,132 18,126 36,134 54,118 72,126 90,114 108,126 126,110 144,132 162,116 180,108 198,96 216,86 234,72 252,58 270,62'

const coins = [
  { glyph: '₿', name: 'Bitcoin', price: '$3,623.75', change: '+4.23%', amount: '+$224', up: true },
  { glyph: 'T', name: 'Tether', price: '$1,223.75', change: '-5.98%', amount: '-$368', up: false },
  { glyph: 'Ξ', name: 'Ethereum', price: '$1,406.34', change: '+3.76%', amount: '+$658', up: true },
  { glyph: '✕', name: 'Ripple', price: '$1,406.34', change: '+3.76%', amount: '+$572', up: true },
]

export function StakeDetail() {
  return (
    <Screen className="st-detail">
      <div className="st-detail__bg" aria-hidden="true" />
      <StatusBar />
      <div className="st-detail__body">
        <header className="st-detail__header">
          <button className="st-round-btn" type="button" aria-label="返回">
            <Ico name="arrow-left" size={17} />
          </button>
          <span>Crypto Balance</span>
          <span className="st-logo st-logo--small">N</span>
        </header>

        <div className="st-detail__amount">
          <strong>$4,596</strong>
          <span className="st-delta st-delta--inline">+0.10%</span>
        </div>

        <div className="st-chart">
          <div className="st-chart__bars" aria-hidden="true">
            {bars.map((height, index) => (
              <i key={index} style={{ height: `${height}%` }} />
            ))}
          </div>
          <svg viewBox="0 0 270 170" preserveAspectRatio="none" className="st-chart__lines" aria-hidden="true">
            <polyline points={lineBlue} fill="none" stroke="#B3CADC" strokeWidth="1.6" />
            <polyline points={lineAmber} fill="none" stroke="#E9A43B" strokeWidth="1.8" />
            <line x1="234" y1="30" x2="234" y2="150" stroke="#151515" strokeWidth="1.1" />
            <circle cx="234" cy="34" r="3" fill="#151515" />
          </svg>
          <div className="st-chart__tag">$238,23</div>
          <div className="st-chart__axis">
            {[
              ['12', 'Mon'],
              ['13', 'Tue'],
              ['14', 'Wed'],
              ['15', 'Thu'],
              ['16', 'Fri'],
              ['17', 'Set'],
              ['18', 'Sun'],
            ].map(([day, week], index) => (
              <span key={day} className={index === 5 ? 'is-active' : ''}>
                <b>{day}</b>
                <i>{week}</i>
              </span>
            ))}
          </div>
        </div>

        <div className="st-week-pill">This Week</div>

        <section className="st-coin-list">
          {coins.map((coin) => (
            <div className="st-coin-row" key={coin.name}>
              <span className="st-coin st-coin--small">{coin.glyph}</span>
              <div className="st-coin-row__body">
                <strong>{coin.name}</strong>
                <span>
                  {coin.price} <em className={coin.up ? 'up' : 'down'}>{coin.change}</em>
                </span>
              </div>
              <b>{coin.amount}</b>
            </div>
          ))}
        </section>
      </div>
      <HomeBar />
    </Screen>
  )
}
