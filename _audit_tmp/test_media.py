import subprocess

script = """
try {
    Add-Type -AssemblyName System.Runtime.WindowsRuntime
    $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
    [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager,Windows.Media,ContentType=WindowsRuntime] | Out-Null
    $asyncOp = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()
    $task = $asTaskGeneric.MakeGenericMethod([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]).Invoke($null, @($asyncOp))
    $task.Wait(1500) | Out-Null
    $manager = $task.Result
    $session = $manager.GetCurrentSession()
    if ($session) {
        $info = $session.GetPlaybackInfo()
        $status = $info.PlaybackStatus.ToString()
        Write-Output "STATUS:$status"
    } else {
        Write-Output "STATUS:NO_SESSION"
    }
} catch {
    Write-Output "ERR:$($_.Exception.Message)"
}
"""

p = subprocess.run(['powershell', '-NoProfile', '-Command', script], capture_output=True, text=True, timeout=5)
print("STDOUT:", p.stdout.strip())
print("STDERR:", p.stderr.strip())
