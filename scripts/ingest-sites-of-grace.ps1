param(
  [string]$OutputPath = (Join-Path $PSScriptRoot '..\data\v1\entities\sites-of-grace.json')
)

$ErrorActionPreference = 'Stop'
$apiUrl = 'https://eldenring.wiki.gg/api.php?action=query&prop=revisions&rvprop=ids%7Ctimestamp%7Ccontent&rvslots=main&format=json&titles=Sites%20of%20Grace'
$headers = @{ 'User-Agent' = 'RUNE-PATH-V1-research/0.1 (local source audit)' }
$response = Invoke-RestMethod -Uri $apiUrl -Headers $headers
$page = $response.query.pages.PSObject.Properties.Value
$revision = $page.revisions[0]
$wikitext = [string]$revision.slots.main.'*'

function Get-Slug([string]$Value) {
  $slug = $Value.ToLowerInvariant() -replace '[^a-z0-9]+', '_'
  return $slug.Trim('_')
}

function Get-Layer([string]$Region, [string]$Subgroup, [string]$Name) {
  $value = "$Region $Subgroup $Name"
  if ($value -match 'Siofra|Ainsel|Deeproot|Nokron|Nokstella|Lake of Rot|Subterranean|Mohgwyn|Abyssal Woods') { return 'underground' }
  if ($value -match 'Castle|Academy|Manor|Leyndell|Crumbling Farum|Haligtree|Shadow Keep|Belurat|Enir-Ilim|Midra|Gaol|Catacomb|Cave|Tunnel|Tomb|Forge|Divine Tower|Mausoleum|Raya Lucaria') { return 'legacy' }
  return 'surface'
}

$region = ''
$subgroup = ''
$records = [System.Collections.Generic.List[object]]::new()
foreach ($line in ($wikitext -split "`n")) {
  if ($line -match '^===([^=].*?)===\s*$') {
    $region = ($Matches[1] -replace '^\[\[File:[^\]]+\]\]\s*', '' -replace '\[\[|\]\]', '').Trim()
    $subgroup = ''
    continue
  }
  if ($line -match '^====([^=].*?)====\s*$') {
    $subgroup = ($Matches[1] -replace '\[\[|\]\]', '').Trim()
    continue
  }
  if ($line -match '\|\[\[([^\]|]+)(?:\|[^\]]+)?\]\]' -and $region) {
    $name = $Matches[1].Trim()
    if ($name -and $name -notmatch '^File:' -and $name -ne 'Sites of Grace') {
      $key = "$region|$subgroup|$name"
      if (-not ($records | Where-Object key -eq $key)) {
        $records.Add([pscustomobject]@{
          key = $key
          canonical_id = "grace_$(Get-Slug $region)_$(if($subgroup){Get-Slug $subgroup}else{'main'})_$(Get-Slug $name)"
          name = $name
          region = $region
          subgroup = $subgroup
          layer = Get-Layer $region $subgroup $name
          coordinate_type = 'unplaced_online_catalog'
          verification_state = 'online_single'
          routeable = $false
          source_evidence = "eldenpedia-sites-of-grace-r$($revision.revid)"
        })
      }
    }
  }
}

$records = @($records | ForEach-Object { $_.PSObject.Properties.Remove('key'); $_ } | Sort-Object region, subgroup, name)
$document = [pscustomobject]@{
  dataset_type = 'sites_of_grace_catalog'
  verification_label = 'Online Verified V1'
  source = [pscustomobject]@{
    source_id = 'eldenpedia'
    page_title = $page.title
    page_id = [int]$page.pageid
    revision_id = [int]$revision.revid
    revision_timestamp = $revision.timestamp
    source_url = 'https://eldenring.wiki.gg/wiki/Sites_of_grace'
    api_url = $apiUrl
    license = 'CC BY-SA 4.0 for page text unless otherwise noted'
    captured_on = (Get-Date).ToString('yyyy-MM-dd')
  }
  record_count = $records.Count
  routeable_record_count = @($records | Where-Object routeable).Count
  records = $records
  notes = @(
    'Names and region groupings are extracted from the pinned MediaWiki revision.',
    'No original game XYZ coordinates are asserted.',
    'Catalog records are not route edges; traversal requires separate evidence and explicit transitions.'
  )
}

$parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Path $parent -Force | Out-Null
$document | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $OutputPath -Encoding utf8
Write-Output "WROTE $OutputPath records=$($document.record_count) revision=$($revision.revid)"
