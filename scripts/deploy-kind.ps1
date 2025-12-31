param(
  [switch]$Recreate
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Exec($cmd) {
  Write-Host "→ $cmd" -ForegroundColor Cyan
  iex $cmd
}

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $root
Push-Location $repo

try {
  $clusterName = 'homework'
  $kindCfg = Join-Path $repo 'k8s/kind-config.yaml'

  $exists = (kind get clusters) -contains $clusterName
  if ($Recreate -and $exists) {
    Exec "kind delete cluster --name $clusterName"
    $exists = $false
  }
  if (-not $exists) {
    Exec "kind create cluster --name $clusterName --config `"$kindCfg`""
  } else {
    Write-Host "Kind cluster '$clusterName' already exists." -ForegroundColor Yellow
  }

  $images = @(
    @{ path = 'usermanager'; tag = 'homework/usermanager:latest' },
    @{ path = 'datacollector'; tag = 'homework/datacollector:latest' },
    @{ path = 'alertsystem'; tag = 'homework/alertsystem:latest' },
    @{ path = 'alertnotifiersystem'; tag = 'homework/alertnotifiersystem:latest' }
  )

  foreach ($img in $images) {
    $ctx = Join-Path $repo $img.path
    Exec "docker build -t $($img.tag) `"$ctx`""
    Exec "kind load docker-image --name $clusterName $($img.tag)"
  }

  $secretsFile = Join-Path $repo 'k8s/secrets.yaml'
  Exec "kubectl apply -f `"$secretsFile`""

  Exec "kubectl apply -k k8s"

  Write-Host "Deployment submitted. To watch: kubectl get pods -n homework -w" -ForegroundColor Green
  Write-Host "Gateway: https://apigate.com/ mapped to https://localhost/ via kind port 443." -ForegroundColor Green
}
finally {
  Pop-Location
}
