# Shared helpers for the contoso-poc PowerShell 7 scripts. Dot-source it: . "$PSScriptRoot/common.ps1"
#Requires -Version 7.2
# Level 1 catches undefined variables (typos). Higher levels also throw on absent state keys, absent properties in
# az JSON and .Count on a single item - all of which these scripts check for on purpose (if (-not $state.x) ...).
Set-StrictMode -Version 1
$ErrorActionPreference = 'Stop'

$script:PocRoot = Split-Path -Parent $PSScriptRoot
$script:StatePath = Join-Path $PocRoot 'state/outputs.json'

# The PoC has its own Azure CLI profile: 'az login' here never touches your other (for example work) sign-ins, and
# they can never leak into these scripts. Python steps use the same folder (python/poc_common.py).
$env:AZURE_CONFIG_DIR = Join-Path $HOME '.azure-contoso-thr985'

function Write-Step([string]$Message) { Write-Host "`n==> $Message" -ForegroundColor Cyan }
function Write-Info([string]$Message) { Write-Host "    $Message" }
function Write-Warn([string]$Message) { Write-Host "    WARNING: $Message" -ForegroundColor Yellow }
function Write-Done([string]$Message) { Write-Host "    OK: $Message" -ForegroundColor Green }

function Get-Settings {
    $path = Join-Path $PocRoot 'config/settings.json'
    if (-not (Test-Path $path)) {
        throw "config/settings.json not found. Copy config/settings.example.json to config/settings.json and fill it in."
    }
    Get-Content $path -Raw | ConvertFrom-Json -Depth 20 -AsHashtable
}

function Get-State {
    if (Test-Path $StatePath) { return (Get-Content $StatePath -Raw | ConvertFrom-Json -Depth 20 -AsHashtable) }
    return @{}
}

function Set-State([hashtable]$Values) {
    $state = Get-State
    foreach ($k in $Values.Keys) { $state[$k] = $Values[$k] }
    New-Item -ItemType Directory -Force -Path (Split-Path $StatePath) | Out-Null
    $state | ConvertTo-Json -Depth 20 | Set-Content -Path $StatePath -Encoding utf8
}

function Get-Names {
    <# Resolves the {suffix} placeholders in settings.names. #>
    $settings = Get-Settings
    $suffix = (Get-State)['suffix']
    if (-not $suffix) { throw "No suffix yet - run 00-preflight.ps1 first." }
    $names = @{}
    foreach ($k in $settings.names.Keys) { $names[$k] = $settings.names[$k].Replace('{suffix}', $suffix) }
    $names
}

function Invoke-Az {
    <# Runs an az command, throws on failure, and returns the JSON az writes to stdout (or $null). stderr - warnings,
       progress bars such as upload-batch's "Finished[####]" - never reaches the JSON parser; it is only shown when
       the command fails. #>
    param([Parameter(ValueFromRemainingArguments)][string[]]$AzArgs)
    $out = [System.Collections.Generic.List[string]]::new()
    $err = [System.Collections.Generic.List[string]]::new()
    & az @AzArgs --only-show-errors -o json 2>&1 | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) { $err.Add("$_") } else { $out.Add("$_") }
    }
    if ($LASTEXITCODE -ne 0) { throw "az $($AzArgs -join ' ') failed:`n$((@($err) + @($out)) -join "`n")" }
    $text = ($out -join "`n").Trim()
    $i = $text.IndexOfAny([char[]]@('{', '['))
    if ($i -lt 0) { return $null }
    return ($text.Substring($i) | ConvertFrom-Json -Depth 50)
}

function Invoke-AzRetry {
    <# Retries transient failures such as RBAC propagation delays. -Attempts and -DelaySeconds must be named:
       every positional argument belongs to az. #>
    [CmdletBinding(PositionalBinding = $false)]
    param([int]$Attempts = 6, [int]$DelaySeconds = 20, [Parameter(ValueFromRemainingArguments)][string[]]$AzArgs)
    for ($n = 1; $n -le $Attempts; $n++) {
        try { return (Invoke-Az @AzArgs) }
        catch {
            if ($n -eq $Attempts) { throw }
            Write-Warn "attempt $n failed, retrying in $DelaySeconds s ($($_.Exception.Message.Split("`n")[0]))"
            Start-Sleep -Seconds $DelaySeconds
        }
    }
}

function Set-RoleAssignment {
    <# Idempotent role assignment for a user or service principal object id. #>
    param([string]$PrincipalId, [string]$Role, [string]$Scope, [string]$PrincipalType = 'ServicePrincipal')
    $existing = Invoke-Az role assignment list --assignee-object-id $PrincipalId --role $Role --scope $Scope
    if ($existing -and @($existing).Count -gt 0) { Write-Info "role '$Role' already assigned at $(Split-Path $Scope -Leaf)"; return }
    Invoke-AzRetry role assignment create --assignee-object-id $PrincipalId --assignee-principal-type $PrincipalType `
        --role $Role --scope $Scope | Out-Null
    Write-Done "assigned '$Role' at $(Split-Path $Scope -Leaf)"
}

function Get-ContainerScope([string]$StorageAccountId, [string]$Container) {
    "$StorageAccountId/blobServices/default/containers/$Container"
}

function Set-KeyVaultAllowlist {
    <# Deny by default; allow one public IP plus trusted Azure services. Idempotent. #>
    param([string]$VaultName, [string]$ResourceGroup, [string]$Ip)
    $kv = Invoke-Az keyvault show --name $VaultName --resource-group $ResourceGroup
    $acls = $kv.properties.PSObject.Properties['networkAcls']
    $rules = if ($acls -and $acls.Value -and $acls.Value.ipRules) { @($acls.Value.ipRules | ForEach-Object { $_.value }) } else { @() }
    if (-not ($rules | Where-Object { $_ -eq $Ip -or $_ -eq "$Ip/32" })) {
        Invoke-Az keyvault network-rule add --name $VaultName --resource-group $ResourceGroup --ip-address "$Ip/32" | Out-Null
    }
    Invoke-Az keyvault update --name $VaultName --resource-group $ResourceGroup --default-action Deny --bypass AzureServices | Out-Null
}

function Get-MyPublicIp { (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 20).Trim() }

function Get-PocPython {
    <# The venv created by 00-preflight.ps1. #>
    $py = Join-Path $PocRoot '.venv/Scripts/python.exe'
    if (-not (Test-Path $py)) { throw "Python venv not found - run 00-preflight.ps1 first." }
    $py
}

function Confirm-Continue([string]$Prompt) {
    $answer = Read-Host "$Prompt [y/N]"
    if ($answer -notmatch '^(y|yes)$') { throw 'Stopped by user.' }
}

function Assert-PersonalTenant {
    <# Stops unless the PoC profile is signed in to settings.tenantId, then selects settings.subscriptionId. #>
    $settings = Get-Settings
    $expected = $settings.tenantId
    if (-not $expected) { throw 'Set tenantId in config/settings.json to your PERSONAL Entra tenant ID.' }
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI not found - install it first.' }
    $account = & az account show -o json --only-show-errors 2>$null | ConvertFrom-Json
    if (-not $account) { throw 'Not signed in to the PoC Azure CLI profile - run scripts/login.ps1 first.' }
    if ($account.tenantId -ne $expected) {
        throw "The PoC Azure CLI profile is signed in to tenant $($account.tenantId), not your personal tenant $expected. Run scripts/login.ps1."
    }
    if ($settings.subscriptionId -and $account.id -ne $settings.subscriptionId) {
        & az account set --subscription $settings.subscriptionId --only-show-errors
        if ($LASTEXITCODE -ne 0) { throw "Subscription $($settings.subscriptionId) isn't available to the signed-in account." }
    }
}

# Every script checks the tenant first (scripts/login.ps1 opts out, because it does the signing in).
if (-not (Get-Variable -Name SkipTenantGuard -ValueOnly -ErrorAction SilentlyContinue)) { Assert-PersonalTenant }
