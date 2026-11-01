import { useState } from 'react';
import { View, Text, Canvas } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { Card, Disclaimer } from './ui';
import { callFn, tempFileURL, type AiImageResult } from '../lib/cloud';
import { DISCLAIMER } from '../lib/chart';
import type { ZiweiChart } from '../engine/types';

// Share poster: Canvas-drawn on the Medley dark tokens, with the user's
// invite code and (when available) the real invite QR image. Nothing is
// faked: without a real QR fileID the poster draws the code as text plus
// a "小程序码待开通" note; the AI background is optional and only used
// when aiImage returns a real cloud fileID (cached results are reused by
// the server, so repeated posters do not re-spend image tokens).
// The poster is drawn at 300x420 logical points and exported at 2x.

const CANVAS_ID = 'zw-poster';

function mingStars(chart: ZiweiChart): string {
  const ming = chart.palaces.find((p) => p.name === '命宫');
  if (!ming) return '';
  return ming.stars.filter((s) => s.type === 'major').map((s) => s.name).join(' ');
}

async function downloadToLocal(url: string): Promise<string | null> {
  try {
    const res = await Taro.downloadFile({ url });
    if (res && res.tempFilePath) return res.tempFilePath as string;
    return null;
  } catch {
    return null;
  }
}

export function PosterCard({ chart, inviteCode }: { chart: ZiweiChart | null; inviteCode: string }) {
  const [bgPath, setBgPath] = useState('');
  const [qrPath, setQrPath] = useState('');
  const [qrNote, setQrNote] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  function toast(title: string) {
    Taro.showToast({ title, icon: 'none' });
  }

  function draw(bg: string, qr: string) {
    if (!chart) return;
    const ctx = Taro.createCanvasContext(CANVAS_ID);
    if (bg) {
      ctx.drawImage(bg, 0, 0, 300, 420);
      ctx.setFillStyle('rgba(17, 21, 24, 0.55)');
      ctx.fillRect(0, 0, 300, 420);
    } else {
      ctx.setFillStyle('#111518');
      ctx.fillRect(0, 0, 300, 420);
    }
    const dots: Array<[number, string]> = [[24, '#5ec8a7'], [38, '#8fb0d8'], [52, '#d98cb4']];
    dots.forEach(([x, color]) => {
      ctx.setFillStyle(color);
      ctx.beginPath();
      ctx.arc(x, 28, 5, 0, Math.PI * 2);
      ctx.fill();
    });
    ctx.setFillStyle('#f5f5f7');
    ctx.setFontSize(22);
    ctx.fillText('紫微星盘', 66, 36);
    ctx.setFontSize(15);
    ctx.fillText('你的命盘，一眼看懂', 24, 70);
    ctx.setFillStyle('#9a9ba2');
    ctx.setFontSize(14);
    const name = chart.birthInfo.name || '未具名';
    const gender = chart.birthInfo.gender === 'male' ? '男' : '女';
    ctx.fillText(name + ' · ' + gender, 24, 100);
    ctx.fillText('命宫主星：' + (mingStars(chart) || '无主星'), 24, 126);
    ctx.fillText('命主 ' + chart.mingZhu + ' · 身主 ' + chart.shenZhu, 24, 152);
    ctx.setFillStyle('#f5f5f7');
    ctx.setFontSize(14);
    ctx.fillText('邀请码：' + (inviteCode || '—'), 24, 300);
    if (qr) {
      ctx.drawImage(qr, 24, 316, 84, 84);
      ctx.setFillStyle('#9a9ba2');
      ctx.setFontSize(11);
      ctx.fillText('扫码打开紫微星盘', 116, 350);
    } else {
      ctx.setFillStyle('#9a9ba2');
      ctx.setFontSize(11);
      ctx.fillText('小程序码待开通（待 AppID / 环境配置就绪）', 24, 340);
    }
    ctx.setFillStyle('#6b6c72');
    ctx.setFontSize(10);
    ctx.fillText(DISCLAIMER.slice(0, 20), 24, 398);
    ctx.fillText(DISCLAIMER.slice(20), 24, 412);
    ctx.draw();
  }

  async function loadQr() {
    setQrNote('');
    const res = await callFn<{ fileID?: string; placeholder?: boolean; message?: string }>('invite', { action: 'qrcode' });
    if (!res.ok) { setQrNote('小程序码获取失败：' + res.code); return ''; }
    if (res.data.placeholder || !res.data.fileID) {
      setQrNote(res.data.message || '小程序码暂不可用，未返回真实 fileID。');
      return '';
    }
    const url = await tempFileURL(res.data.fileID);
    if (!url) { setQrNote('小程序码临时链接获取失败，请稍后重试。'); return ''; }
    const local = await downloadToLocal(url);
    if (!local) { setQrNote('小程序码下载失败，请稍后重试。'); return ''; }
    setQrPath(local);
    return local;
  }

  async function generatePoster() {
    if (!chart) { toast('请先在首页排盘'); return; }
    setBusy(true);
    const qr = qrPath || (await loadQr());
    draw(bgPath, qr);
    setBusy(false);
    setNote('海报已生成，可点“保存海报到相册”。');
  }

  async function aiBackground() {
    if (!chart) { toast('请先在首页排盘'); return; }
    setBusy(true);
    const res = await callFn<AiImageResult>('aiImage', {
      kind: 'poster',
      prompt: '紫微星盘分享海报背景，中国风星空，简洁留白，深色，适配竖版海报',
    });
    setBusy(false);
    if (!res.ok) { toast('AI 背景生成失败：' + res.code); return; }
    const url = await tempFileURL(res.data.fileID);
    if (!url) { toast('AI 背景链接获取失败'); return; }
    const local = await downloadToLocal(url);
    if (!local) { toast('AI 背景下载失败'); return; }
    setBgPath(local);
    draw(local, qrPath);
    setNote('AI 背景已应用' + (res.data.cached ? '（缓存复用，未重复生图）' : ''));
  }

  async function savePoster() {
    try {
      const res = await Taro.canvasToTempFilePath({ canvasId: CANVAS_ID, destWidth: 600, destHeight: 840 });
      const path = (res as any).tempFilePath as string;
      await Taro.saveImageToPhotosAlbum({ filePath: path });
      toast('海报已保存到相册');
    } catch {
      toast('保存失败：请在设置中允许保存到相册后重试');
    }
  }

  return (
    <Card title='分享海报'>
      {!chart ? <Text className='muted'>请先在首页排盘，再生成分享海报。</Text> : null}
      <Canvas canvasId={CANVAS_ID} style={{ width: '300px', height: '420px', background: '#111518', borderRadius: '16px' }} />
      <View className='btn' style={{ marginTop: '12px' }} onClick={generatePoster}>{busy ? '生成中…' : '生成海报'}</View>
      <View className='btn-ghost' style={{ marginTop: '10px' }} onClick={aiBackground}>AI 背景（云开发省图 token，生图结果缓存复用）</View>
      <View className='btn-ghost' style={{ marginTop: '10px' }} onClick={savePoster}>保存海报到相册</View>
      {qrNote ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{qrNote}</Text> : null}
      {note ? <Text className='muted' style={{ display: 'block', marginTop: '8px' }}>{note}</Text> : null}
      <Disclaimer />
    </Card>
  );
}
