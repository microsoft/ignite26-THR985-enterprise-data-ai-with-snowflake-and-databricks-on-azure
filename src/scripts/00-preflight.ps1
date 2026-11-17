#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 00 - checks tools and sign-in, records tenant/subscription/user, registers providers,
           creates the Python venv and generates the unique name suffix. Safe to re-run.
#>
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings

Write-Step 'Tools'
if ($PSVersionTable.PSVersion.Major -lt 7) { throw 'PowerShell 7+ is required.' }
$azVersion = (az version -o json | ConvertFrom-Json).'azure-cli'
Write-Done "Azure CLI $azVersion"
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { throw 'Python 3.10+ is required on PATH.' }
$pyVersion = & python -c "import sys; print('%d.%d' % sys.version_info[:2])"
if ([version]$pyVersion -lt [version]'3.10') { throw "Python 3.10+ required (found $pyVersion)." }
Write-Done "Python $pyVersion"

Write-Step 'Azure sign-in and subscription (PoC profile)'
$account = Invoke-Az account show
$me = Invoke-Az ad signed-in-user show
Write-Done "tenant $($account.tenantId) · subscription '$($account.name)' · signed in as $($me.userPrincipalName)"
Write-Done "profile $env:AZURE_CONFIG_DIR - every script stops unless it is signed in to tenant $($settings.tenantId)"

$sub = Invoke-Az rest --method get --url "https://management.azure.com/subscriptions/$($account.id)?api-version=2022-12-01"
$policies = $sub.subscriptionPolicies
Write-Info "offer quotaId: $($policies.quotaId) · spending limit: $($policies.spendingLimit)"
if ($policies.spendingLimit -eq 'On') {
    Write-Info 'The spending limit is ON: if the credit runs out, Azure disables this subscription until the next billing period. That is fine for this PoC (about US$1.20 a day when idle) if you create the AI gateway from Foundry (README F1): that API Management instance is free for up to 100,000 requests.'
}

Write-Step 'Resource providers'
$namespaces = 'Microsoft.Storage', 'Microsoft.KeyVault', 'Microsoft.Databricks', 'Microsoft.CognitiveServices',
    'Microsoft.Insights', 'Microsoft.OperationalInsights', 'Microsoft.ApiManagement', 'Microsoft.Consumption',
    'Microsoft.Compute', 'Microsoft.Network', 'Microsoft.ManagedIdentity'   # the last three: Databricks workspace
foreach ($ns in $namespaces) {
    if ((Invoke-Az provider show --namespace $ns).registrationState -ne 'Registered') {
        Invoke-Az provider register --namespace $ns | Out-Null
        Write-Info "registering $ns"
    }
}
# Later steps fail with MissingSubscriptionRegistration while a provider is still registering, so wait for all.
for ($n = 1; ; $n++) {
    $pending = @($namespaces | Where-Object { (Invoke-Az provider show --namespace $_).registrationState -ne 'Registered' })
    if (-not $pending) { break }
    if ($n -gt 40) { throw "Still registering after 10 minutes: $($pending -join ', '). Re-run this script later." }
    Write-Info "waiting for $($pending -join ', ') (15 s)"
    Start-Sleep -Seconds 15
}
Write-Done "$($namespaces.Count) resource providers registered"

Write-Step 'Azure CLI extensions'
foreach ($ext in 'databricks', 'application-insights') {
    & az extension add --name $ext --upgrade --only-show-errors 2>&1 | Out-Null
    Write-Done $ext
}

Write-Step 'Python virtual environment'
$venv = Join-Path $PocRoot '.venv'
if (-not (Test-Path $venv)) { & python -m venv $venv; Write-Done "created $venv" }
$venvPy = Join-Path $venv 'Scripts/python.exe'
& $venvPy -m pip install --quiet --upgrade pip
& $venvPy -m pip install --quiet -r (Join-Path $PocRoot 'python/requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'pip install failed.' }
Write-Done 'python/requirements.txt installed'

Write-Step 'Names, public IP and state'
$state = Get-State
$suffix = $state['suffix']
if (-not $suffix) {
    $suffix = -join ((97..122) + (48..57) | Get-Random -Count 6 | ForEach-Object { [char]$_ })
    Write-Info "generated name suffix '$suffix'"
}
$myIp = Get-MyPublicIp
Set-State @{
    suffix = $suffix; tenantId = $account.tenantId; subscriptionId = $account.id
    userUpn = $me.userPrincipalName; userObjectId = $me.id; myPublicIp = $myIp
}
Write-Done "suffix=$suffix · your public IP=$myIp · state/outputs.json updated"

Write-Step 'Snowflake checklist (needed from phase 4 - start the trial now)'
Write-Info '1. Create a NEW Snowflake trial: Enterprise edition, Microsoft Azure, East US 2 (Virginia).'
Write-Info '2. Add a credit card right away (Admin > Billing): AI features are off on trial accounts without one.'
Write-Info '3. Put the account identifier (orgname-accountname) and your user name into config/settings.json > snowflake.'
Write-Info '4. Convert the trial to on-demand before it ends (30 days) - Ignite is on Nov 17.'
Write-Step 'Next: scripts/10-azure-foundation.ps1'
