Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$evidence = "H:\workbuddy\aliceV2\docs\evidence\al343"

function Take-Screenshot { param($Path)
    $screen = [System.Windows.Forms.Screen]::PrimaryScreen
    $bmp = New-Object System.Drawing.Bitmap($screen.Bounds.Width, $screen.Bounds.Height)
    $gfx = [System.Drawing.Graphics]::FromImage($bmp)
    $gfx.CopyFromScreen(0, 0, 0, 0, $screen.Bounds.Size)
    $gfx.Dispose()
    $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
}

Add-Type @"
using System; using System.Runtime.InteropServices; using System.Text;
public class WinApi {
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
}
"@

$allWindows = @{}
$callback = [WinApi+EnumWindowsProc]{
    param($hWnd, $lParam)
    $len = [WinApi]::GetWindowTextLength($hWnd)
    if ($len -gt 0) {
        $sb = New-Object System.Text.StringBuilder($len + 1)
        [WinApi]::GetWindowText($hWnd, $sb, $sb.Capacity) | Out-Null
        $title = $sb.ToString()
        if ($title.Length -gt 0) { $allWindows[$hWnd] = $title }
    }
    return $true
}
[WinApi]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null

$hwnd = [IntPtr]::Zero
foreach ($w in $allWindows.GetEnumerator()) {
    if ($w.Value -match '\u767d\u6cfd' -or $w.Value -like "*白*") { $hwnd = $w.Key }
}

if ($hwnd -ne [IntPtr]::Zero) {
    [WinApi]::ShowWindow($hwnd, 9)
    [WinApi]::SetForegroundWindow($hwnd)
    Start-Sleep -Milliseconds 500
    
    # Type chat message
    [System.Windows.Forms.SendKeys]::SendWait("你好，简单介绍一下你自己")
    Start-Sleep -Milliseconds 500
    [System.Windows.Forms.SendKeys]::SendWait("{ENTER}")
    Write-Host "Message sent, waiting for streaming reply..."
    Start-Sleep -Milliseconds 15000
    
    Take-Screenshot "$evidence\05-chat-streaming.png"
    Write-Host "Chat streaming screenshot taken"
} else {
    Write-Host "Window not found"
}
