param(
  [ValidateSet("mock", "openai")]
  [string]$Backend = "openai",
  [string]$FlashModel = "ds/deepseek-v4-flash",
  [string]$ProModel = "ds/deepseek-v4-pro",
  [string]$ProxyModel = "ds/deepseek-v4-pro",
  [int]$MaxTurns = 5,
  [int]$NumHypotheses = 4,
  [int]$NumCandidates = 4,
  [int]$RequestTimeout = 600,
  [string]$Dataset = "ambig_swe_10_clean_with_useful_info.jsonl",
  [string]$OutDir = "results/ambig_swe_10_usefulinfo_v1",
  [switch]$VerboseTurns,
  [switch]$Resume
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Resolve-Path $PSScriptRoot
Push-Location $Root
try {
  if (-not (Test-Path -LiteralPath $Dataset)) {
    throw "Dataset not found: $Dataset"
  }

  $SrcPath = Join-Path $Root "src"
  if ($env:PYTHONPATH) {
    $env:PYTHONPATH = "$SrcPath;$env:PYTHONPATH"
  } else {
    $env:PYTHONPATH = $SrcPath
  }

  New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
  $ResumeArgs = @()
  if ($Resume) {
    $ResumeArgs = @("--resume")
  }
  $VerboseArgs = @()
  if ($VerboseTurns) {
    $VerboseArgs = @("--verbose-turns")
  }

  $Runs = @(
    @{ Label = "flash"; Model = $FlashModel },
    @{ Label = "pro"; Model = $ProModel }
  )

  foreach ($Run in $Runs) {
    $Label = $Run.Label
    $Model = $Run.Model
    $BedOut = Join-Path $OutDir "bed_$Label.jsonl"
    $DirectOut = Join-Path $OutDir "direct_$Label.jsonl"
    $ReportOut = Join-Path $OutDir "report_$Label.txt"
    $PerTaskOut = Join-Path $OutDir "per_task_$Label.jsonl"

    & python -m ambig_swe_useful_info.cli run `
      --dataset $Dataset `
      --output $DirectOut `
      --runner direct `
      --backend $Backend `
      --model $Model `
      --proxy-model $ProxyModel `
      --max-turns $MaxTurns `
      --request-timeout $RequestTimeout `
      @VerboseArgs `
      @ResumeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Direct $Label run failed with exit code $LASTEXITCODE"
    }

    & python -m ambig_swe_useful_info.cli run `
      --dataset $Dataset `
      --output $BedOut `
      --runner bed `
      --backend $Backend `
      --model $Model `
      --proxy-model $ProxyModel `
      --max-turns $MaxTurns `
      --num-hypotheses $NumHypotheses `
      --num-candidates $NumCandidates `
      --request-timeout $RequestTimeout `
      @VerboseArgs `
      @ResumeArgs
    if ($LASTEXITCODE -ne 0) {
      throw "BED $Label run failed with exit code $LASTEXITCODE"
    }

    & python -m ambig_swe_useful_info.cli evaluate `
      --bed $BedOut `
      --direct $DirectOut `
      --dataset $Dataset `
      --max-turns $MaxTurns `
      --report $ReportOut `
      --per-task-jsonl $PerTaskOut
    if ($LASTEXITCODE -ne 0) {
      throw "Evaluation $Label failed with exit code $LASTEXITCODE"
    }
  }
}
finally {
  Pop-Location
}
