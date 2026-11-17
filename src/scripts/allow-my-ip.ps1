#!/usr/bin/env pwsh
<#
.SYNOPSIS  Refreshes the IP allowlists after your public IP changes (home, hotel, conference Wi-Fi): Key Vault always,
           and the storage firewall too once 90-lockdown-storage.ps1 has been run. Removes the previous IP.
#>
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$rg = $settings.resourceGroup
if (-not $state.keyVaultName) { throw 'Run 10-azure-foundation.ps1 first.' }

$old = $state.myPublicIp
$new = Get-MyPublicIp
Write-Step "Public IP: $new (previous: $old)"

Set-KeyVaultAllowlist -VaultName $state.keyVaultName -ResourceGroup $rg -Ip $new
if ($old -and $old -ne $new) {
    try { Invoke-Az keyvault network-rule remove --name $state.keyVaultName --resource-group $rg --ip-address "$old/32" | Out-Null }
    catch { Write-Warn "could not remove $old from Key Vault (already gone?)" }
}
Write-Done "Key Vault $($state.keyVaultName)"

if ($state.storageLockedDown) {
    Invoke-Az storage account network-rule add --account-name $state.storageAccountName --resource-group $rg --ip-address $new | Out-Null
    if ($old -and $old -ne $new) {
        try { Invoke-Az storage account network-rule remove --account-name $state.storageAccountName --resource-group $rg --ip-address $old | Out-Null }
        catch { Write-Warn "could not remove $old from the storage firewall" }
    }
    Write-Done "storage $($state.storageAccountName)"
}
Set-State @{ myPublicIp = $new }
