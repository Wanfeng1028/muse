// Shared compare-charge gate (合盘对照 60 积分/次), used by both the
// standalone compare page and the mine compare section so neither
// entry point bypasses the price.
// Rules: charge only when both sides are picked; the same pair is
// charged once per component session (changing either side charges
// again); on insufficient balance the second pick is cleared and the
// earn guide is shown (never silent, never partial results).
// Duplicate-charge guards: an in-flight ref (re-renders must not
// re-fire a charge) + the charged-pair check. The onUnpaid callback
// is held in a ref so inline page callbacks do not re-trigger the
// effect; it is only called on a failed charge.

import { useEffect, useRef, useState } from 'react';
import { callFn, cloudConfigured } from './cloud';
import { localSpend, EARN_GUIDE } from './pricing';

export function useCompareCharge(aId: string, bId: string, onUnpaid: () => void): { locked: boolean; note: string } {
  const [chargedPair, setChargedPair] = useState('');
  const [note, setNote] = useState('');
  const onUnpaidRef = useRef(onUnpaid);
  onUnpaidRef.current = onUnpaid;
  const inflightRef = useRef('');

  const pairComplete = !!aId && !!bId && aId !== bId;
  const pairKey = pairComplete ? (aId < bId ? aId + '|' + bId : bId + '|' + aId) : '';
  const locked = pairComplete && pairKey !== chargedPair;

  useEffect(() => {
    if (!pairComplete || pairKey === chargedPair || inflightRef.current === pairKey) return;
    inflightRef.current = pairKey;
    let cancelled = false;
    (async () => {
      if (cloudConfigured()) {
        const res = await callFn<{ delta: number; balance: number }>('points', { action: 'spend', rule: 'compare' });
        if (cancelled) return;
        inflightRef.current = '';
        if (res.ok) {
          setChargedPair(pairKey);
          setNote('已扣 60 积分，合盘对照已解锁（本次查看有效）。');
        } else {
          setNote('积分不足：合盘对照需 60 积分。' + EARN_GUIDE);
          onUnpaidRef.current();
        }
      } else {
        const res = localSpend('compare');
        if (cancelled) return;
        inflightRef.current = '';
        if (res.ok) {
          setChargedPair(pairKey);
          setNote('已扣 ' + res.charged + ' 积分，合盘对照已解锁（本次查看有效）。');
        } else {
          setNote('积分不足：合盘对照需 60 积分，当前余额 ' + ('balance' in res ? res.balance : 0) + '。' + EARN_GUIDE);
          onUnpaidRef.current();
        }
      }
    })();
    // Clear the in-flight marker on cleanup: without this, a cancelled
    // flight (pair changed mid-charge) leaves the marker set, and
    // re-picking the same pair would return early forever -- locked
    // with no charge attempt and no error note.
    return () => {
      cancelled = true;
      if (inflightRef.current === pairKey) inflightRef.current = '';
    };
  }, [aId, bId, chargedPair, pairComplete, pairKey]);

  return { locked, note };
}
