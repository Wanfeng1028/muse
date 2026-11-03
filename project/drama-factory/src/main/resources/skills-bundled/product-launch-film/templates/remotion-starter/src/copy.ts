// ALL on-screen text lives here (no imports, so scripts/check-layout.ts can read it under plain Node).
// Real CLI/app output must be pasted verbatim from a sandbox capture (docs/captures/); note the source
// next to each string. Only demo data (repo names, test names) may be fictional; list those in the concept doc.

export const TAGLINE = 'Do the thing. Keep the flow.'; // placeholder: write yours before any visuals

export const S1 = {
	title: 'One command. Real output.',
	window: {title: 'Terminal', meta: '~/code/demo'},
	// source: `yourtool --help` captured in sandbox, docs/captures/c-help.txt (placeholder)
	cmd: 'yourtool run --task demo',
	out: ['Resolved 3 inputs -> 1 plan', 'Plan saved to .yourtool/plan.md', 'Done in 1.2s'],
	highlight: 'Plan saved to .yourtool/plan.md',
};
