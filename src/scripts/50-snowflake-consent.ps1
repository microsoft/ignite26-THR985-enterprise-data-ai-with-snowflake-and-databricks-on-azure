#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 50 - lets Snowflake reach ADLS: admin consent for Snowflake's multi-tenant app, then storage RBAC for its
           service principal. Snowflake writes only its own containers (core, commercial, loyalty) and reads landing.
           Run after: python snowflake/run_snowflake.py --only 00 10 ; python snowflake/azure_consent_info.py
.NOTES     After consent, Azure can take an hour or more to create Snowflake's service principal in your tenant -
           the script waits and retries.
#>
. "$PSScriptRoot/common.ps1"
$state = Get-State
if (-not $state.snowflakeAzureApps) { throw 'Run python snowflake/azure_consent_info.py first.' }

Write-Step 'Admin consent for Snowflake''s multi-tenant app'
$urls = $state.snowflakeAzureApps | ForEach-Object { $_.consentUrl } | Sort-Object -Unique
foreach ($url in $urls) {
    Write-Info "Opening: $url"
    Start-Process $url
    Read-Host '    Sign in as a Global Administrator, select Accept, then press Enter here'
}

Write-Step 'Waiting for Snowflake service principals and assigning storage roles'
$delegated = @{}
foreach ($app in $state.snowflakeAzureApps) {
    $spName = $app.appName.Split('_')[0]
    $sp = $null
    for ($n = 1; $n -le 40 -and -not $sp; $n++) {
        $sp = (Invoke-Az ad sp list --display-name $spName) | Select-Object -First 1
        if (-not $sp) { Write-Info "service principal '$spName' not visible yet (attempt $n/40) - waiting 90 s"; Start-Sleep 90 }
    }
    if (-not $sp) { throw "Service principal '$spName' never appeared. Re-run this script later." }
    # Snowflake reads and writes through a user delegation SAS: generateUserDelegationKey must be granted at
    # storage-account scope. The SAS can't exceed the container-scoped data role, so one-writer-per-product holds.
    if (-not $delegated[$sp.id]) {
        Set-RoleAssignment -PrincipalId $sp.id -Role 'Storage Blob Delegator' -Scope $state.storageAccountId
        $delegated[$sp.id] = $true
    }
    Set-RoleAssignment -PrincipalId $sp.id -Role $app.role -Scope (Get-ContainerScope $state.storageAccountId $app.container)
    Write-Done "$($app.object) -> $spName : $($app.role) on $($app.container)"
}
Write-Info 'Role assignments can take a few minutes to apply. 20_silver.sql starts with SYSTEM$VERIFY_EXTERNAL_VOLUME:'
Write-Info 'if it fails, wait a few minutes and run the same command again.'
Write-Step 'Done - next: python snowflake/run_snowflake.py --only 20 30 40 50 60'
