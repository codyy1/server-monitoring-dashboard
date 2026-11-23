# Configures VirtualBox NAT port forwarding on "Ubuntu Server" (3306 -> 3306, 2222 -> 22) and boots the VM
param(
    [string]$VmName = "Ubuntu Server"
)

$VBoxManage = "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"
if (-not (Test-Path $VBoxManage)) {
    Write-Error "VBoxManage.exe not found at $VBoxManage"
    exit 1
}

Write-Host "[1/3] Checking VM '$VmName' state..."
$info = & $VBoxManage showvminfo $VmName --machinereadable
$stateLine = $info | Where-Object { $_ -match '^VMState=' }
$vmState = ($stateLine -split '=')[1].Trim('"')
Write-Host "Current VM State: $vmState"

if ($vmState -eq "poweroff") {
    Write-Host "[2/3] Adding NAT port forwarding rules (MySQL 3306, SSH 2222)..."
    & $VBoxManage modifyvm $VmName --natpf1 delete "mysql3306" 2>$null
    & $VBoxManage modifyvm $VmName --natpf1 "mysql3306,tcp,0.0.0.0,3306,,3306"
    & $VBoxManage modifyvm $VmName --natpf1 delete "ssh2222" 2>$null
    & $VBoxManage modifyvm $VmName --natpf1 "ssh2222,tcp,0.0.0.0,2222,,22"
} else {
    Write-Host "[2/3] Adding live controlvm NAT port forwarding rules (MySQL 3306, SSH 2222)..."
    & $VBoxManage startvm $VmName --type headless
    Start-Sleep -Seconds 3
    & $VBoxManage controlvm $VmName natpf1 delete "mysql3306" 2>$null
    & $VBoxManage controlvm $VmName natpf1 "mysql3306,tcp,0.0.0.0,3306,,3306"
    & $VBoxManage controlvm $VmName natpf1 delete "ssh2222" 2>$null
    & $VBoxManage controlvm $VmName natpf1 "ssh2222,tcp,0.0.0.0,2222,,22"
    exit 0
}

Write-Host "[3/3] Starting VirtualBox VM '$VmName' headless..."
& $VBoxManage startvm $VmName --type headless
