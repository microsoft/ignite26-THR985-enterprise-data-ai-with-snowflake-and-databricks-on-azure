#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 99 - removes the Azure side of the PoC: resource group (workspace, storage, Key Vault, Foundry...),
           the soft-deleted Key Vault and Foundry account, the budget, and optionally the Entra users/groups/apps.
           Snowflake is not touched - drop the account objects or the trial account yourself.
#>
param([switch]$RemoveEntra, [switch]$Force)
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$names = Get-Names
$rg = $settings.resourceGroup

if (-not $Force) { Confirm-Continue "Delete resource group '$rg' and everything in it?" }

Write-Step "Deleting resource group $rg (also removes the Databricks managed resource group)"
Invoke-Az group delete --name $rg --yes | Out-Null
Write-Done $rg

Write-Step 'Purging soft-deleted Key Vault and Foundry account'
try { Invoke-Az keyvault purge --name $names.keyVault --location $settings.location | Out-Null; Write-Done $names.keyVault }
catch { Write-Warn "Key Vault purge skipped: $($_.Exception.Message.Split("`n")[0])" }
try {
    Invoke-Az cognitiveservices account purge --name $names.foundryAccount --resource-group $rg --location $settings.location | Out-Null
    Write-Done $names.foundryAccount
} catch { Write-Warn "Foundry purge skipped: $($_.Exception.Message.Split("`n")[0])" }

Write-Step 'Budget'
try {
    Invoke-Az rest --method delete --url "https://management.azure.com/subscriptions/$($state.subscriptionId)/providers/Microsoft.Consumption/budgets/budget-contoso-thr985?api-version=2023-05-01" | Out-Null
    Write-Done 'budget-contoso-thr985'
} catch { Write-Warn 'budget not found' }

if ($RemoveEntra) {
    Write-Step 'Entra users, groups and app registrations'
    foreach ($u in $state.entraUsers.Values) { try { Invoke-Az ad user delete --id $u.upn | Out-Null; Write-Done $u.upn } catch { } }
    foreach ($gid in @($state.entraGroups.Values) + @($state.entraAdminGroupId)) {
        if ($gid) { try { Invoke-Az ad group delete --group $gid | Out-Null } catch { } }
    }
    foreach ($appId in $state.snowflakeResourceAppId, $state.foundryClientAppId) {
        if ($appId) { try { Invoke-Az ad app delete --id $appId | Out-Null; Write-Done "app $appId" } catch { } }
    }
}
Write-Step 'Done. Snowflake: DROP the CORE, COMMERCIAL, LOYALTY and GOVERNANCE databases, integrations and external volumes (or the account).'
