package com.dramafactory.service;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import java.util.List;

class SubtitleTranscriptServiceTest {

    @Test
    void parseSrt_正常三条() {
        // 测试正常解析包含三条字幕的SRT内容
        String srt = "1\n00:00:00,000 --> 00:00:02,000\n你好，这是第一镜\n\n2\n00:00:02,000 --> 00:00:04,000\n第二镜的字幕内容\n\n3\n00:00:04,000 --> 00:00:06,000\n第三镜结束";
        List<SubtitleTranscriptService.TranscriptSegment> result = SubtitleTranscriptService.parseSrt(srt);
        
        assertEquals(3, result.size());
        assertEquals(0.0, result.get(0).startSec(), 0.001);
        assertEquals(2.0, result.get(0).endSec(), 0.001);
        assertEquals("你好，这是第一镜", result.get(0).text());
        
        assertEquals(2.0, result.get(1).startSec(), 0.001);
        assertEquals(4.0, result.get(1).endSec(), 0.001);
        assertEquals("第二镜的字幕内容", result.get(1).text());
        
        assertEquals(4.0, result.get(2).startSec(), 0.001);
        assertEquals(6.0, result.get(2).endSec(), 0.001);
        assertEquals("第三镜结束", result.get(2).text());
    }

    @Test
    void parseSrt_多行文本() {
        // 测试解析单条字幕中包含多行文本的情况
        String srt = "1\n00:00:01,000 --> 00:00:02,000\n第一行\n第二行";
        List<SubtitleTranscriptService.TranscriptSegment> result = SubtitleTranscriptService.parseSrt(srt);
        
        assertEquals(1, result.size());
        assertEquals("第一行\n第二行", result.get(0).text());
    }

    @Test
    void parseSrt_兼容CRLF() {
        // 测试兼容Windows风格的CRLF换行符
        String srt = "1\r\n00:00:01,000 --> 00:00:02,000\r\n第一条\r\n\r\n2\r\n00:00:03,000 --> 00:00:04,000\r\n第二条";
        List<SubtitleTranscriptService.TranscriptSegment> result = SubtitleTranscriptService.parseSrt(srt);
        
        assertEquals(2, result.size());
        assertEquals("第一条", result.get(0).text());
        assertEquals("第二条", result.get(1).text());
    }

    @Test
    void parseSrt_坏块跳过() {
        // 测试当SRT中夹带格式错误的时间戳坏块时，能正确跳过并只返回好块
        String srt = "1\n00:00:01,000 --> 00:00:02,000\n好块一\n\n2\n这不是时间戳\n坏块文本\n\n3\n00:00:03,000 --> 00:00:04,000\n好块二";
        List<SubtitleTranscriptService.TranscriptSegment> result = SubtitleTranscriptService.parseSrt(srt);
        
        assertEquals(2, result.size());
        assertEquals("好块一", result.get(0).text());
        assertEquals("好块二", result.get(1).text());
    }

    @Test
    void parseSrt_空内容() {
        // 测试空字符串或纯空白字符的SRT内容应返回空列表
        assertTrue(SubtitleTranscriptService.parseSrt("").isEmpty());
        assertTrue(SubtitleTranscriptService.parseSrt("   ").isEmpty());
    }

    @Test
    void parseVtt_WEBVTT头与NOTE块() {
        // 测试解析包含WEBVTT头和NOTE注释块的VTT内容
        String vtt = "WEBVTT\n\nNOTE 这是注释\n\n00:00:01.000 --> 00:00:03.000\n第一条\n\n00:00:04.000 --> 00:00:06.000\n第二条\n";
        List<SubtitleTranscriptService.TranscriptSegment> result = SubtitleTranscriptService.parseVtt(vtt);
        
        assertEquals(2, result.size());
        assertEquals(1.0, result.get(0).startSec(), 0.001);
        assertEquals(3.0, result.get(0).endSec(), 0.001);
        assertEquals("第一条", result.get(0).text());
        
        assertEquals(4.0, result.get(1).startSec(), 0.001);
        assertEquals(6.0, result.get(1).endSec(), 0.001);
        assertEquals("第二条", result.get(1).text());
    }
}