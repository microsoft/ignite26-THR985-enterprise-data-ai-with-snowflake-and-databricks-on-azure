#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 10 - resource group, Log Analytics + Application Insights, ADLS Gen2 (HNS) with one container per
           data product plus 'landing' (bronze), Key Vault, and an alerts-only budget. Idempotent.
#>
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$names = Get-Names
$rg = $settings.resourceGroup
$loc = $settings.location

Write-Step "Resource group $rg ($loc)"
Invoke-Az group create --name $rg --location $loc --tags project=thr985 owner=$($state.userUpn) | Out-Null
Write-Done $rg

Write-Step 'Log Analytics + Application Insights (tracing for Foundry)'
$law = Invoke-Az monitor log-analytics workspace create --resource-group $rg --workspace-name $names.logAnalytics --location $loc
$appi = Invoke-Az monitor app-insights component create --app $names.appInsights --location $loc --resource-group $rg `
    --workspace $law.id --application-type web --kind web
Write-Done "$($names.logAnalytics) · $($names.appInsights)"

Write-Step "ADLS Gen2 storage account $($names.storageAccount)"
$sa = Invoke-Az storage account create --name $names.storageAccount --resource-group $rg --location $loc `
    --sku Standard_LRS --kind StorageV2 --enable-hierarchical-namespace true --min-tls-version TLS1_2 `
    --allow-blob-public-access false --allow-shared-key-access false --public-network-access Enabled --default-action Allow
Write-Done 'HNS on · shared keys off (Entra only) · public endpoint (lock down later with 90-lockdown-storage.ps1)'

# Soft delete is the recovery story: no Snowflake Fail-safe on external volumes, and blob versioning
# isn't supported on hierarchical-namespace accounts.
Invoke-Az storage account blob-service-properties update --account-name $names.storageAccount --resource-group $rg `
    --enable-delete-retention true --delete-retention-days 14 `
    --enable-container-delete-retention true --container-delete-retention-days 14 | Out-Null
Write-Done 'soft delete for blobs and containers: 14 days'

$containers = @($settings.containers.landing) + $settings.containers.snowflakeProducts +
    $settings.containers.databricksProducts + @($settings.containers.databricksPlatform)
foreach ($c in $containers) {
    Invoke-Az storage container-rm create --storage-account $names.storageAccount --resource-group $rg --name $c | Out-Null
    Write-Done "container $c"
}
Set-RoleAssignment -PrincipalId $state.userObjectId -PrincipalType User -Role 'Storage Blob Data Contributor' -Scope $sa.id

Write-Step "Key Vault $($names.keyVault) (RBAC mode)"
$kv = $null
try { $kv = Invoke-Az keyvault show --name $names.keyVault --resource-group $rg } catch { $kv = $null }
if (-not $kv) {
    $kv = Invoke-Az keyvault create --name $names.keyVault --resource-group $rg --location $loc `
        --enable-rbac-authorization true --retention-days 7
}
Set-RoleAssignment -PrincipalId $state.userObjectId -PrincipalType User -Role 'Key Vault Secrets Officer' -Scope $kv.id
# Only the PoC scripts on this machine read Key Vault, so it is the one endpoint with an IP allowlist.
Set-KeyVaultAllowlist -VaultName $names.keyVault -ResourceGroup $rg -Ip $state.myPublicIp
Write-Done "Key Vault firewall: deny by default, allow $($state.myPublicIp) (refresh with scripts/allow-my-ip.ps1)"

Write-Step 'Budget alerts (alerts only - nothing is blocked)'
$email = if ($settings.budget.alertEmail) { $settings.budget.alertEmail } else { $state.userUpn }
$start = (Get-Date -Day 1).ToString('yyyy-MM-01T00:00:00Z')
$end = (Get-Date -Day 1).AddMonths(6).ToString('yyyy-MM-01T00:00:00Z')
$notifications = @{}
foreach ($t in 50, 80, 100) {
    $notifications["Actual_GreaterThan_$t"] = @{ enabled = $true; operator = 'GreaterThan'; threshold = $t
        thresholdType = 'Actual'; contactEmails = @($email) }
}
$notifications['Forecasted_GreaterThan_100'] = @{ enabled = $true; operator = 'GreaterThan'; threshold = 100
    thresholdType = 'Forecasted'; contactEmails = @($email) }
$budget = @{ properties = @{ category = 'Cost'; amount = $settings.budget.azureMonthlyUsd; timeGrain = 'Monthly'
    timePeriod = @{ startDate = $start; endDate = $end }; notifications = $notifications } }
$tmp = New-TemporaryFile
$budget | ConvertTo-Json -Depth 10 | Set-Content $tmp -Encoding utf8
Invoke-Az rest --method put --body "@$tmp" `
    --url "https://management.azure.com/subscriptions/$($state.subscriptionId)/providers/Microsoft.Consumption/budgets/budget-contoso-thr985?api-version=2023-05-01" | Out-Null
Remove-Item $tmp
Write-Done "monthly budget `$$($settings.budget.azureMonthlyUsd) · emails to $email at 50/80/100% actual and 100% forecast"

Set-State @{
    storageAccountName = $names.storageAccount; storageAccountId = $sa.id
    keyVaultName = $names.keyVault; keyVaultId = $kv.id; keyVaultUri = $kv.properties.vaultUri
    logAnalyticsId = $law.id; appInsightsId = $appi.id; appInsightsConnectionString = $appi.connectionString
}
Write-Step 'Done - next: 30-upload-landing.ps1'
