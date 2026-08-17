param(
  [string]$OutputPath = (Join-Path $PSScriptRoot '..\data\v1\entities\er-guide-route-legs.json'),
  [string]$Commit = '7f24d64d3631ef4d549f56b42d4c3e3817a269fa'
)

$ErrorActionPreference = 'Stop'
$headers = @{ 'User-Agent' = 'RUNE-PATH-V1-research/0.1'; 'Accept' = 'application/vnd.github+json' }
$apiRoot = 'https://api.github.com/repos/aether-auto/er-guide/contents'
$regionIndexUrl = "$apiRoot/data/regions?ref=$Commit"
$regionListing = Invoke-RestMethod -Uri $regionIndexUrl -Headers $headers -TimeoutSec 30
$regionFiles = [System.Collections.Generic.List[object]]::new()
foreach ($entry in $regionListing) {
  if ($entry.type -eq 'file' -and $entry.name -like '*.json') { $regionFiles.Add($entry) }
}

function Get-StringArray($Value) {
  return @($Value | Where-Object { $_ } | ForEach-Object { [string]$_ } | Sort-Object -Unique)
}

$legs = [System.Collections.Generic.List[object]]::new()
foreach ($file in $regionFiles) {
  if ($legs.Count -gt 0) { Start-Sleep -Milliseconds 1000 }
  Write-Verbose "Fetching $($file.path)" -Verbose
  $uri = "$apiRoot/$($file.path)?ref=$Commit"
  $payload = Invoke-RestMethod -Uri $uri -Headers $headers -TimeoutSec 30
  $document = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String(($payload.content -replace '\s', ''))) | ConvertFrom-Json
  foreach ($leg in @($document.legs)) {
    $steps = @($leg.steps)
    $itemIds = Get-StringArray ($steps | ForEach-Object { $_.itemId })
    $questIds = Get-StringArray ($steps | ForEach-Object { $_.id } | Where-Object { $_ -like 'quest-*' })
    $bossIds = Get-StringArray ($steps | ForEach-Object { $_.id } | Where-Object { $_ -like 'boss-*' })
    $stepTypes = Get-StringArray ($steps | ForEach-Object { $_.type })
    $hasMissable = @($steps | Where-Object { $_.missable }).Count -gt 0
    $legs.Add([pscustomobject]@{
      canonical_id = "er_guide_leg_$($leg.id)"
      upstream_id = $leg.id
      source_file = $file.path
      region_id = $document.id
      region_name = $document.name
      from = [string]$leg.from
      to = [string]$leg.to
      step_types = $stepTypes
      item_ids = $itemIds
      quest_ids = $questIds
      boss_ids = $bossIds
      has_missable_content = $hasMissable
      verification_state = 'online_single'
      routeable = $false
      requires_independent_cross_check = $true
      coordinates_excluded = $true
      source_evidence = "er-guide-main-$Commit"
    })
  }
}

$legs = @($legs | Sort-Object region_id, upstream_id)
$document = [pscustomobject]@{
  dataset_type = 'route_leg_candidate_catalog'
  verification_label = 'Online Candidate — not yet routeable'
  source = [pscustomobject]@{
    source_id = 'er_guide'
    repository = 'https://github.com/aether-auto/er-guide'
    commit = $Commit
    license = 'MIT code; route and imported data require file/source-level audit'
    captured_on = (Get-Date).ToString('yyyy-MM-dd')
    region_file_count = $regionFiles.Count
  }
  record_count = $legs.Count
  routeable_record_count = @($legs | Where-Object routeable).Count
  records = $legs
  notes = @(
    'This artifact imports only structured from/to and step metadata from region JSON files.',
    'Source prose, images, tiles and mixed-origin coordinates are excluded.',
    'Every record remains non-routeable until an independent source confirms direction, entrance and state conditions.'
  )
}

$parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$json = $document | ConvertTo-Json -Depth 10
[IO.File]::WriteAllText([IO.Path]::GetFullPath($OutputPath), $json, (New-Object Text.UTF8Encoding($false)))
Write-Output "WROTE $OutputPath records=$($document.record_count) regions=$($regionFiles.Count) commit=$Commit"
