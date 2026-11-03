// Colour tokens only (no imports) so scripts/check-contrast.ts can run them under plain Node.
// Replace with tokens derived from the product's own brand / hero image / app stylesheet.
// Keep ONE accent. Every text colour must pass WCAG AA (4.5:1) on every surface in SURFACES.
export const c = {
	bg: '#f4f5f7', // page
	panel: '#ffffff', // windows, cards
	head: '#f8f9fa', // window header strip
	ring: 'rgba(20,23,31,0.10)', // shadow-as-border (non-text)
	hairline: 'rgba(20,23,31,0.08)', // non-text
	shadow: '0 1px 2px rgba(20,23,31,0.06), 0 18px 48px rgba(20,23,31,0.08)',
	ink: '#14171f', // primary text
	text2: '#3d4350', // secondary text
	text3: '#5b6170', // labels / metadata: the lightest text colour allowed
	accent: '#1f5fbf', // placeholder accent: replace with the product's brand colour (keep it text-safe)
	accentTint: '#e8eff9', // highlight background behind ink/accent text
	deny: '#b42318',
	denyTint: '#f8e9e8',
	allow: '#0b6e3e',
	allowTint: '#e7f1ec',
};

/** Surfaces text can sit on; check-contrast tests every TEXT colour against each of these. */
export const SURFACES = {bg: c.bg, panel: c.panel, head: c.head, accentTint: c.accentTint, denyTint: c.denyTint, allowTint: c.allowTint};
/** Text colours (body/label sizes, so all need 4.5:1). */
export const TEXT = {ink: c.ink, text2: c.text2, text3: c.text3, accent: c.accent, deny: c.deny, allow: c.allow};
