// All on-screen copy lives here so it can be tweaked without touching layout.
// Titles are arrays of lines; `muted: true` renders a line in secondary grey.
export const COPY = {
  problem: {
    lines: [
      {text: '10 machines.', muted: true},
      {text: '10 terminals.', muted: true},
      {text: 'One you.'},
    ],
  },
  connect: {
    title: [{text: 'Every device.'}],
    sub: 'Install Connectra Desktop on each machine. Sign in once. It connects outbound.',
  },
  command: {
    prompt: 'Update the model and restart the agent on every machine.',
    agentIntro: 'Found 10 online devices. Running the update on each one.',
    // run_command takes structured argv + cwd (no shell chaining), so the update is one script.
    command: './bin/agent-update',
    args: '--model latest --restart',
    cwd: '~/agents',
    done: 'All 10 machines updated. Agents restarted and reconnected.',
    title: [{text: 'One chat.', muted: true}, {text: 'Every machine.'}],
    titleSub: 'list_devices, then run_command on each device',
  },
  anyAgent: {
    title: [{text: 'Every agent.'}],
    sub: 'Any MCP-compatible client.',
    caption: 'If it speaks MCP, it can reach your machines.',
  },
  anyone: {
    title: [{text: 'Anyone can drive the fleet.'}],
  },
  trust: {
    title: [{text: 'Cloud requests.', muted: true}, {text: 'Local decides.'}],
    bullets: ['No inbound ports', 'No public IP', 'Approval on the machine', 'Undo for file changes'],
  },
  close: {
    line1: 'Every agent. Every device.',
    line2: 'Connected by Connectra.',
    tagline: 'Remote AI. Local authority.',
    url: 'x-connectra.com',
  },
};
