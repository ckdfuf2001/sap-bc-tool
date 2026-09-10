#Requires -Version 5.1
<#
.SYNOPSIS
  새 PC 세팅용: NW RFC SDK zip + pyrfc 휠을 한 번에 설치한다.
  (SDK는 SAP 라이선스상 재배포 금지라 레포에 포함하지 않음. SAP 포털에서 직접 받아둘 것)

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\install_sdk.ps1 `
    -SdkZip "$env:USERPROFILE\Downloads\nwrfc750P_19-70002755.zip" `
    -PyrfcWheel "$env:LOCALAPPDATA\Temp\opencode\pyrfc-3.3.1-cp312-cp312-win_amd64.whl"
#>
param(
    [Parameter(Mandatory = $true)][string]$SdkZip,
    [string]$PyrfcWheel = "",
    [string]$DestDir = "C:\nwrfcsdk"
)

if (-not (Test-Path -LiteralPath $SdkZip)) { throw "SDK zip 없음: $SdkZip" }
Write-Output "SDK 압축 해제: $SdkZip -> $DestDir"
Add-Type -AssemblyName System.IO.Compression.FileSystem
if (Test-Path -LiteralPath $DestDir) { Remove-Item -LiteralPath $DestDir -Recurse -Force }
[System.IO.Compression.ZipFile]::ExtractToDirectory($SdkZip, $DestDir)
$lib = Join-Path $DestDir "nwrfcsdk\lib"
if (-not (Test-Path -LiteralPath (Join-Path $lib "sapnwrfc.dll"))) { throw "sapnwrfc.dll 없음. zip 내용 확인 필요" }

$userPath = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($userPath -notlike "*nwrfcsdk*") {
    [Environment]::SetEnvironmentVariable("PATH", "$lib;$userPath", "User")
    Write-Output "사용자 PATH 등록: $lib"
}
$env:PATH = "$lib;" + $env:PATH

if ($PyrfcWheel -ne "" -and (Test-Path -LiteralPath $PyrfcWheel)) {
    pip install $PyrfcWheel
}
python -c "import pyrfc; print('pyrfc OK', pyrfc.__version__)"
Write-Output "완료. 새 터미널에서 PATH 적용됨."
