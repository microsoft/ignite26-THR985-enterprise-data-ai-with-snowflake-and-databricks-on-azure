#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 30 - generates the Contoso Retail data (deterministic) and uploads the raw Parquet files to the
           'landing' container: the bronze layer. Layout: landing/<data_product>/<table>.parquet
.PARAMETER EndDate  Last day of data (a Sunday); its Monday-Sunday week is the demo week. Default from settings.demo.
#>
param([string]$EndDate)
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
if (-not $state.storageAccountName) { throw 'Run 10-azure-foundation.ps1 first.' }
if (-not $EndDate) { $EndDate = $settings.demo.dataEndDate }
$py = Get-PocPython
$gen = Join-Path $PocRoot 'data-generator'
$data = Join-Path $gen 'data'

Write-Step "Generating data (end date $EndDate)"
& $py (Join-Path $gen 'generate_contoso_retail.py') --out $data --end-date $EndDate
if ($LASTEXITCODE -ne 0) { throw 'Data generation failed.' }

Write-Step "Uploading to $($state.storageAccountName)/$($settings.containers.landing) (bronze)"
foreach ($platformDir in Get-ChildItem $data -Directory) {
    foreach ($productDir in Get-ChildItem $platformDir.FullName -Directory) {
        Invoke-AzRetry -Attempts 6 -DelaySeconds 20 storage blob upload-batch --auth-mode login `
            --account-name $state.storageAccountName --destination $settings.containers.landing `
            --destination-path $productDir.Name --source $productDir.FullName --pattern '*.parquet' --overwrite true `
            --no-progress | Out-Null
        Write-Done "$($productDir.Name)/ ($(@(Get-ChildItem $productDir.FullName -Filter *.parquet).Count) files)"
    }
}
Copy-Item (Join-Path $data 'answer_key.json') (Join-Path $PocRoot 'state/answer_key.json') -Force
Write-Done 'answer key copied to state/answer_key.json (used by the checks)'
Write-Step 'Done - next: 40-entra-identity.ps1'
