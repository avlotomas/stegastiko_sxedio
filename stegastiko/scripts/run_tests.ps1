# Run automated tests from the stegastiko project root.
param(
    [ValidateSet("unit", "e2e", "all")]
    [string]$Suite = "unit"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

switch ($Suite) {
    "unit" {
        python -m pytest -m "not e2e" @args
    }
    "e2e" {
        python -m pytest -m e2e @args
    }
    "all" {
        python -m pytest @args
    }
}
