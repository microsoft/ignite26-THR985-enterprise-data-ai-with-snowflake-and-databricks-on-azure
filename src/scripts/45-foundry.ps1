#!/usr/bin/env pwsh
<#
.SYNOPSIS  Step 45 - Microsoft Foundry base setup, run right after Entra (risk-first: a model-quota or role problem
           shows up now, not after Snowflake and Databricks are built): resource (AIServices, East US 2) + project,
           the pinned model deployment every orchestrator uses (gpt-5-mini), Application Insights tracing, and roles:
             * you: Foundry User + Foundry Project Manager (build, publish, Control Plane)
             * Ava, Ben, Cara: Foundry User on the project (chat in the playground) + Foundry Agent Consumer
               (required for OAuth identity passthrough to the MCP servers)
             * the project's managed identity: read traces from Application Insights
           Idempotent. Needs only steps 10 and 40. Connections and agents come later (README phases 5 and 7).
#>
. "$PSScriptRoot/common.ps1"
$settings = Get-Settings
$state = Get-State
$names = Get-Names
$rg = $settings.resourceGroup
$loc = $settings.location
$f = $settings.foundry
if (-not $state.appInsightsId) { throw 'Run 10-azure-foundation.ps1 first.' }
if (-not $state.entraUsers) { throw 'Run 40-entra-identity.ps1 first.' }
function Get-OrNull([scriptblock]$Block) { try { & $Block } catch { $null } }

Write-Step "Foundry resource $($names.foundryAccount) ($loc)"
$acct = Get-OrNull { Invoke-Az cognitiveservices account show --name $names.foundryAccount --resource-group $rg }
if (-not $acct) {
    $acct = Invoke-Az cognitiveservices account create --name $names.foundryAccount --resource-group $rg --location $loc `
        --kind AIServices --sku S0 --custom-domain $names.foundryAccount --allow-project-management true `
        --assign-identity --yes
}
Write-Done $acct.properties.endpoint

Write-Step "Project $($names.foundryProject)"
$proj = Get-OrNull { Invoke-Az cognitiveservices account project show --name $names.foundryAccount --resource-group $rg `
        --project-name $names.foundryProject }
if (-not $proj) {
    $proj = Invoke-AzRetry -Attempts 5 -DelaySeconds 30 cognitiveservices account project create `
        --name $names.foundryAccount --resource-group $rg --location $loc --project-name $names.foundryProject `
        --display-name 'Contoso THR985' --description 'Orchestrators over the Snowflake and Databricks data-product agents' `
        --assign-identity
}
$projectEndpoint = "https://$($names.foundryAccount).services.ai.azure.com/api/projects/$($names.foundryProject)"
Write-Done $projectEndpoint

Write-Step "Model deployment $($f.deploymentName) ($($f.model) $($f.modelVersion), $($f.deploymentSku))"
$dep = Get-OrNull { Invoke-Az cognitiveservices account deployment show --name $names.foundryAccount --resource-group $rg `
        --deployment-name $f.deploymentName }
if (-not $dep) {
    # Foundry quota tiers: a subscription only has quota for the models in its tier (the Free Tier has gpt-5-mini,
    # gpt-4.1-mini and o4-mini, not gpt-5.4-mini). Fail fast with the tier and the alternatives instead of retrying.
    $usage = @(Invoke-Az cognitiveservices usage list --location $loc)
    $quota = $usage | Where-Object { $_.name.value -eq "OpenAI.$($f.deploymentSku).$($f.model)" } | Select-Object -First 1
    if ($quota -and ($quota.limit - $quota.currentValue) -lt $f.capacityThousandTpm) {
        $tier = Get-OrNull { (Invoke-Az rest --method get --url "https://management.azure.com/subscriptions/$($state.subscriptionId)/providers/Microsoft.CognitiveServices/quotaTiers?api-version=2025-10-01-preview").value[0].properties.currentTierName }
        $alternatives = $usage | Where-Object {
            $_.name.value -like "OpenAI.$($f.deploymentSku).*" -and ($_.limit - $_.currentValue) -ge $f.capacityThousandTpm -and
            $_.name.value -notmatch 'finetune|transcribe|tts|audio|realtime|embedding|image|dall|sora|whisper'
        } | ForEach-Object { "$($_.name.value.Split('.', 3)[2] -replace '^gpt4\.', 'gpt-4.') ($($_.limit - $_.currentValue)K)" }
        throw ("No quota for $($f.model) ($($f.deploymentSku)): $($quota.limit - $quota.currentValue)K tokens/min available, " +
            "$($f.capacityThousandTpm)K needed. Quota tier: $tier. Request quota at https://aka.ms/oai/stuquotarequest, or set " +
            "foundry.model, modelVersion and deploymentName in config/settings.json to a model with quota: $($alternatives -join ', ').")
    }
}
# Create or update through ARM: the CLI can't set versionUpgradeOption, and its default lets Azure move the deployment
# to a newer model version on its own. NoAutoUpgrade keeps the demo on the version it was tested with.
$wantPinned = -not $dep -or $dep.properties.versionUpgradeOption -ne 'NoAutoUpgrade' -or $dep.sku.capacity -ne $f.capacityThousandTpm -or
    $dep.properties.model.name -ne $f.model -or $dep.properties.model.version -ne $f.modelVersion
if ($wantPinned) {
    $body = @{ sku = @{ name = $f.deploymentSku; capacity = $f.capacityThousandTpm }
        properties = @{ model = @{ format = 'OpenAI'; name = $f.model; version = $f.modelVersion }
            versionUpgradeOption = 'NoAutoUpgrade' } }
    $tmp = New-TemporaryFile
    $body | ConvertTo-Json -Depth 6 | Set-Content $tmp -Encoding utf8
    try {
        Invoke-AzRetry -Attempts 3 -DelaySeconds 30 rest --method put --body "@$tmp" `
            --url "https://management.azure.com$($acct.id)/deployments/$($f.deploymentName)?api-version=2024-10-01" | Out-Null
    } finally { Remove-Item $tmp -Force }
    for ($n = 1; $n -le 24; $n++) {
        $dep = Invoke-Az cognitiveservices account deployment show --name $names.foundryAccount --resource-group $rg `
            --deployment-name $f.deploymentName
        if ($dep.properties.provisioningState -in 'Succeeded', 'Failed', 'Canceled') { break }
        Start-Sleep -Seconds 5
    }
    if ($dep.properties.provisioningState -ne 'Succeeded') { throw "Deployment $($f.deploymentName): $($dep.properties.provisioningState)" }
}
Write-Done "$($f.capacityThousandTpm)K tokens per minute, version $($f.modelVersion) pinned (versionUpgradeOption $($dep.properties.versionUpgradeOption))"

Write-Step 'Application Insights connection (server-side agent tracing)'
# Same shape as the official foundry-samples Bicep (connection-application-insights.bicep).
$conn = @{ properties = @{
        category = 'AppInsights'; target = $state.appInsightsId; authType = 'ApiKey'; isSharedToAll = $true
        credentials = @{ key = $state.appInsightsConnectionString }
        metadata = @{ ApiType = 'Azure'; ResourceId = $state.appInsightsId } } }
$tmp = New-TemporaryFile
$conn | ConvertTo-Json -Depth 6 | Set-Content $tmp -Encoding utf8
try {
    Invoke-AzRetry -Attempts 3 -DelaySeconds 20 rest --method put --body "@$tmp" `
        --url "https://management.azure.com$($proj.id)/connections/appinsights?api-version=2025-04-01-preview" | Out-Null
} finally { Remove-Item $tmp -Force }
$identity = $proj.PSObject.Properties['identity']
$projMi = if ($identity -and $identity.Value) { $identity.Value.principalId } else { $null }
if (-not $projMi) {
    throw "Project $($names.foundryProject) has no managed identity. Delete it in the portal and re-run this script (it is created with --assign-identity)."
}
Set-RoleAssignment -PrincipalId $projMi -Role 'Log Analytics Reader' -Scope $state.appInsightsId
Set-RoleAssignment -PrincipalId $projMi -Role 'dbc9c667-e97f-4491-aee6-90b9cf960190' -Scope $state.appInsightsId  # Privileged Monitoring Data Reader
Write-Done 'traces flow to Application Insights; the project identity can read GenAI content'

Write-Step 'Roles'
$FoundryUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d'
$FoundryProjectManager = 'eadc314b-1a2d-4efa-be10-5d325db5065e'
Set-RoleAssignment -PrincipalId $state.userObjectId -PrincipalType User -Role $FoundryUser -Scope $acct.id
Set-RoleAssignment -PrincipalId $state.userObjectId -PrincipalType User -Role $FoundryProjectManager -Scope $acct.id
$consumer = Get-OrNull { (Invoke-Az role definition list --name 'Foundry Agent Consumer') | Select-Object -First 1 }
if (-not $consumer) { Write-Warn "'Foundry Agent Consumer' not found in this tenant - users get Foundry User only." }
foreach ($u in $state.entraUsers.Values) {
    Set-RoleAssignment -PrincipalId $u.objectId -PrincipalType User -Role $FoundryUser -Scope $proj.id
    if ($consumer) { Set-RoleAssignment -PrincipalId $u.objectId -PrincipalType User -Role $consumer.name -Scope $proj.id }
}
Write-Done 'Ava, Ben and Cara can chat with the published agents (OAuth passthrough runs as each of them)'

Set-State @{
    foundryAccountId = $acct.id; foundryAccountName = $names.foundryAccount; foundryProjectId = $proj.id
    foundryProjectName = $names.foundryProject; foundryProjectEndpoint = $projectEndpoint
    foundryProjectPrincipalId = $projMi; foundryDeployment = $f.deploymentName
}

Write-Step 'Next'
Write-Info 'Snowflake (README phase 4): python snowflake/keys.py. The AI gateway comes at the checkpoint (phase 5); the'
Write-Info 'OAuth connections, agents and Control Plane follow in two passes: the checkpoint (phase 5) and after Databricks'
Write-Info '(phase 7).'
