param(
    [string]$HostName = $env:SUMIKA_ECS_HOST,
    [string]$User = $(if ($env:SUMIKA_ECS_USER) { $env:SUMIKA_ECS_USER } else { "ecs-user" }),
    [string]$RemoteDir = $(if ($env:SUMIKA_REMOTE_DIR) { $env:SUMIKA_REMOTE_DIR } else { "/opt/sumika" }),
    [string]$OpenRouterKeyFile = $env:OPENROUTER_KEY_FILE
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($HostName)) {
    throw "HostName is required. Pass -HostName or set SUMIKA_ECS_HOST."
}

$target = "$User@$HostName"

Write-Host "Preparing remote directory $RemoteDir on $target"
ssh -o StrictHostKeyChecking=accept-new $target "mkdir -p '$RemoteDir/secrets'"

Write-Host "Syncing project files"
rsync -av --delete `
    --exclude ".git" `
    --exclude ".venv" `
    --exclude "data" `
    --exclude "secrets" `
    --exclude "deploy/.env" `
    ./ "${target}:$RemoteDir/"

if (![string]::IsNullOrWhiteSpace($OpenRouterKeyFile)) {
    if (!(Test-Path -LiteralPath $OpenRouterKeyFile)) {
        throw "OpenRouter key file not found: $OpenRouterKeyFile"
    }
    Write-Host "Uploading OpenRouter key"
    scp -q "$OpenRouterKeyFile" "${target}:$RemoteDir/secrets/openrouter_key"
    ssh $target "chmod 600 '$RemoteDir/secrets/openrouter_key'"
}

ssh $target "if [ ! -f '$RemoteDir/deploy/.env' ]; then cp '$RemoteDir/deploy/.env.example' '$RemoteDir/deploy/.env'; fi"

Write-Host "Remote files are ready. Install Docker and run compose from the deployment step."
