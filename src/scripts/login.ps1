#!/usr/bin/env pwsh
<#
.SYNOPSIS  Signs in to your PERSONAL tenant in the PoC's own Azure CLI profile (~/.azure-contoso-thr985). Your other
           sign-ins (for example work) stay untouched, and every script stops if this profile is signed in to any
           tenant other than settings.tenantId. Run it once per machine, and again when a script says to.
#>
$SkipTenantGuard = $true
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
if (-not $settings.tenantId) { throw 'Set tenantId in config/settings.json to your PERSONAL Entra tenant ID first.' }

Write-Step "Signing in to tenant $($settings.tenantId) (Azure CLI profile $env:AZURE_CONFIG_DIR)"
& az login --tenant $settings.tenantId --only-show-errors -o none
if ($LASTEXITCODE -ne 0) { throw 'az login failed.' }
Assert-PersonalTenant
$account = Invoke-Az account show
Write-Done "tenant $($account.tenantId) · subscription '$($account.name)' · $($account.user.name)"
Write-Info 'This terminal now uses the PoC profile for az commands - keep it for the PoC and use another one for work.'
Write-Step 'Next: scripts/00-preflight.ps1'
