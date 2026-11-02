import { Avatar, HomeBar, Screen, StatusBar } from '../components/Phone'
import { GoogleG, Ico } from '../components/Icons'

export function LivingOnboarding() {
  return (
    <Screen className="sh-onboard">
      <div className="sh-onboard__glow" aria-hidden="true" />
      <StatusBar />
      <div className="sh-onboard__body">
        <div className="sh-logo">
          <GoogleG size={34} />
        </div>
        <svg className="sh-lines" viewBox="0 0 220 76" fill="none" aria-hidden="true">
          <path d="M110 0v26M110 26c-22 0-34 15-34 26v24M110 26c22 0 34 15 34 26v24" stroke="rgba(33,84,190,.28)" strokeWidth="1.2" />
        </svg>

        <div className="sh-card">
          <div className="sh-card__head">
            <Ico name="arrow-left" size={17} />
            <span>Smart Home Summary</span>
            <div className="sh-card__head-tools">
              <Ico name="sparkles" size={16} />
              <Ico name="more" size={16} />
            </div>
          </div>
          <div className="sh-skeleton">
            <span style={{ width: '76%' }} />
            <span style={{ width: '56%' }} />
            <span style={{ width: '82%' }} />
            <span style={{ width: '44%' }} />
          </div>
          <div className="sh-progress">
            <span style={{ width: '44%' }} />
          </div>
          <div className="sh-skeleton sh-skeleton--short">
            <span style={{ width: '38%' }} />
            <span style={{ width: '52%' }} />
          </div>
          <div className="sh-better">
            <strong>Better Insight</strong>
            <div className="sh-skeleton sh-skeleton--inside">
              <span style={{ width: '70%' }} />
              <span style={{ width: '46%' }} />
            </div>
          </div>
        </div>

        <div className="sh-chip sh-chip--left">
          <span className="sh-chip__dot sh-chip__dot--blue">
            <Ico name="bulb" size={12} />
          </span>
          Auto Lights
        </div>
        <div className="sh-chip sh-chip--right">
          <span className="sh-chip__dot sh-chip__dot--violet">
            <Ico name="mic" size={12} />
          </span>
          Voice Control
        </div>

        <div className="sh-smart-pill">
          <Ico name="home" size={13} />
          Smart Control
        </div>

        <h1 className="sh-title">
          Experience Smarter
          <br />
          Living Every Day
        </h1>
        <p className="sh-copy">
          Control devices, automate routines, and enjoy seamless comfort tailored to your lifestyle.
        </p>
        <button className="sh-cta" type="button">
          Get Started
        </button>
      </div>
      <HomeBar />
    </Screen>
  )
}

const tabs = [
  { icon: 'home' as const, active: true },
  { icon: 'doc' as const },
  { icon: 'sparkles' as const },
  { icon: 'refresh' as const },
  { icon: 'settings' as const },
]

export function LivingDashboard() {
  return (
    <Screen className="sh-home">
      <StatusBar />
      <div className="sh-home__body">
        <header className="sh-home__header">
          <Avatar name="James Carter" size={42} tone="clay" />
          <div className="sh-home__who">
            <strong>James Carter</strong>
            <span>
              <Ico name="target" size={11} /> New York City
            </span>
          </div>
          <button className="sh-circle-btn" type="button" aria-label="Notifications">
            <Ico name="bell" size={17} />
          </button>
        </header>

        <div className="sh-section-head">
          <h2>Favourites</h2>
          <button type="button">See all</button>
        </div>

        <section className="sh-hero">
          <div className="sh-hero__stats">
            <div>
              <div className="sh-stat__value">98%</div>
              <div className="sh-stat__label">
                <Ico name="battery" size={14} /> battery
              </div>
            </div>
            <div>
              <div className="sh-stat__value">On</div>
              <div className="sh-stat__label">
                <Ico name="bulb" size={14} /> light
              </div>
            </div>
          </div>
          <img className="sh-hero__photo" src="./assets/lamp.webp" alt="暖光吊灯" />
          <div className="sh-hero__photo-fade" aria-hidden="true" />
          <div className="sh-hero__control">
            <button type="button" aria-label="锁定">
              <Ico name="lock" size={14} />
            </button>
            <div className="sh-hero__step">
              <span>›</span>
              <span>›</span>
              <span>›</span>
            </div>
            <button type="button" aria-label="锁定">
              <Ico name="lock" size={14} />
            </button>
          </div>
        </section>

        <div className="sh-tile-grid">
          <section className="sh-tile">
            <div className="sh-tile__top">
              <span className="sh-tile__glyph">
                <Ico name="mic" size={16} />
              </span>
              <span className="sh-power">
                <Ico name="power" size={11} />
                <i />
              </span>
            </div>
            <div>
              <h3>Assistant</h3>
              <div className="sh-tile__meta">
                <Ico name="battery" size={12} /> 80%
              </div>
            </div>
          </section>
          <section className="sh-tile">
            <div className="sh-tile__top">
              <span className="sh-tile__glyph">
                <Ico name="wifi" size={16} />
              </span>
              <span className="sh-power">
                <Ico name="power" size={11} />
                <i />
              </span>
            </div>
            <div>
              <h3>Hus Bridge</h3>
              <div className="sh-tile__meta">
                <Ico name="battery" size={12} /> 76%
              </div>
            </div>
          </section>
        </div>

        <div className="sh-ghost-row">
          <button type="button">Reorder</button>
          <button type="button">Edit</button>
        </div>
      </div>

      <nav className="sh-tabbar" aria-label="底部导航">
        {tabs.map((tab, index) => (
          <button key={index} type="button" className={tab.active ? 'is-active' : ''} aria-label={tab.icon}>
            <Ico name={tab.icon} size={18} />
          </button>
        ))}
      </nav>
      <HomeBar />
    </Screen>
  )
}
