declare module 'lunar-javascript' {
  class Lunar {
    /** month 为负表示闰月（如 -5 = 闰五月） */
    static fromYmd(year: number, month: number, day: number): Lunar;
    getYear(): number;
    getMonth(): number;  // negative = leap month
    getDay(): number;
    getYearGan(): string;
    getYearZhi(): string;
    getMonthGan(): string;
    getMonthZhi(): string;
    getDayGan(): string;
    getDayZhi(): string;
    /** 换算成公历(2026-08-05 补声明:lib/ziwei/share.ts 早在用，只是从前靠 as any 绕过) */
    getSolar(): Solar;
    // 门户轮补声明（2026-11-01 于 lunar-javascript 1.7.3 实测存在）：
    // 干支须分开取（getDayGanZhi 合并方法不存在）；节日、节气、
    // 宜忌、星宿、冲煞、日生肖均实测返回真实值。
    getYearShengXiao(): string;
    getMonthShengXiao(): string;
    getDayShengXiao(): string;
    getTimeShengXiao(): string;
    getYearShengXiaoExact(): string;
    getDayYi(): string[];
    getDayJi(): string[];
    getXiu(): string;
    getDayChong(): string;
    getDaySha(): string;
    /** 节气日返回节气名，非节气日返回空串 */
    getJieQi(): string;
    getFestivals(): string[];
  }

  class Solar {
    static fromYmd(year: number, month: number, day: number): Solar;
    getLunar(): Lunar;
    getYear(): number;
    getMonth(): number;
    getDay(): number;
    getFestivals(): string[];
  }

  /** 农历月信息(2026-06-10 补:闰月大小月边界 clamp 用) */
  class LunarMonth {
    /** month 为负表示闰月(如 -5 = 闰五月);查无此月返回 null */
    static fromYm(year: number, month: number): LunarMonth | null;
    getDayCount(): number;
  }
}
