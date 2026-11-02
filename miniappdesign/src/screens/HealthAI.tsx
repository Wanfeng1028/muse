import { Avatar, HomeBar, Screen, StatusBar } from '../components/Phone'
import { Ico } from '../components/Icons'

const promptChips = [
  { icon: 'user' as const, label: 'Check Symptoms', tone: 'blue' },
  { icon: 'users' as const, label: 'Check Available Doctor', tone: 'blue' },
  { icon: 'list' as const, label: 'Today my Report', tone: 'red' },
  { icon: 'chat' as const, label: 'Chat With Ai', tone: 'green' },
  { icon: 'calendar' as const, label: 'Your Upcoming Appointment', tone: 'amber' },
]

export function HealthChat() {
  return (
    <Screen className="hl-chat">
      <div className="hl-chat__sky" aria-hidden="true" />
      <StatusBar />
      <div className="hl-chat__body">
        <div className="hl-orb" aria-hidden="true">
          <span />
        </div>
        <h1 className="hl-chat__title">
          Hi ALex
          <br />
          How Can I Help You?
        </h1>
        <p className="hl-chat__sub">Your smart Your smart Your smart</p>

        <div className="hl-chips">
          {promptChips.map((chip) => (
            <button key={chip.label} type="button" className={`hl-chip hl-chip--${chip.tone}`}>
              <Ico name={chip.icon} size={15} />
              {chip.label}
            </button>
          ))}
        </div>
      </div>

      <div className="hl-composer">
        <div className="hl-input">
          <span>Write your message...</span>
          <Ico name="mic" size={17} />
        </div>
        <button className="hl-send" type="button" aria-label="发送">
          <Ico name="arrow-up" size={18} />
        </button>
      </div>
      <HomeBar />
    </Screen>
  )
}

const bloodDots = (() => {
  const dots: { x: number; y: number; r: number; o: number }[] = []
  for (let row = 0; row < 8; row += 1) {
    for (let col = 0; col < 7; col += 1) {
      const drift = (row % 3) * 1.6
      dots.push({
        x: 8 + col * 15,
        y: 7 + row * 10 + drift,
        r: row < 5 ? 1.2 : 2.4,
        o: row < 5 ? 0.55 : 0.95,
      })
    }
  }
  return dots
})()

const navItems = [
  { icon: 'home' as const },
  { icon: 'heart' as const },
  { icon: 'user' as const },
  { icon: 'grid' as const },
  { icon: 'sparkles' as const, dark: true },
]

export function HealthDashboard() {
  return (
    <Screen className="hl-dash">
      <div className="hl-dash__sky" aria-hidden="true" />
      <StatusBar />
      <div className="hl-dash__body">
        <header className="hl-dash__header">
          <div>
            <span className="hl-hello">Welcome Back Sofia👋</span>
            <h1>Track health with AI</h1>
          </div>
          <div className="hl-dash__actions">
            <button className="hl-icon-btn" type="button" aria-label="消息">
              <Ico name="bell" size={16} />
              <i />
            </button>
            <div className="hl-avatar-ring">
              <Avatar name="Sofia" size={40} tone="rose" />
            </div>
          </div>
        </header>

        <div className="hl-search-row">
          <div className="hl-search">
            <Ico name="search" size={17} />
            <span>Search Doctors...</span>
          </div>
          <button className="hl-filter" type="button" aria-label="筛选">
            <Ico name="filter" size={17} />
          </button>
        </div>

        <div className="hl-section-head">
          <h2>Health Logs</h2>
          <button type="button">See All</button>
        </div>

        <div className="hl-log-grid">
          <section className="hl-log-card">
            <div className="hl-log-card__top">
              <h3>Heart Rate</h3>
              <span className="hl-heart-icon">
                <Ico name="heart" size={15} />
              </span>
            </div>
            <div className="hl-reading">
              <strong>140</strong>
              <span>bpm</span>
            </div>
            <div className="hl-ecg">
              <svg viewBox="0 0 170 62" fill="none" preserveAspectRatio="none">
                <path
                  d="M0 35h9l4-2 4 8 5-26 6 34 7-14 10 6 6-24 7 30 9-12 11 4 8-12 8 18 10-16 8 12 10-6 9 4 9-8h10"
                  stroke="#4C8DFF"
                  strokeWidth="1.5"
                  strokeLinejoin="round"
                  strokeLinecap="round"
                />
              </svg>
              <div className="hl-ecg__tag">140<br />bpm</div>
            </div>
          </section>

          <section className="hl-log-card hl-log-card--blood">
            <div className="hl-log-card__top">
              <h3>Blood Status</h3>
            </div>
            <div className="hl-reading">
              <strong>116/70</strong>
              <span>g/dL</span>
            </div>
            <svg className="hl-dots" viewBox="0 0 104 92" fill="none" aria-hidden="true">
              <g stroke="#E7D9F5" strokeWidth="0.6">
                <path d="M9 6v84M24 6v84M39 6v84M54 6v84M69 6v84M84 6v84M99 6v84" />
              </g>
              {bloodDots.map((dot, index) => (
                <circle key={index} cx={dot.x} cy={dot.y} r={dot.r} fill="#7C4FE0" opacity={dot.o} />
              ))}
            </svg>
          </section>
        </div>

        <div className="hl-section-head">
          <h2>Upcoming Appointment</h2>
          <button type="button">See All</button>
        </div>

        <section className="hl-doctor">
          <div className="hl-doctor__head">
            <Avatar name="Daniel Joseph" size={40} tone="sky" />
            <div>
              <h3>Dr. Daniel Joseph</h3>
              <p>Cardiologist</p>
            </div>
            <button className="hl-video" type="button" aria-label="视频通话">
              <Ico name="video" size={16} />
            </button>
          </div>
          <div className="hl-doctor__meta">
            <div>
              <span>
                <Ico name="calendar" size={12} /> Date
              </span>
              <strong>21 June, Sunday</strong>
            </div>
            <div>
              <span>
                <Ico name="clock" size={12} /> Time
              </span>
              <strong>09am-10am</strong>
            </div>
          </div>
        </section>
      </div>

      <nav className="hl-nav" aria-label="底部导航">
        {navItems.map((item, index) => (
          <button key={index} type="button" className={item.dark ? 'is-dark' : index === 0 ? 'is-active' : ''} aria-label={item.icon}>
            <Ico name={item.icon} size={17} />
          </button>
        ))}
      </nav>
      <HomeBar />
    </Screen>
  )
}
