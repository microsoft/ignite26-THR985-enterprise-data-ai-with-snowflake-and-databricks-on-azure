#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 40 - Microsoft Entra identities for the demo (personal tenant, Global Administrator):
             * users Ava (West), Ben (East) and Cara (HQ, all regions) with passwords stored in Key Vault
             * region groups plus contoso-hq-analysts (used by Databricks row filters and grants)
             * 'contoso-snowflake-external-oauth' - resource app for Snowflake External OAuth (scope session:role-any)
             * 'contoso-foundry-mcp-client'     - confidential client Foundry uses for OAuth identity passthrough to
                                                  Snowflake and Azure Databricks; secret stored in Key Vault
.PARAMETER RedirectUri  Re-run with the redirect URL(s) Foundry shows when you create the MCP tool OAuth connections
                        (one or more; they are added to the existing ones).
#>
param([string[]]$RedirectUri)
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
if (-not $state.keyVaultName) { throw 'Run 10-azure-foundation.ps1 first.' }
$DatabricksAppId = '2ff814a6-3304-4ab8-85cb-cd0e6f879c1d'   # first-party Azure Databricks resource

function Get-OrNull([scriptblock]$Block) { try { & $Block } catch { $null } }
function Set-KvSecret([string]$Name, [string]$Value) {
    $tmp = New-TemporaryFile
    try {
        Set-Content -Path $tmp -Value $Value -NoNewline -Encoding utf8
        Invoke-Az keyvault secret set --vault-name $state.keyVaultName --name $Name --file $tmp --encoding utf-8 | Out-Null
    } finally { Remove-Item $tmp -Force }
}
function New-Password {
    # Starts with a letter and has no '%' or '@': az.cmd passes arguments through cmd.exe, and az reads a value that
    # starts with '@' as a file name (or '-' as an option). Cryptographic randomness; all four character classes.
    $upper, $lower, $digits, $special = 'ABCDEFGHJKLMNPQRSTUVWXYZ', 'abcdefghijkmnpqrstuvwxyz', '23456789', '!#*-_=+'
    $pick = { param([string]$Set, [int]$Count)
        1..$Count | ForEach-Object { $Set[[System.Security.Cryptography.RandomNumberGenerator]::GetInt32($Set.Length)] } }
    $rest = @(& $pick $upper 3) + @(& $pick $lower 4) + @(& $pick $digits 4) + @(& $pick $special 3) +
        @(& $pick ($upper + $lower + $digits) 9)
    $shuffled = $rest | Sort-Object { [System.Security.Cryptography.RandomNumberGenerator]::GetInt32([int]::MaxValue) }
    -join (@(& $pick ($upper + $lower) 1) + $shuffled)
}

Write-Step 'Tenant domain'
$domain = $settings.entra.domain
if (-not $domain) {
    $domains = (Invoke-Az rest --method get --url 'https://graph.microsoft.com/v1.0/domains').value
    $domain = ($domains | Where-Object isDefault).id
}
Write-Done $domain

Write-Step 'Demo users and region groups'
$users = @{}
foreach ($u in $settings.entra.users) {
    $upn = "$($u.alias)@$domain"
    $user = Get-OrNull { Invoke-Az ad user show --id $upn }
    if (-not $user) {
        $pw = New-Password
        $user = Invoke-Az ad user create --display-name $u.displayName --user-principal-name $upn --password $pw `
            --force-change-password-next-sign-in false
        Set-KvSecret "entra-$($u.alias)-password" $pw
        Write-Done "created $upn (password in Key Vault secret entra-$($u.alias)-password)"
    } else { Write-Info "$upn exists" }
    $users[$u.alias] = @{ upn = $upn; objectId = $user.id; region = $u.region }
}
$groups = @{}
foreach ($region in $settings.entra.groups.Keys) {
    $name = $settings.entra.groups[$region]
    $g = Get-OrNull { Invoke-Az ad group show --group $name }
    if (-not $g) { $g = Invoke-Az ad group create --display-name $name --mail-nickname $name; Write-Done "group $name" }
    $groups[$region] = $g.id
}
foreach ($u in $users.Values) {
    $gid = $groups[$u.region]
    if (-not (Invoke-Az ad group member check --group $gid --member-id $u.objectId).value) {
        Invoke-Az ad group member add --group $gid --member-id $u.objectId | Out-Null
    }
    Write-Done "$($u.upn) -> $($settings.entra.groups[$u.region])"
}
$adminGroupName = $settings.entra.adminGroup
$adminGroup = Get-OrNull { Invoke-Az ad group show --group $adminGroupName }
if (-not $adminGroup) { $adminGroup = Invoke-Az ad group create --display-name $adminGroupName --mail-nickname $adminGroupName }
if (-not (Invoke-Az ad group member check --group $adminGroup.id --member-id $state.userObjectId).value) {
    Invoke-Az ad group member add --group $adminGroup.id --member-id $state.userObjectId | Out-Null
}
Write-Done "$($state.userUpn) -> $adminGroupName (sees every region in Databricks)"

Write-Step "Snowflake External OAuth resource app ($($settings.entra.apps.snowflakeResource))"
$snow = (Invoke-Az ad app list --display-name $settings.entra.apps.snowflakeResource) | Select-Object -First 1
if (-not $snow) { $snow = Invoke-Az ad app create --display-name $settings.entra.apps.snowflakeResource --sign-in-audience AzureADMyOrg }
$appIdUri = "api://$($snow.appId)"
Invoke-Az ad app update --id $snow.appId --identifier-uris $appIdUri | Out-Null
$snowObj = Invoke-Az rest --method get --url "https://graph.microsoft.com/v1.0/applications/$($snow.id)"
$scope = $snowObj.api.oauth2PermissionScopes | Where-Object value -eq 'session:role-any'
if (-not $scope) {
    $scope = @{ id = [guid]::NewGuid().ToString(); value = 'session:role-any'; type = 'Admin'; isEnabled = $true
        adminConsentDisplayName = 'Snowflake session (default role)'
        adminConsentDescription = 'Lets the app open a Snowflake session as the signed-in user with the user''s default role.' }
    $body = @{ api = @{ oauth2PermissionScopes = @($scope) } } | ConvertTo-Json -Depth 6
    $tmp = New-TemporaryFile; Set-Content $tmp $body -Encoding utf8
    Invoke-Az rest --method patch --url "https://graph.microsoft.com/v1.0/applications/$($snow.id)" --body "@$tmp" `
        --headers 'Content-Type=application/json' | Out-Null
    Remove-Item $tmp
}
if (-not (Get-OrNull { Invoke-Az ad sp show --id $snow.appId })) { Invoke-Az ad sp create --id $snow.appId | Out-Null }
Write-Done "App ID URI $appIdUri · scope session:role-any ($($scope.id))"

Write-Step "Foundry MCP client app ($($settings.entra.apps.foundryMcpClient))"
$dbxSp = Get-OrNull { Invoke-Az ad sp show --id $DatabricksAppId }
if (-not $dbxSp) { $dbxSp = Invoke-Az ad sp create --id $DatabricksAppId }
$dbxScope = @($dbxSp.oauth2PermissionScopes | Where-Object value -eq 'user_impersonation') | Select-Object -First 1
if (-not $dbxScope) { throw "The Azure Databricks service principal ($DatabricksAppId) exposes no 'user_impersonation' scope." }
$dbxScopeId = $dbxScope.id
$client = (Invoke-Az ad app list --display-name $settings.entra.apps.foundryMcpClient) | Select-Object -First 1
$isNew = -not $client
if ($isNew) { $client = Invoke-Az ad app create --display-name $settings.entra.apps.foundryMcpClient --sign-in-audience AzureADMyOrg }
if (-not (Get-OrNull { Invoke-Az ad sp show --id $client.appId })) { Invoke-Az ad sp create --id $client.appId | Out-Null }
# 'az ad app permission add' appends without checking, so only add what's missing (safe to re-run).
$granted = @((Invoke-Az ad app show --id $client.appId).requiredResourceAccess)
foreach ($perm in @(@{ api = $snow.appId; scopeId = $scope.id }, @{ api = $DatabricksAppId; scopeId = $dbxScopeId })) {
    $entry = $granted | Where-Object { $_.resourceAppId -eq $perm.api } | Select-Object -First 1
    if (-not ($entry -and @($entry.resourceAccess | Where-Object { $_.id -eq $perm.scopeId }).Count)) {
        Invoke-Az ad app permission add --id $client.appId --api $perm.api --api-permissions "$($perm.scopeId)=Scope" | Out-Null
    }
}
Invoke-AzRetry -Attempts 6 -DelaySeconds 20 ad app permission admin-consent --id $client.appId | Out-Null
Write-Done 'delegated permissions: Snowflake session:role-any + Azure Databricks user_impersonation (admin consent granted)'
$secretStored = @(Invoke-Az keyvault secret list --vault-name $state.keyVaultName --query "[?name=='foundry-mcp-client-secret']").Count -gt 0
if ($isNew -or -not $secretStored) {
    $cred = Invoke-Az ad app credential reset --id $client.appId --display-name 'foundry-mcp' --years 1 --append
    Set-KvSecret 'foundry-mcp-client-secret' $cred.password
    Write-Done 'client secret stored in Key Vault secret foundry-mcp-client-secret'
} else { Write-Info 'client secret already in Key Vault (foundry-mcp-client-secret)' }
$redirects = @()
if ($RedirectUri) {
    $current = @((Invoke-Az ad app show --id $client.appId).web.redirectUris)
    $redirects = @($current + $RedirectUri | Where-Object { $_ } | Sort-Object -Unique)
    Invoke-Az ad app update --id $client.appId --web-redirect-uris @redirects | Out-Null
    Write-Done "redirect URIs: $($redirects -join ', ')"
}

Set-State @{
    entraDomain = $domain; entraUsers = $users; entraGroups = $groups; entraAdminGroupId = $adminGroup.id
    snowflakeResourceAppId = $snow.appId; snowflakeResourceAppIdUri = $appIdUri; snowflakeScopeId = $scope.id
    foundryClientAppId = $client.appId; foundryClientSecretSet = $true
    foundryOAuthRedirectUri = $(if ($RedirectUri) { $RedirectUri[0] } else { $state.foundryOAuthRedirectUri })
    foundryOAuthRedirectUris = $(if ($RedirectUri) { $redirects } else { $state.foundryOAuthRedirectUris })
}
if ($RedirectUri) { Write-Step 'Done - next: python foundry/agents.py (README step F3)' }
else { Write-Step 'Done - next: scripts/45-foundry.ps1 (Foundry setup), then Snowflake (python snowflake/keys.py)' }
Write-Info 'Sign in once as Ava, Ben and Cara (private browser windows) to register MFA - passwords are in Key Vault.'
