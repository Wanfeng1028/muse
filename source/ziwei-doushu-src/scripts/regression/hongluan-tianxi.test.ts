/** Regression coverage for Hongluan/Tianxi placement and palace labels. */
import assert from 'node:assert/strict';
import { generateChart } from '../../lib/ziwei/algorithm';
import { BRANCHES, STEMS } from '../../lib/ziwei/constants';

function placementsFor(year: number, month = 5, day = 15) {
  const chart = generateChart({ year, month, day, hour: 11, gender: 'male', longitude: 120 });
  return chart.palaces.flatMap((palace) =>
    palace.stars
      .filter((star) => star.name === '红鸾' || star.name === '天喜')
      .map((star) => ({
        name: star.name,
        branch: BRANCHES[palace.branch],
        palaceLabel: `${STEMS[palace.stem]}${BRANCHES[palace.branch]}`,
      })),
  );
}

const placements = placementsFor(1974, 1, 28);

assert.deepEqual(
  placements.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
  [
    { name: '天喜', branch: '未', palaceLabel: '辛未' },
    { name: '红鸾', branch: '丑', palaceLabel: '丁丑' },
  ].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')),
  '甲寅年应按卯起子年逆数得到红鸾丑、天喜未；丁丑/辛未是所在宫完整干支',
);

const representativeYears = [2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2016, 2017, 2018, 2019];
for (let yearBranch = 0; yearBranch < 12; yearBranch += 1) {
  const year = representativeYears[yearBranch];
  const yearPlacements = placementsFor(year);
  const hongluan = yearPlacements.filter((item) => item.name === '红鸾');
  const tianxi = yearPlacements.filter((item) => item.name === '天喜');
  const expectedHongluan = (3 - yearBranch + 12) % 12;
  const expectedTianxi = (expectedHongluan + 6) % 12;

  assert.equal(hongluan.length, 1, `${BRANCHES[yearBranch]}年应且仅应有一颗红鸾`);
  assert.equal(tianxi.length, 1, `${BRANCHES[yearBranch]}年应且仅应有一颗天喜`);
  assert.equal(hongluan[0].branch, BRANCHES[expectedHongluan], `${BRANCHES[yearBranch]}年红鸾宫位错误`);
  assert.equal(tianxi[0].branch, BRANCHES[expectedTianxi], `${BRANCHES[yearBranch]}年天喜宫位错误`);
  assert.equal(
    (BRANCHES.indexOf(tianxi[0].branch) - BRANCHES.indexOf(hongluan[0].branch) + 12) % 12,
    6,
    `${BRANCHES[yearBranch]}年红鸾与天喜必须互为对宫`,
  );
}

console.log('✓ 甲寅案例与十二年支红鸾天喜映射、唯一性及对宫关系回归通过');
