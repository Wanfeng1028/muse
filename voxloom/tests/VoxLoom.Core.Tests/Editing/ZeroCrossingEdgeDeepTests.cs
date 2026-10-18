using System;
using VoxLoom.Core.Editing;
using Xunit;

namespace VoxLoom.Core.Tests.Editing
{
    public class ZeroCrossingEdgeDeepTests
    {
        // 按源码 FindNearest 步骤推导：
        // 步骤1 ArgumentNullException 检查通过；步骤2 mono.Length==0 不成立（长度1）；
        // 步骤3 index=5 钳位为 mono.Length-1=0；步骤4 searchRadius=10>0 但 mono.Length<2 成立 → 返回 index=0。
        [Fact]
        public void LengthOne_ReturnsClampedIndex()
        {
            var mono = new[] { 0.5f };

            int result = ZeroCrossing.FindNearest(mono, 5, 10);

            Assert.Equal(0, result);
        }

        // 按源码 FindNearest 步骤推导：
        // 步骤1 非空检查通过；步骤2 长度1 非空；步骤3 index=-3<0 → index=0；
        // 步骤4 searchRadius>0 但 mono.Length<2 → 返回 index=0。
        [Fact]
        public void LengthOne_NegativeIndex_ReturnsZero()
        {
            var mono = new[] { 0.5f };

            int result = ZeroCrossing.FindNearest(mono, -3, 10);

            Assert.Equal(0, result);
        }

        // 按源码 FindNearest 步骤推导：
        // 步骤1 非空通过；步骤2 长度3 非空；步骤3 index=5>=3 → index=2；
        // 步骤4 searchRadius=-3<=0 → 直接返回 index=2。
        [Fact]
        public void NegativeSearchRadius_ReturnsClampedIndex()
        {
            var mono = new[] { 1f, -1f, 1f };

            int result = ZeroCrossing.FindNearest(mono, 5, -3);

            Assert.Equal(2, result);
        }

        // 按源码 FindNearest 步骤推导：
        // 步骤1-3 index=0 合法；步骤4 searchRadius=10>0 且长度3>=2；
        // 步骤5 lo=max(0,-10)=0, hi=min(1,10)=1；
        // 步骤6 循环：i=0 时 a=1,b=1 → (a<0&&b>=0)F, (a>0&&b<=0)F, (a==0&&b!=0)F → 不过零；
        //        i=1 时 a=1,b=-1 → (a>0&&b<=0)成立 → 过零，distance=|1-0|=1<MaxValue → bestIndex=1。
        // 步骤7 返回 bestIndex=1。
        [Fact]
        public void CrossingAtLastPair_ReturnsOne()
        {
            var mono = new[] { 1f, 1f, -1f };

            int result = ZeroCrossing.FindNearest(mono, 0, 10);

            Assert.Equal(1, result);
        }

        // 按源码 FindNearest 步骤推导：
        // 步骤1-3 index=0 合法；步骤4 searchRadius=5>0 且长度2>=2；
        // 步骤5 lo=0, hi=min(0,5)=0；
        // 步骤6 i=0：a=0,b=-1 → (a==0&&b!=0)成立 → 过零，distance=0<MaxValue → bestIndex=0。
        // 步骤7 返回 0。
        [Fact]
        public void SingleZeroThenNegative_IsCrossing()
        {
            var mono = new[] { 0f, -1f };

            int result = ZeroCrossing.FindNearest(mono, 0, 5);

            Assert.Equal(0, result);
        }

        // 按源码 FindNearest 步骤推导：
        // 步骤1-3 index=1 合法；步骤4 searchRadius=10>0 且长度4>=2；
        // 步骤5 lo=max(0,-9)=0, hi=min(2,11)=2；
        // 步骤6 i=0：a=-1,b=1 → (a<0&&b>=0)成立 → 过零，distance=|0-1|=1<MaxValue → bestIndex=0, bestDistance=1；
        //        i=1：a=1,b=1 → 不过零；
        //        i=2：a=1,b=-1 → (a>0&&b<=0)成立 → 过零，distance=|2-1|=1，1<1 为 false → 不替换；
        // 步骤7 返回 bestIndex=0（等距取先出现者）。
        [Fact]
        public void EquidistantCrossings_TakesFirst()
        {
            var mono = new[] { -1f, 1f, 1f, -1f };

            int result = ZeroCrossing.FindNearest(mono, 1, 10);

            Assert.Equal(0, result);
        }

        // 按源码 ApplyShortFade 步骤推导：
        // 步骤1 非空通过；步骤2 length=0<=0 → 直接返回，数组任何元素都不被修改。
        [Fact]
        public void ApplyShortFade_ZeroLength_NoChange()
        {
            var mono = new[] { 1f, 2f, 3f };
            var expected = new[] { 1f, 2f, 3f };

            ZeroCrossing.ApplyShortFade(mono, 0, 0);

            Assert.Equal(expected, mono);
        }
    }
}
