#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 55 (first step of phase 6) - the Azure Databricks workspace (Unity Catalog auto-enabled) and the Access
           Connector whose managed identity is the Unity Catalog storage credential. Pricing tier from
           settings.databricks.sku: 'trial' = Premium features with 14 days of free DBUs; after that, compute stops
           until you upgrade the workspace to Premium (the command is printed at the end). Storage
           RBAC enforces one writer per data product: Databricks writes only its own containers and reads the rest.
           Created only when the Databricks phase starts, because the 14 free DBU days start with the workspace.
           Idempotent.
#>
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$names = Get-Names
$rg = $settings.resourceGroup
$loc = $settings.location
if (-not $state.storageAccountId) { throw 'Run 10-azure-foundation.ps1 first.' }

# A spending limit doesn't block the workspace, during the trial or after the upgrade to Premium (verified on a
# Visual Studio subscription). After the upgrade, serverless SQL DBUs come out of the monthly credit.
$policies = (Invoke-Az rest --method get --url "https://management.azure.com/subscriptions/$($state.subscriptionId)?api-version=2022-12-01").subscriptionPolicies
if ($policies.spendingLimit -eq 'On') {
    Write-Info 'The spending limit is ON. That is fine: after the upgrade to Premium, serverless SQL DBUs come out of the monthly credit.'
}

Write-Step "Access Connector $($names.accessConnector) (system-assigned managed identity)"
$ac = $null
try { $ac = Invoke-Az databricks access-connector show --resource-group $rg --name $names.accessConnector } catch { $ac = $null }
if (-not $ac) {
    $ac = Invoke-Az databricks access-connector create --resource-group $rg --name $names.accessConnector `
        --location $loc --identity-type SystemAssigned
}
$acPrincipal = $ac.identity.principalId
Write-Done "principalId $acPrincipal"

Write-Step 'Storage RBAC for the Access Connector (one writer per data product)'
# User delegation SAS needs generateUserDelegationKey at account scope; the SAS is still capped by the
# container-scoped data roles below, so Databricks can only write its own containers.
Set-RoleAssignment -PrincipalId $acPrincipal -Role 'Storage Blob Delegator' -Scope $state.storageAccountId
foreach ($c in $settings.containers.databricksProducts + @($settings.containers.databricksPlatform)) {
    Set-RoleAssignment -PrincipalId $acPrincipal -Role 'Storage Blob Data Contributor' `
        -Scope (Get-ContainerScope $state.storageAccountId $c)
}
foreach ($c in @($settings.containers.landing) + $settings.containers.snowflakeProducts) {
    Set-RoleAssignment -PrincipalId $acPrincipal -Role 'Storage Blob Data Reader' `
        -Scope (Get-ContainerScope $state.storageAccountId $c)
}

Write-Step "Databricks workspace $($names.databricksWorkspace) (sku: $($settings.databricks.sku))"
$ws = $null
try { $ws = Invoke-Az databricks workspace show --resource-group $rg --name $names.databricksWorkspace } catch { $ws = $null }
if (-not $ws) {
    Write-Info 'creating the workspace takes a few minutes...'
    $ws = Invoke-Az databricks workspace create --resource-group $rg --name $names.databricksWorkspace --location $loc `
        --sku $settings.databricks.sku --managed-resource-group $names.databricksManagedResourceGroup
}
$wsUrl = "https://$($ws.workspaceUrl)"
Write-Done $wsUrl

Set-State @{
    accessConnectorId = $ac.id; accessConnectorPrincipalId = $acPrincipal
    databricksWorkspaceId = $ws.id; databricksWorkspaceUrl = $wsUrl; databricksWorkspaceNumericId = $ws.workspaceId
}
Write-Step 'Next'
Write-Info "1. Open $wsUrl once in the browser (signs you in and initializes the workspace)."
Write-Info '2. Open https://accounts.azuredatabricks.net, copy the account ID into config/settings.json > databricks.accountId.'
Write-Info '3. Run python databricks/setup_platform.py (step D1).'
if ($ws.sku.name -eq 'trial') {
    Write-Info "When the 14-day trial ends, compute stops. Upgrade (about 2 minutes, keeps everything):"
    Write-Info "   az resource update --ids $($ws.id) --set sku.name=premium"
}
