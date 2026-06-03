# init_db.ps1 — инициализация БД на Windows
# Использование: .\scripts\init_db.ps1 [--incremental]
# По умолчанию --full

param([string]$Mode = "--full")

# Читаем PUBLIC_BASE_URL из shared.env
$PublicBaseUrl = "http://localhost"
if (Test-Path "shared.env") {
    $line = Get-Content "shared.env" | Where-Object { $_ -match "^PUBLIC_BASE_URL=" } | Select-Object -First 1
    if ($line) {
        $PublicBaseUrl = ($line -split "=", 2)[1].Trim().Trim('"').Trim("'")
    }
}

Write-Host "[init_db] Режим: $Mode"
Write-Host "[init_db] PUBLIC_BASE_URL: $PublicBaseUrl"

$cmd = "sed 's|{{PUBLIC_BASE_URL}}|$PublicBaseUrl|g' /app/json_files/resources.json > /app/json_files/resources_deploy.json && cd knowledge_base_scripts/Relational && python -m db_importer.main $Mode --resources-file /app/json_files/resources_deploy.json && rm -f /app/json_files/resources_deploy.json"

docker compose exec -T backend bash -c $cmd

Write-Host "[init_db] Готово"
