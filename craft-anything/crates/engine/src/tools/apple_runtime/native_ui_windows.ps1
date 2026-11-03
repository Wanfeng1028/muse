# Read, or drive, the UI Automation tree of one process's top-level windows and print JSON
# (runtime_ui_read and runtime_ui_walkthrough_record on Windows). The request arrives as UTF-8
# JSON on standard input, so nothing from it is ever part of this script:
#   {"command":"observe","pid":1234,"window_id":0,"max_nodes":5000}
#   {"command":"walkthrough","pid":1234,"max_nodes":5000,"steps":[{"action":"press","element":"Save"}]}
# A password field's title and value are never read.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, UIAutomationClientsideProviders
try {
  Add-Type -MemberDefinition @'
[DllImport("user32.dll", CharSet = CharSet.Auto)]
public static extern bool PostMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
'@ -Name NativeMethods -Namespace CraftAnything -ErrorAction SilentlyContinue
} catch { }
# The proxies that make Win32 and WinForms controls real buttons, boxes and checkboxes (with their
# password flag) aren't loaded on their own here; registering them needs UI Automation started.
$null = [System.Windows.Automation.AutomationElement]::RootElement
try {
  [System.Windows.Automation.ClientSettings]::RegisterClientSideProviders([UIAutomationClientsideProviders.UIAutomationClientSideProviders]::ClientSideProviderDescriptionTable)
} catch { }
$stdin = New-Object System.IO.MemoryStream
[Console]::OpenStandardInput().CopyTo($stdin)
$req = [Text.Encoding]::UTF8.GetString($stdin.ToArray()) | ConvertFrom-Json
$A = [System.Windows.Automation.AutomationElement]
$max = [int]$req.max_nodes
$window = if ($req.window_id) { [long]$req.window_id } else { 0 }
$walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker

function Windows {
  $cond = New-Object System.Windows.Automation.PropertyCondition($A::ProcessIdProperty, [int]$req.pid)
  @($A::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond) |
    Where-Object { $window -eq 0 -or $_.Current.NativeWindowHandle -eq $window })
}

function Walk($el, $depth) {
  if ($nodes.Count -ge $max) { return }
  # An element can close while it is read; it is left out.
  try {
    $c = $el.Current
    $n = [ordered]@{ depth = $depth; role = $c.ControlType.ProgrammaticName -replace '^ControlType\.', '' }
    # A password box can carry its text as its name; an edit box nothing recognised might be one.
    $secret = $c.IsPassword -or ($c.ControlType -eq [System.Windows.Automation.ControlType]::Pane -and $c.ClassName -match 'edit')
    if ($c.Name -and -not $secret) { $n.title = $c.Name }
    if ($c.AutomationId) { $n.identifier = $c.AutomationId }
    if ($c.ClassName) { $n.class = $c.ClassName }
    $r = $c.BoundingRectangle
    if (-not $r.IsEmpty) { $n.frame = [ordered]@{ x = [int]$r.X; y = [int]$r.Y; w = [int]$r.Width; h = [int]$r.Height } }
    if (-not $c.IsEnabled) { $n.enabled = $false }
    $p = $null
    if (-not $secret -and $el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$p)) {
      $v = [string]$p.Current.Value
      if ($v) { $n.value = if ($v.Length -gt 500) { $v.Substring(0, 500) } else { $v } }
    }
    $nodes.Add($n)
    $child = $walker.GetFirstChild($el)
  } catch { return }
  while ($null -ne $child -and $nodes.Count -lt $max) {
    Walk $child ($depth + 1)
    try { $child = $walker.GetNextSibling($child) } catch { $child = $null }
  }
}

# Every window's tree, read now (a dialog opened by a step is one more window).
function Snapshot {
  $script:nodes = New-Object System.Collections.Generic.List[object]
  foreach ($w in (Windows)) { Walk $w 0 }
  , $script:nodes.ToArray()
}

# The first control, in any window, whose title or automation id is exactly $needle.
function Find($needle) {
  $byName = New-Object System.Windows.Automation.PropertyCondition($A::NameProperty, $needle)
  $byId = New-Object System.Windows.Automation.PropertyCondition($A::AutomationIdProperty, $needle)
  $cond = New-Object System.Windows.Automation.OrCondition($byName, $byId)
  foreach ($w in (Windows)) {
    if ($w.Current.Name -eq $needle -or $w.Current.AutomationId -eq $needle) { return $w }
    $found = $w.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $cond)
    if ($null -ne $found) { return $found }
  }
  $null
}

# What each action may do, in order of preference: (pattern, method).
$ways = @{
  press    = @(@('InvokePattern', 'Invoke'), @('TogglePattern', 'Toggle'), @('SelectionItemPattern', 'Select'), @('ExpandCollapsePattern', 'Expand'))
  expand   = @(, @('ExpandCollapsePattern', 'Expand'))
  showmenu = @(, @('ExpandCollapsePattern', 'Expand'))
  collapse = @(, @('ExpandCollapsePattern', 'Collapse'))
  toggle   = @(, @('TogglePattern', 'Toggle'))
  select   = @(, @('SelectionItemPattern', 'Select'))
}

function Act($el, $action) {
  try {
    if ($action -in 'focus', 'raise') { $el.SetFocus(); return 'dispatched' }
    if (-not $ways.ContainsKey($action)) { return 'unknown_action' }
    foreach ($way in $ways[$action]) {
      $pattern = ("System.Windows.Automation." + $way[0]) -as [type]
      $p = $null
      if ($el.TryGetCurrentPattern($pattern::Pattern, [ref]$p)) {
        try {
          [void]$p.($way[1]).Invoke()
          return 'dispatched'
        } catch {
          # UI Automation's WindowsButton/WindowsCheckBox proxy calls SendInput, which fails with
          # InvalidOperationException when the window is off-screen or running non-interactively
          # (e.g. in tests or background jobs). Fall back to Win32 BM_CLICK for buttons and checkboxes.
          $ct = $el.Current.ControlType
          $hwnd = [IntPtr]$el.Current.NativeWindowHandle
          if ($hwnd -ne [IntPtr]::Zero -and ($ct -eq [System.Windows.Automation.ControlType]::Button -or $ct -eq [System.Windows.Automation.ControlType]::CheckBox)) {
            [void][CraftAnything.NativeMethods]::PostMessage($hwnd, 0x00F5, [IntPtr]::Zero, [IntPtr]::Zero)
            return 'dispatched'
          }
          throw
        }
      }
    }
    'not_supported'
  } catch { 'failed' }
}

$windows = @(Windows).Count
if ($req.command -eq 'walkthrough') {
  $before = Snapshot
  $steps = New-Object System.Collections.Generic.List[object]
  foreach ($s in @($req.steps)) {
    # `AXPress` and `press` are the same action.
    $action = ([string]$s.action).ToLowerInvariant() -replace '^ax', ''
    $el = Find ([string]$s.element)
    $outcome = if ($null -eq $el) { 'element_not_found' } else { Act $el $action }
    $steps.Add([ordered]@{ action = $s.action; element = $s.element; outcome = $outcome })
    Start-Sleep -Milliseconds 400
  }
  $after = Snapshot
  ConvertTo-Json -Depth 5 -Compress -InputObject @{ windows = $windows; steps = $steps.ToArray(); nodes_before = $before; nodes_after = $after }
} else {
  $tree = Snapshot
  ConvertTo-Json -Depth 5 -Compress -InputObject @{ windows = $windows; nodes = $tree; truncated = ($max -gt 0 -and $tree.Count -ge $max) }
}
