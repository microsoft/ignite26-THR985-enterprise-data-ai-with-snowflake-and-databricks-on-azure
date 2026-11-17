#!/usr/bin/env pwsh
<#
.SYNOPSIS  README step F2 helper: writes the Foundry MCP client app's secret (Key Vault foundry-mcp-client-secret) into
           the custom-OAuth MCP connections created in the Foundry portal, so the secret is never copied by hand.
           Every other property stays as the portal created it, including the redirect URL registered with step 40.
           Connections that already hold the right secret are left alone, so it is safe to re-run.
.PARAMETER Name  Only these connections. Default: every connection named in settings.foundry.connections that exists.
#>
param([string[]]$Name)
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
if (-not $state.foundryProjectId) { throw 'Run 45-foundry.ps1 first.' }
if (-not $state.foundryClientAppId) { throw 'Run 40-entra-identity.ps1 first.' }
$api = '2025-06-01'
$base = "https://management.azure.com$($state.foundryProjectId)/connections"
$names = if ($Name) { $Name } else { @($settings.foundry.connections.Values | Sort-Object) }
$secret = (Invoke-Az keyvault secret show --vault-name $state.keyVaultName --name foundry-mcp-client-secret).value

Write-Step 'Foundry MCP connections: client secret from Key Vault'
foreach ($n in $names) {
    $url = "$base/$n`?api-version=$api"
    try { $p = (Invoke-Az rest --method get --url $url).properties }
    catch {
        if ($_.Exception.Message -match 'NotFound|could not be found|404') { Write-Info "$n - not created yet, skipped"; continue }
        throw
    }
    if ($p.authType -ne 'OAuth2') { Write-Warn "$n uses $($p.authType), not custom OAuth - skipped"; continue }
    $cred = (Invoke-Az rest --method post --url "$base/$n/listsecrets?api-version=$api").properties.credentials
    if ($cred.clientId -ne $state.foundryClientAppId) {
        Write-Warn "$n uses client ID $($cred.clientId), not contoso-foundry-mcp-client - skipped"; continue
    }
    if ($cred.clientSecret -ceq $secret) { Write-Info "$n - already current"; continue }

    # Read-modify-write: resend what the portal stored, with only the secret replaced.
    $props = [ordered]@{}
    foreach ($k in 'authType', 'category', 'target', 'group', 'metadata', 'authorizationUrl', 'tokenUrl', 'refreshUrl',
        'scopes', 'connectorName', 'redirectUrl', 'isSharedToAll', 'useCustomConnector', 'useWorkspaceManagedIdentity',
        'peRequirement') {
        if ($p.PSObject.Properties[$k]) { $props[$k] = $p.$k }
    }
    $props['sharedUserList'] = @($p.sharedUserList)
    $props['credentials'] = [ordered]@{ clientId = $cred.clientId; clientSecret = $secret }
    $tmp = New-TemporaryFile
    try {
        @{ properties = $props } | ConvertTo-Json -Depth 8 | Set-Content $tmp -Encoding utf8
        Invoke-Az rest --method put --url $url --body "@$tmp" | Out-Null
    } finally { Remove-Item $tmp -Force }

    $after = (Invoke-Az rest --method get --url $url).properties
    if ($after.redirectUrl -ne $p.redirectUrl) {
        Write-Warn "$n - redirect URL changed to $($after.redirectUrl): add it with 40-entra-identity.ps1 -RedirectUri"
    }
    Write-Done "$n - client secret updated"
}
Write-Step 'Done - next: python foundry/agents.py (if not run yet), then python foundry/chat.py --as ava'
