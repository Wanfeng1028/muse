import {existsSync, readFileSync} from 'node:fs';
import {dirname, isAbsolute, relative, resolve} from 'node:path';
import {describe, expect, it} from 'vitest';

const root = resolve(import.meta.dirname, '..');
const read = (path: string) => readFileSync(resolve(root, path), 'utf8');
const publicDocs = ['README.md', 'docs/USAGE.md', 'docs/EXAMPLES.md', 'docs/TROUBLESHOOTING.md'];
const repository = 'https://github.com/cytxnyu/chuanyuntian-auto-edit-pro';

describe('public release documentation', () => {
  it('identifies the maintainer, installable Skill, and actual public repository', () => {
    const markdown = read('README.md');
    expect(markdown).toMatch(/^# 川云添 · 自动剪辑 Pro/);
    expect(markdown).toContain('chuanyuntian-auto-edit-pro');
    expect(markdown).toContain(`git clone ${repository}.git`);
    expect(markdown).toContain(`${repository}/issues`);
    expect(markdown).toContain('$HOME/.agents/skills/auto-edit-pro');
    expect(markdown).toContain('npm ci');
    expect(markdown).toContain('Node.js 24');
    expect(markdown).toContain('name: auto-edit-pro');
    expect(read('agents/openai.yaml')).toContain('$auto-edit-pro');
    expect(read('SKILL.md')).toMatch(/^---\nname: auto-edit-pro\n/);
    expect(markdown).toContain('https://learn.chatgpt.com/docs/build-skills');
  });

  it('resolves every local document and brand image link inside the release', () => {
    let localLinks = 0;
    for (const document of publicDocs) {
      const links = [...read(document).matchAll(/!?\[[^\]]*\]\(([^)]+)\)/g)].map((match) => match[1]);
      for (const link of links) {
        if (/^https?:\/\//.test(link) || link.startsWith('#')) continue;
        const target = resolve(root, dirname(document), decodeURIComponent(link.split('#')[0]));
        const local = relative(root, target);
        expect(isAbsolute(local), `${document}: ${link}`).toBe(false);
        expect(local.startsWith('..'), `${document}: ${link}`).toBe(false);
        expect(existsSync(target), `${document}: ${link}`).toBe(true);
        localLinks += 1;
      }
    }
    expect(localLinks).toBeGreaterThanOrEqual(20);
    expect(read('README.md')).toContain('](assets/brand-banner.svg)');
    expect(read('assets/brand-banner.svg')).toContain('<svg');
  });

  it('offers a source-preserving prompt with two explicit human approval boundaries', () => {
    const markdown = read('README.md');
    const prompt = markdown.match(/```text\n([\s\S]*?)\n```/)?.[1];
    expect(prompt).toBeDefined();
    for (const phrase of [
      '$auto-edit-pro', 'input.mp4', 'input.srt',
      '保留完整原片、原声、背景、顺序和速度', '等我确认后再补齐',
      '本次先做 Gate A', '完成 Gate B 并自动进入 Gate C',
      '等我明确批准 Gate D', '手势互动记录源帧',
    ]) expect(prompt).toContain(phrase);
    const commands = markdown.split(/\r?\n/).filter((line) => line.startsWith('npm run package-video --'));
    expect(commands).toHaveLength(3);
    expect(commands[0]).not.toContain('--approve-');
    expect(commands[0]).not.toMatch(/(?:^|\s)--render(?:\s|$)/);
    expect(commands[1]).toContain('--approve-gate-a --approve-gate-b');
    expect(commands[1]).not.toContain('--approve-gate-d');
    expect(commands[1]).not.toMatch(/(?:^|\s)--render(?:\s|$)/);
    expect(commands[2]).toContain('--approve-gate-d --render');
  });

  it('documents synthetic Gate A honestly and links reproducible source inputs', () => {
    const examples = read('docs/EXAMPLES.md');
    const pkg = JSON.parse(read('package.json'));
    expect(examples).toContain('4 秒');
    expect(examples).toContain('Gate A 安装自测');
    expect(examples).toContain('测试音不含人声');
    expect(examples).toContain('SRT 不是语音转写');
    expect(examples).toContain('npm run make:synthetic');
    expect(examples).toContain('npm run example:synthetic');
    expect(pkg.scripts['make:synthetic']).toContain('scripts/make-synthetic.ts');
    expect(pkg.scripts['example:synthetic']).toContain('examples/synthetic-horizontal/input.srt');
    expect(pkg.scripts['example:synthetic']).not.toMatch(/(?:^|\s)--render(?:\s|$)/);
    expect(pkg.scripts['example:synthetic']).not.toContain('--approve-');
    expect(read('scripts/make-synthetic.ts')).toContain('duration=4');
    expect(read('examples/synthetic-horizontal/input.srt')).toContain('00:00:04,000');
    expect(read('README.md')).toContain('八种不同语义结构');
    expect(read('README.md')).toContain('71 种');
    expect(read('README.md')).toContain('不是 71 项全览');
    expect(pkg.scripts['list:styles']).toContain('scripts/list-styles.ts');
    expect(pkg.scripts['demo:styles']).toContain('scripts/demo-styles.ts');
  });

  it('keeps project-facing branding consistent and retains required notices in the license', () => {
    const markdown = read('README.md');
    expect(markdown).toContain('川云添（cytxnyu）');
    expect(markdown).not.toContain('品牌化整理');
    expect(markdown).toContain('MIT');
    expect(markdown).toContain('[NOTICE](NOTICE)');
    expect(markdown).toMatch(/\[[^\]]+\]\(LICENSE\)/);
    expect(read('NOTICE')).toContain('Maintained and published by 川云添');
    const copyrightOwners = [...read('LICENSE').matchAll(/^Copyright \(c\) \d{4} (.+)$/gm)].map((match) => match[1]);
    expect(copyrightOwners).toHaveLength(2);
    expect(copyrightOwners).toContain('川云添 (cytxnyu)');
    for (const owner of copyrightOwners.filter((name) => name !== '川云添 (cytxnyu)')) {
      for (const document of [...publicDocs, 'SKILL.md', 'NOTICE', 'PUBLIC_RELEASE_REPORT.md']) {
        expect(read(document), document).not.toContain(owner);
      }
    }
    expect(read('LICENSE')).toContain('The above copyright notice and this permission notice shall be included in all');
    expect(read('LICENSE')).toContain('MIT License');
    for (const document of publicDocs) {
      expect(read(document)).not.toMatch(/examples\/auto-editing-0|docs\/assets\/(?:contact|previews)|wechat-qr/);
    }
  });
});
