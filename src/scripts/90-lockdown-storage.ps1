#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 90 (optional, war story D) - turn on the storage firewall and see which engine loses access.
           Allowed: your IP, Snowflake's Azure VNet subnets (python snowflake/platform_info.py), the Databricks Access
           Connector as a resource instance, and - if you pass them - the subnets of a Databricks serverless network
           connectivity configuration (NCC; create it and attach it to the workspace in the account console first).
           Then it re-tests both engines. -Undo opens the storage account again.
.PARAMETER DatabricksSubnetIds  Subnet resource IDs from the NCC's default rules (account console > Cloud resources >
                                Network connectivity configurations > your NCC). Without them, expect serverless reads
                                to fail: that is the war story.
#>
param([string[]]$DatabricksSubnetIds, [switch]$Undo)
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$rg = $settings.resourceGroup
$sa = $state.storageAccountName
if (-not $sa) { throw 'Run 10-azure-foundation.ps1 first.' }

if ($Undo) {
    Write-Step "Opening $sa again (default action Allow)"
    Invoke-Az storage account update --name $sa --resource-group $rg --default-action Allow | Out-Null
    Set-State @{ storageLockedDown = $false }
    Write-Done 'storage firewall off'
    return
}
if (-not $state.snowflakeSubnetIds) { throw 'Run python snowflake/platform_info.py first (Snowflake VNet subnets).' }

Write-Step "Network rules for $sa"
$myIp = Get-MyPublicIp
Invoke-Az storage account network-rule add --account-name $sa --resource-group $rg --ip-address $myIp | Out-Null
Write-Done "your IP $myIp"
foreach ($subnet in $state.snowflakeSubnetIds) {
    Invoke-Az storage account network-rule add --account-name $sa --resource-group $rg --subnet $subnet | Out-Null
    Write-Done "Snowflake subnet $(Split-Path $subnet -Leaf)"
}
Invoke-Az storage account network-rule add --account-name $sa --resource-group $rg --resource-id $state.accessConnectorId `
    --tenant-id $state.tenantId | Out-Null
Write-Done 'Databricks Access Connector (resource instance rule)'
foreach ($subnet in $DatabricksSubnetIds) {
    Invoke-Az storage account network-rule add --account-name $sa --resource-group $rg --subnet $subnet | Out-Null
    Write-Done "Databricks serverless subnet $(Split-Path $subnet -Leaf)"
}
if (-not $DatabricksSubnetIds) { Write-Warn 'No Databricks NCC subnets passed - serverless SQL may lose access to storage (war story D).' }

Write-Step 'Default action: Deny (trusted Azure services still bypass)'
Invoke-Az storage account update --name $sa --resource-group $rg --default-action Deny --bypass AzureServices | Out-Null
Set-State @{ storageLockedDown = $true; myPublicIp = $myIp }
Write-Info 'Waiting 60 s for the firewall to apply...'
Start-Sleep 60

Write-Step 'Re-testing both engines'
$py = Get-PocPython
& $py (Join-Path $PocRoot 'snowflake/check_answers.py')
& $py (Join-Path $PocRoot 'databricks/check_answers.py')
Write-Info 'Failures here are the lesson: give every engine a network path before you close the door. Undo: -Undo'
