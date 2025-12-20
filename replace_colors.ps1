$files = Get-ChildItem -Path "templates" -Filter "*.html" -Recurse
$replacements = @{
    "orange-500" = "blue-600"
    "orange-600" = "blue-700"
    "orange-400" = "blue-500"
    "orange-300" = "blue-400"
    "orange-700" = "blue-800"
    "orange-accent" = "blue-accent"
    "#f97316" = "#2563eb"
    "#ea580c" = "#1d4ed8"
}

foreach ($file in $files) {
    $content = Get-Content $file.FullName -Raw
    $modified = $false
    
    foreach ($old in $replacements.Keys) {
        if ($content -match $old) {
            $content = $content -replace $old, $replacements[$old]
            $modified = $true
        }
    }
    
    if ($modified) {
        Set-Content -Path $file.FullName -Value $content -NoNewline
        Write-Host "Updated: $($file.Name)"
    }
}

Write-Host "Color replacement complete!"
