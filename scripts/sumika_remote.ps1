param(
    [string]$HostName = $env:SUMIKA_ECS_HOST,
    [string]$User = $(if ($env:SUMIKA_ECS_USER) { $env:SUMIKA_ECS_USER } else { "ecs-user" }),
    [string]$RemoteDir = $(if ($env:SUMIKA_REMOTE_DIR) { $env:SUMIKA_REMOTE_DIR } else { "/opt/sumika" }),
    [Parameter(Mandatory = $true)]
    [ValidateSet("health", "send-assets", "agent-status", "napcat-status", "agent-restart", "napcat-restart")]
    [string]$Action,
    [string]$UserId
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($HostName)) {
    throw "HostName is required. Pass -HostName or set SUMIKA_ECS_HOST."
}

$target = "$User@$HostName"
$sshArgs = @("-o", "StrictHostKeyChecking=accept-new", $target)

function Invoke-Remote {
    param([string[]]$Command)
    & ssh @sshArgs -- @Command
}

switch ($Action) {
    "health" {
        Invoke-Remote @("curl", "-fsS", "http://127.0.0.1:8787/health")
    }
    "send-assets" {
        if ([string]::IsNullOrWhiteSpace($UserId)) {
            throw "-UserId is required for send-assets"
        }
        if ($UserId -notmatch '^\d+$') {
            throw "-UserId must be numeric"
        }
        Invoke-Remote @(
            "$RemoteDir/.venv/bin/python",
            "$RemoteDir/scripts/send_sumika_assets.py",
            "import-and-send",
            $UserId
        )
    }
    "agent-status" {
        Invoke-Remote @("systemctl", "is-active", "sumika-agent")
    }
    "napcat-status" {
        Invoke-Remote @("systemctl", "is-active", "napcat-shell")
    }
    "agent-restart" {
        Invoke-Remote @("sudo", "systemctl", "restart", "sumika-agent")
    }
    "napcat-restart" {
        Invoke-Remote @("sudo", "systemctl", "restart", "napcat-shell")
    }
}
