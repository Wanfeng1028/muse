using System;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Media.Imaging;
using Avalonia.Threading;

namespace VoxLoom.Desktop.Services;

public static class ScreenshotService
{
    public static void SaveWindowPng(Window window, string path, int width = 1600, int height = 900)
    {
        // 确保离屏布局
        window.Width = width;
        window.Height = height;

        var size = new Size(width, height);
        window.Measure(size);
        window.Arrange(new Rect(size));
        window.UpdateLayout();

        // 强制跑一轮 UI 队列
        Dispatcher.UIThread.RunJobs();

        var pixelSize = new PixelSize(width, height);
        var dpi = new Vector(96, 96);
        var rtb = new RenderTargetBitmap(pixelSize, dpi);

        rtb.Render(window);

        rtb.Save(path);
    }
}
