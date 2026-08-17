$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$productionScript = Join-Path $repoRoot 'diag-build-tools\Invoke-AllevaEndUserTools.ps1'
. $productionScript -NoRun -NoPause -SettingsPath (Join-Path $env:TEMP 'alleva-synthetic-settings-not-used.json') -LogDirectory (Join-Path $env:TEMP 'alleva-synthetic-logs-not-used') -ExportDirectory (Join-Path $env:TEMP 'alleva-synthetic-exports-not-used')

Describe 'Alleva retained-script baseline behavior' {
    It 'normalizes arrays and common JSON collection envelopes without changing record order' {
        $arrayPayload = @([pscustomobject]@{ id = 'synthetic-1' }, [pscustomobject]@{ id = 'synthetic-2' })
        $itemsPayload = [pscustomobject]@{ items = $arrayPayload; total = 2 }

        $arrayRecords = @(Get-RecordsFromPayload $arrayPayload)
        $itemRecords = @(Get-RecordsFromPayload $itemsPayload)

        $arrayRecords.Count | Should Be 2
        $itemRecords.Count | Should Be 2
        $itemRecords[0].id | Should Be 'synthetic-1'
        $itemRecords[1].id | Should Be 'synthetic-2'
    }

    It 'returns no collection records for null or scalar payloads' {
        @(Get-RecordsFromPayload $null).Count | Should Be 0
        @(Get-RecordsFromPayload 'synthetic-scalar').Count | Should Be 0
    }

    It 'merges only recognized settings keys over defaults' {
        $settingsPath = Join-Path $TestDrive 'settings.json'
        '{"Limit":37,"ApiVersion":"synthetic-v2","UnknownSyntheticKey":"ignored"}' | Set-Content -LiteralPath $settingsPath -Encoding UTF8
        $script:SettingsPath = $settingsPath

        Import-Settings

        $script:Settings['Limit'] | Should Be 37
        $script:Settings['ApiVersion'] | Should Be 'synthetic-v2'
        $script:Settings['MaxPages'] | Should Be 10
        $script:Settings.Contains('UnknownSyntheticKey') | Should Be $false
    }

    It 'keeps defaults and does not throw when settings JSON is malformed' {
        $settingsPath = Join-Path $TestDrive 'malformed-settings.json'
        '{not-json' | Set-Content -LiteralPath $settingsPath -Encoding UTF8
        $script:SettingsPath = $settingsPath

        { Import-Settings } | Should Not Throw
        $script:Settings['Limit'] | Should Be 500
        $script:Settings['MaxPages'] | Should Be 10
    }

    It 'handles a synthetic payload nested more than 100 levels without crashing the host' {
        $root = [ordered]@{}
        $cursor = $root
        for ($i = 0; $i -lt 110; $i++) {
            $next = [ordered]@{}
            $cursor["level$i"] = $next
            $cursor = $next
        }
        $cursor['leaf'] = 'synthetic-deep-value'

        { ConvertTo-FlattenedHashtable $root } | Should Not Throw
    }
}

Describe 'Todo 1 noninteractive entry-point contract' {
    It 'declares the action, no-run, no-pause, provider, row-limit, and failure-hook seams' {
        $tokens = $null
        $errors = $null
        $ast = [System.Management.Automation.Language.Parser]::ParseFile($productionScript, [ref]$tokens, [ref]$errors)
        $errors.Count | Should Be 0

        $parameterNames = @($ast.ParamBlock.Parameters | ForEach-Object { $_.Name.VariablePath.UserPath })
        foreach ($name in @('Action','NoRun','NoPause','PageProvider','DetailProvider','RetryDelayProvider','WorksheetRowLimit','FailureHook','ExportDirectory')) {
            ($parameterNames -contains $name) | Should Be $true
        }
    }

    It 'loads with NoRun without creating output or entering the menu' {
        $outputRoot = Join-Path $TestDrive 'no-run-output'
        $arguments = @(
            '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $productionScript),
            '-Action', 'Menu', '-NoRun', '-NoPause', '-ExportDirectory', ('"{0}"' -f $outputRoot),
            '-LogDirectory', ('"{0}"' -f (Join-Path $TestDrive 'no-run-logs')),
            '-SettingsPath', ('"{0}"' -f (Join-Path $TestDrive 'no-run-settings.json'))
        )
        $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -PassThru -Wait -NoNewWindow

        $process.ExitCode | Should Be 0
        (Test-Path -LiteralPath $outputRoot) | Should Be $false
    }

    It 'runs a synthetic self-test without settings or network access and emits one result artifact' {
        $outputRoot = Join-Path $TestDrive 'self-test-output'
        $arguments = @(
            '-NoLogo', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ('"{0}"' -f $productionScript),
            '-Action', 'SelfTest', '-NoPause', '-ExportDirectory', ('"{0}"' -f $outputRoot),
            '-LogDirectory', ('"{0}"' -f (Join-Path $TestDrive 'self-test-logs')),
            '-SettingsPath', ('"{0}"' -f (Join-Path $TestDrive 'missing-settings.json'))
        )
        $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -PassThru -Wait -NoNewWindow

        $process.ExitCode | Should Be 0
        $results = @(Get-ChildItem -LiteralPath $outputRoot -Filter 'alleva-end-user-self-test-*.json' -File)
        $results.Count | Should Be 1
        (Get-Content -LiteralPath $results[0].FullName -Raw | ConvertFrom-Json).status | Should Be 'PASS'
    }

    It 'forwards CMD arguments, preserves the PowerShell exit code, and gates pause behavior' {
        $cmdPath = Join-Path $repoRoot 'diag-build-tools\Run-AllevaEndUserTools.cmd'
        $cmd = Get-Content -LiteralPath $cmdPath -Raw

        $cmd | Should Match '-File\s+"%PS_SCRIPT%"\s+%\*'
        $cmd | Should Match 'exit\s+/b\s+%EXIT_CODE%'
        $cmd | Should Match '(?i)SHOULD_PAUSE'
        $cmd | Should Match 'if\s+not\s+"%~1"==""\s+set\s+"SHOULD_PAUSE=0"'
    }

    It 'does not pause and propagates exit 1 for an invalid Action even without NoPause' {
        $cmdPath = Join-Path $repoRoot 'diag-build-tools\Run-AllevaEndUserTools.cmd'
        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = 'cmd.exe'
        $startInfo.Arguments = ('/d /c call "{0}" -Action InvalidSyntheticAction' -f $cmdPath)
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $completed = $process.WaitForExit(10000)
        if (-not $completed) {
            $process.Kill()
            $process.WaitForExit()
        }
        $stdout = $stdoutTask.Result
        [void]$stderrTask.Result

        $completed | Should Be $true
        $process.ExitCode | Should Be 1
        $stdout | Should Match 'Tool exited with error code 1'
    }

    It 'uses injected page and detail providers without contacting Alleva' {
        $script:Settings = Get-DefaultSettings
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            [pscustomobject]@{ items = @([pscustomobject]@{ id = 'synthetic-page-record' }); hasMore = $false }
        }
        $script:DetailProvider = {
            param($Path, $Query, $Label, $PlanId)
            [pscustomobject]@{ id = $PlanId; detailOnly = 'synthetic-detail' }
        }

        try {
            $records = @(Invoke-AllevaCollection -Path '/synthetic' -Query @{ Limit = 10; Cursor = 0 } -MaxPages 1 -Label 'synthetic-page')
            $detail = Invoke-FullTreatmentPlanPull -Plan ([pscustomobject]@{ id = 'synthetic-plan' })

            $records.Count | Should Be 1
            $records[0].id | Should Be 'synthetic-page-record'
            $detail.detailOnly | Should Be 'synthetic-detail'
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
        }
    }

    It 'exposes the injected row limit and deterministic failure hook' {
        $script:WorksheetRowLimit | Should Be 1048576
        $script:FailureHook = { param($Stage) throw "synthetic-failure:$Stage" }
        try {
            { Invoke-InjectedFailureHook -Stage 'test-stage' } | Should Throw 'synthetic-failure:test-stage'
        } finally {
            $script:FailureHook = $null
        }
    }
}

function New-SyntheticRecords {
    param([int]$Start, [int]$Count)
    $records = New-Object System.Collections.Generic.List[object]
    for ($index = 0; $index -lt $Count; $index++) {
        $records.Add([pscustomobject]@{ id = ('synthetic-{0:D5}' -f ($Start + $index)); value = ($Start + $index) })
    }
    return $records.ToArray()
}

Describe 'Todo 2 complete streaming collection core' {
    It 'preserves a scalar leaf nested more than 100 levels deep without recursion failure or truncation' {
        $root = [ordered]@{}
        $cursor = $root
        $segments = New-Object System.Collections.Generic.List[string]
        for ($i = 0; $i -lt 110; $i++) {
            $name = "level$i"
            $segments.Add($name)
            $next = [ordered]@{}
            $cursor[$name] = $next
            $cursor = $next
        }
        $cursor['leaf'] = 'synthetic-deep-value'
        $expectedPath = (($segments.ToArray() + 'leaf') -join '.')

        $flat = ConvertTo-FlattenedHashtable $root
        $flat[$expectedPath] | Should Be 'synthetic-deep-value'
    }

    It 'completes empty and single-record collections only after observing a terminal condition' {
        $script:syntheticCalls = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $script:syntheticCalls++
            [pscustomobject]@{ items = @() }
        }
        try {
            $empty = Invoke-CompleteCollection -Path '/synthetic-empty' -Query @{ Limit = 5; Cursor = 0 } -CollectRecords
            $empty.Complete | Should Be $true
            $empty.TerminationReason | Should Be 'empty_page'
            $empty.RawRecordCount | Should Be 0
            $empty.UniqueRecordCount | Should Be 0
            $script:syntheticCalls | Should Be 1

            $script:syntheticCalls = 0
            $script:PageProvider = {
                param($Path, $Query, $Label, $PageIndex)
                $script:syntheticCalls++
                if ([int]$Query['Cursor'] -eq 0) {
                    return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1) }
                }
                return [pscustomobject]@{ items = @() }
            }
            $one = Invoke-CompleteCollection -Path '/synthetic-one' -Query @{ Limit = 5; Cursor = 0 } -CollectRecords
            $one.Complete | Should Be $true
            $one.TerminationReason | Should Be 'empty_page'
            $one.PageCount | Should Be 2
            $one.RawRecordCount | Should Be 1
            $one.UniqueRecordCount | Should Be 1
            $one.Records[0].id | Should Be 'synthetic-00000'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'exhausts an exactly-full page and a full final page by requesting the following empty page' {
        $script:syntheticCursors = New-Object System.Collections.Generic.List[object]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $cursorValue = [int]$Query['Cursor']
            $script:syntheticCursors.Add($cursorValue)
            if ($cursorValue -lt 6) {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start $cursorValue -Count 3) }
            }
            return [pscustomobject]@{ items = @() }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-full-pages' -Query @{ Limit = 3; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $true
            $result.PageCount | Should Be 3
            $result.RawRecordCount | Should Be 6
            $result.UniqueRecordCount | Should Be 6
            ($script:syntheticCursors.ToArray() -join ',') | Should Be '0,3,6'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'advances by raw server-clamped page counts and does not treat a short page as terminal' {
        $script:syntheticCursors = New-Object System.Collections.Generic.List[object]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $cursorValue = [int]$Query['Cursor']
            $script:syntheticCursors.Add($cursorValue)
            if ($cursorValue -lt 6) {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start $cursorValue -Count ([Math]::Min(2, 6 - $cursorValue))) }
            }
            return [pscustomobject]@{ items = @() }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-clamped' -Query @{ Limit = 5; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $true
            $result.RawRecordCount | Should Be 6
            $result.UniqueRecordCount | Should Be 6
            ($script:syntheticCursors.ToArray() -join ',') | Should Be '0,2,4,6'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'deduplicates oversized overlapping pages while tracking raw and unique counts separately' {
        $script:syntheticCursors = New-Object System.Collections.Generic.List[object]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $cursorValue = [int]$Query['Cursor']
            $script:syntheticCursors.Add($cursorValue)
            switch ($cursorValue) {
                0 { return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 4) } }
                4 { return [pscustomobject]@{ items = @([pscustomobject]@{ id = 'synthetic-00003'; value = 3 }, [pscustomobject]@{ id = 'synthetic-00004'; value = 4 }, [pscustomobject]@{ id = 'synthetic-00005'; value = 5 }) } }
                default { return [pscustomobject]@{ items = @() } }
            }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-overlap' -Query @{ Limit = 3; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $true
            $result.RawRecordCount | Should Be 7
            $result.UniqueRecordCount | Should Be 6
            $result.DuplicateRecordCount | Should Be 1
            $result.Records.Count | Should Be 6
            ($script:syntheticCursors.ToArray() -join ',') | Should Be '0,4,7'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'honors a nonzero start offset while keeping counts relative to the returned range' {
        $script:syntheticCursors = New-Object System.Collections.Generic.List[object]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $cursorValue = [int]$Query['Cursor']
            $script:syntheticCursors.Add($cursorValue)
            if ($cursorValue -eq 10) { return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 10 -Count 2) } }
            return [pscustomobject]@{ items = @() }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-nonzero' -Query @{ Limit = 8; Cursor = 10 } -CollectRecords
            $result.Complete | Should Be $true
            $result.InitialOffset | Should Be 10
            $result.RawRecordCount | Should Be 2
            $result.UniqueRecordCount | Should Be 2
            ($script:syntheticCursors.ToArray() -join ',') | Should Be '10,12'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'uses validated total and explicit hasMore false as terminal metadata' {
        $script:syntheticCalls = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $script:syntheticCalls++
            [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 3); total = 3 }
        }
        try {
            $totalResult = Invoke-CompleteCollection -Path '/synthetic-total' -Query @{ Limit = 10; Cursor = 0 } -CollectRecords
            $totalResult.Complete | Should Be $true
            $totalResult.TerminationReason | Should Be 'validated_total'
            $script:syntheticCalls | Should Be 1

            $script:syntheticCalls = 0
            $script:PageProvider = {
                param($Path, $Query, $Label, $PageIndex)
                $script:syntheticCalls++
                [pscustomobject]@{ items = @(New-SyntheticRecords -Start 20 -Count 2); hasMore = $false }
            }
            $hasMoreResult = Invoke-CompleteCollection -Path '/synthetic-has-more' -Query @{ Limit = 10; Cursor = 20 } -CollectRecords
            $hasMoreResult.Complete | Should Be $true
            $hasMoreResult.TerminationReason | Should Be 'has_more_false'
            $script:syntheticCalls | Should Be 1
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'gives a changing explicit next token precedence over numeric offset fallback' {
        $script:syntheticRequests = New-Object System.Collections.Generic.List[string]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $requestCursor = [string]$Query['Cursor']
            $script:syntheticRequests.Add($requestCursor)
            if ($requestCursor -eq '0') {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 2); nextCursor = 'synthetic-token-a'; hasMore = $true }
            }
            return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 2 -Count 1); hasMore = $false }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-token' -Query @{ Limit = 10; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $true
            $result.UniqueRecordCount | Should Be 3
            ($script:syntheticRequests.ToArray() -join ',') | Should Be '0,synthetic-token-a'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'accepts an integral primitive continuation token without lossy object coercion' {
        $script:syntheticRequests = New-Object System.Collections.Generic.List[string]
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $requestCursor = [string]$Query['Cursor']
            $script:syntheticRequests.Add($requestCursor)
            if ($PageIndex -eq 0) {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); continuation_token = [int64]7; has_more = $true }
            }
            return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 1 -Count 1); has_more = $false }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-integral-token' -Query @{ Limit = 10; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $true
            $result.UniqueRecordCount | Should Be 2
            ($script:syntheticRequests.ToArray() -join ',') | Should Be '0,7'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'detects a repeated nonempty page without an unbounded loop' {
        $script:syntheticCalls = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $script:syntheticCalls++
            [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 3) }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-repeat' -Query @{ Limit = 3; Cursor = 0 } -SafetyPageCap 100 -CollectRecords
            $result.Complete | Should Be $false
            $result.Status | Should Be 'INCOMPLETE'
            $result.TerminationReason | Should Be 'repeated_page'
            $script:syntheticCalls | Should BeLessThan 3
            $result.RawRecordCount | Should Be 6
            $result.UniqueRecordCount | Should Be 3
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'detects an unchanged explicit token and contradictory terminal metadata' {
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            [pscustomobject]@{ items = @(New-SyntheticRecords -Start $PageIndex -Count 1); next_cursor = 'synthetic-static-token'; has_more = $true }
        }
        try {
            $tokenResult = Invoke-CompleteCollection -Path '/synthetic-static-token' -Query @{ Limit = 3; Cursor = 0 } -CollectRecords
            $tokenResult.Complete | Should Be $false
            $tokenResult.TerminationReason | Should Be 'repeated_cursor'

            $script:PageProvider = {
                param($Path, $Query, $Label, $PageIndex)
                [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); totalCount = 3; hasMore = $false }
            }
            $contradictory = Invoke-CompleteCollection -Path '/synthetic-contradictory' -Query @{ Limit = 3; Cursor = 0 } -CollectRecords
            $contradictory.Complete | Should Be $false
            $contradictory.TerminationReason | Should Be 'contradictory_metadata'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'returns incomplete with a controlled reason after an API error or safety cap' {
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($PageIndex -eq 0) { return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 2) } }
            throw 'synthetic-provider-failure'
        }
        try {
            $failed = Invoke-CompleteCollection -Path '/synthetic-error' -Query @{ Limit = 2; Cursor = 0 } -CollectRecords
            $failed.Complete | Should Be $false
            $failed.TerminationReason | Should Be 'api_error'
            $failed.UniqueRecordCount | Should Be 2

            $script:PageProvider = {
                param($Path, $Query, $Label, $PageIndex)
                [pscustomobject]@{ items = @(New-SyntheticRecords -Start ([int]$Query['Cursor']) -Count 2) }
            }
            $capped = Invoke-CompleteCollection -Path '/synthetic-cap' -Query @{ Limit = 2; Cursor = 0 } -SafetyPageCap 2 -CollectRecords
            $capped.Complete | Should Be $false
            $capped.TerminationReason | Should Be 'safety_page_cap'
            $capped.PageCount | Should Be 2
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'streams 1250 records to a consumer with page-bounded retained record state' {
        $script:syntheticConsumed = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $cursorValue = [int]$Query['Cursor']
            if ($cursorValue -ge 1250) { return [pscustomobject]@{ items = @() } }
            $count = [Math]::Min(137, 1250 - $cursorValue)
            [pscustomobject]@{ items = @(New-SyntheticRecords -Start $cursorValue -Count $count) }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-large' -Query @{ Limit = 500; Cursor = 0 } -OnRecord { param($Record) $script:syntheticConsumed++; 'synthetic-consumer-output' }
            ($result -is [System.Array]) | Should Be $false
            $result.Complete | Should Be $true
            $result.RawRecordCount | Should Be 1250
            $result.UniqueRecordCount | Should Be 1250
            $script:syntheticConsumed | Should Be 1250
            $result.PeakPageRecordCount | Should Be 137
            $result.RetainedRecordCount | Should Be 0
            @($result.Records).Count | Should Be 0
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'marks an empty page with hasMore true as contradictory and incomplete' {
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            [pscustomobject]@{ items = @(); hasMore = $true }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-empty-contradiction' -Query @{ Limit = 4; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $false
            $result.TerminationReason | Should Be 'contradictory_metadata'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'marks malformed or conflicting pagination metadata incomplete and makes the compatibility action fail' {
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); hasMore = 'synthetic-unknown' }
        }
        try {
            $unknown = Invoke-CompleteCollection -Path '/synthetic-unknown-meta' -Query @{ Limit = 4; Cursor = 0 } -CollectRecords
            $unknown.Complete | Should Be $false
            $unknown.TerminationReason | Should Be 'unknown_pagination_metadata'

            $script:PageProvider = {
                param($Path, $Query, $Label, $PageIndex)
                [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); hasMore = $true; has_more = $false }
            }
            $conflict = Invoke-CompleteCollection -Path '/synthetic-conflicting-meta' -Query @{ Limit = 4; Cursor = 0 } -CollectRecords
            $conflict.Complete | Should Be $false
            $conflict.TerminationReason | Should Be 'contradictory_metadata'
            $failureMessage = ''
            try {
                [void](Invoke-AllevaCollection -Path '/synthetic-conflicting-meta' -Query @{ Limit = 4; Cursor = 0 } -Label 'synthetic-conflict')
            } catch {
                $failureMessage = $_.Exception.Message
            }
            $failureMessage | Should Match 'incomplete \(contradictory_metadata\)'
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'rejects array-valued continuation metadata without following it to a false terminal page' {
        $script:syntheticCalls = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $script:syntheticCalls++
            if ($PageIndex -eq 0) {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); nextCursor = @('synthetic-token-a','synthetic-token-b'); hasMore = $true }
            }
            return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 1 -Count 1); hasMore = $false }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-array-token' -Query @{ Limit = 4; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $false
            $result.Status | Should Be 'INCOMPLETE'
            $result.TerminationReason | Should Be 'unknown_pagination_metadata'
            $script:syntheticCalls | Should Be 1
            $result.UniqueRecordCount | Should Be 1
        } finally {
            $script:PageProvider = $null
        }
    }

    It 'rejects object-valued continuation metadata without following it to a false terminal page' {
        $script:syntheticCalls = 0
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            $script:syntheticCalls++
            if ($PageIndex -eq 0) {
                return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 0 -Count 1); continuationToken = [pscustomobject]@{ cursor = 'synthetic-token-object' }; hasMore = $true }
            }
            return [pscustomobject]@{ items = @(New-SyntheticRecords -Start 1 -Count 1); hasMore = $false }
        }
        try {
            $result = Invoke-CompleteCollection -Path '/synthetic-object-token' -Query @{ Limit = 4; Cursor = 0 } -CollectRecords
            $result.Complete | Should Be $false
            $result.Status | Should Be 'INCOMPLETE'
            $result.TerminationReason | Should Be 'unknown_pagination_metadata'
            $script:syntheticCalls | Should Be 1
            $result.UniqueRecordCount | Should Be 1
        } finally {
            $script:PageProvider = $null
        }
    }
}

function Get-ZipEntryText {
    param($Archive, [string]$Name)
    $entry = $Archive.GetEntry($Name)
    if ($null -eq $entry) { return $null }
    $stream = $entry.Open()
    $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8, $true)
    try { return $reader.ReadToEnd() } finally { $reader.Dispose(); $stream.Dispose() }
}

Describe 'Todo 3 dependency-free streaming XLSX writer' {
    It 'converts every Excel column boundary through XFD and rejects out-of-range indexes' {
        $expectedColumns = @(
            [pscustomobject]@{ Index = 1; Name = 'A' },
            [pscustomobject]@{ Index = 26; Name = 'Z' },
            [pscustomobject]@{ Index = 27; Name = 'AA' },
            [pscustomobject]@{ Index = 52; Name = 'AZ' },
            [pscustomobject]@{ Index = 702; Name = 'ZZ' },
            [pscustomobject]@{ Index = 703; Name = 'AAA' },
            [pscustomobject]@{ Index = 16384; Name = 'XFD' }
        )
        foreach ($expected in $expectedColumns) {
            Get-AllevaExcelColumnName -Index $expected.Index | Should Be $expected.Name
        }

        foreach ($invalidIndex in @(0, 16385)) {
            $rangeMessage = ''
            try { [void](Get-AllevaExcelColumnName -Index $invalidIndex) } catch { $rangeMessage = $_.Exception.Message }
            $rangeMessage | Should Not BeNullOrEmpty
        }
    }

    It 'creates a structurally valid navigable OOXML workbook with text-safe cells' {
        $path = Join-Path $TestDrive 'synthetic-navigable.xlsx'
        $result = New-AllevaWorkbook -Path $path `
            -SummaryRows @([pscustomobject]@{ Metric = 'Status'; Value = 'COMPLETE' }) `
            -PatientRosterRows @([pscustomobject]@{
                PatientId = '000012345678901234567890'; ClientFullName = '=SYNTHETIC()';
                LegalFirstName = '+synthetic'; LegalMiddleName = '-synthetic'; LegalLastName = '@synthetic';
                PreferredName = 'Synthetic'; Status = 'active'; DateOfBirth = '2001-02-03'
            }) `
            -PatientFieldRows @([pscustomobject]@{ PatientId = '000012345678901234567890'; FieldPath = 'contact.note'; Value = "synthetic`tvalue"; ChunkIndex = 1; ChunkCount = 1 }) `
            -TreatmentPlanRows @([pscustomobject]@{ TreatmentPlanId = '000000000000000007'; PatientId = '000012345678901234567890'; Status = 'draft'; PlanDate = '2026-07-14' }) `
            -TreatmentPlanFieldRows @([pscustomobject]@{ TreatmentPlanId = '000000000000000007'; PatientId = '000012345678901234567890'; SourceScope = 'detail'; FieldPath = 'goal'; Value = '=1+1'; ChunkIndex = 1; ChunkCount = 1 }) `
            -RetrievalComplete $true -WorksheetRowLimit 100

        (Test-Path -LiteralPath $path -PathType Leaf) | Should Be $true
        $result.Status | Should Be 'COMPLETE'
        $result.WorksheetCount | Should Be 5
        $result.TotalDataRowCount | Should Be 5

        $archive = [System.IO.Compression.ZipFile]::OpenRead($path)
        try {
            foreach ($entryName in @('[Content_Types].xml','_rels/.rels','xl/workbook.xml','xl/_rels/workbook.xml.rels','xl/styles.xml','xl/worksheets/sheet1.xml')) {
                $archive.GetEntry($entryName) | Should Not BeNullOrEmpty
            }
            $workbookXml = Get-ZipEntryText -Archive $archive -Name 'xl/workbook.xml'
            $stylesXml = Get-ZipEntryText -Archive $archive -Name 'xl/styles.xml'
            $worksheetXml = Get-ZipEntryText -Archive $archive -Name 'xl/worksheets/sheet2.xml'
            $workbookXml | Should Match 'Summary'
            $workbookXml | Should Match 'Patient Roster'
            $workbookXml | Should Match 'Patient Fields'
            $workbookXml | Should Match 'Treatment Plans'
            $workbookXml | Should Match 'Treatment Plan Fields 1'
            $stylesXml | Should Match 'cellXfs'
            $worksheetXml | Should Match '<pane[^>]+state="frozen"'
            $worksheetXml | Should Match '<autoFilter'
            $worksheetXml | Should Match 't="inlineStr"'
            $worksheetXml | Should Match '000012345678901234567890'
            $worksheetXml | Should Match '=SYNTHETIC\(\)'
            $worksheetXml | Should Not Match '<f>'
        } finally { $archive.Dispose() }
    }

    It 'splits sheets at the header-aware row threshold and round-trips a 70000-character value in ordered chunks' {
        $path = Join-Path $TestDrive 'synthetic-split.xlsx'
        $longValue = ('A' * 31999) + [char]::ConvertFromUtf32(0x1F600) + ('B' * 32000) + ('C' * 5999)
        $fieldRows = @(
            [pscustomobject]@{ TreatmentPlanId = 'plan-long'; PatientId = 'patient-long'; SourceScope = 'detail'; FieldPath = 'long.value'; Value = $longValue; ChunkIndex = 1; ChunkCount = 1 },
            [pscustomobject]@{ TreatmentPlanId = 'plan-after'; PatientId = 'patient-after'; SourceScope = 'list'; FieldPath = 'after.value'; Value = 'after'; ChunkIndex = 1; ChunkCount = 1 }
        )
        $result = New-AllevaWorkbook -Path $path -SummaryRows @() -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows $fieldRows -RetrievalComplete $true -WorksheetRowLimit 3

        $result.WorksheetCount | Should Be 6
        $result.TotalDataRowCount | Should Be 4
        $result.Sheets[-2].Name | Should Be 'Treatment Plan Fields 1'
        $result.Sheets[-1].Name | Should Be 'Treatment Plan Fields 2'

        $archive = [System.IO.Compression.ZipFile]::OpenRead($path)
        try {
            $allDetailXml = ''
            $valueCells = New-Object System.Collections.Generic.List[string]
            foreach ($sheet in @($result.Sheets | Where-Object { $_.Name -like 'Treatment Plan Fields *' })) {
                $sheetXml = Get-ZipEntryText -Archive $archive -Name $sheet.EntryName
                $allDetailXml += $sheetXml
                $xmlDocument = New-Object System.Xml.XmlDocument
                $xmlDocument.LoadXml($sheetXml)
                $namespace = New-Object System.Xml.XmlNamespaceManager($xmlDocument.NameTable)
                $namespace.AddNamespace('x','http://schemas.openxmlformats.org/spreadsheetml/2006/main')
                $headerCells = @($xmlDocument.SelectNodes('//x:row[@r="1"]/x:c/x:is/x:t', $namespace))
                $valueColumn = 0
                for ($headerIndex = 0; $headerIndex -lt $headerCells.Count; $headerIndex++) {
                    if ($headerCells[$headerIndex].InnerText -eq 'Value') { $valueColumn = $headerIndex + 1; break }
                }
                $valueColumn | Should BeGreaterThan 0
                foreach ($node in @($xmlDocument.SelectNodes(("//x:row[@r!='1']/x:c[{0}]/x:is/x:t" -f $valueColumn), $namespace))) {
                    $valueCells.Add($node.InnerText)
                }
                $sheetXml | Should Match '<pane[^>]+state="frozen"'
                $sheetXml | Should Match '<autoFilter'
            }
            ($valueCells.ToArray()[0..2] | ForEach-Object { $_.Length } | Measure-Object -Sum).Sum | Should Be 70000
            ($valueCells.ToArray()[0..2] -join '') | Should Be $longValue
            foreach ($valueCell in $valueCells.ToArray()) { $valueCell.Length | Should BeLessThan 32001 }
            $allDetailXml | Should Match '>1</t>'
            $allDetailXml | Should Match '>3</t>'
        } finally { $archive.Dispose() }
    }

    It 'streams a large synthetic row provider without retaining workbook rows' {
        $path = Join-Path $TestDrive 'synthetic-stream.xlsx'
        $script:syntheticRowsEmitted = 0
        $provider = {
            param($Emit)
            for ($index = 0; $index -lt 5000; $index++) {
                & $Emit ([pscustomobject]@{ TreatmentPlanId = "plan-$index"; PatientId = "patient-$index"; SourceScope = 'detail'; FieldPath = 'value'; Value = "v$index"; ChunkIndex = 1; ChunkCount = 1 })
                $script:syntheticRowsEmitted++
            }
        }
        $result = New-AllevaWorkbook -Path $path -SummaryRows @() -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows $provider -RetrievalComplete $true -WorksheetRowLimit 1048576

        $script:syntheticRowsEmitted | Should Be 5000
        $result.TotalDataRowCount | Should Be 5000
        $result.RetainedRowCount | Should Be 0
        (Get-Item -LiteralPath $path).Length | Should BeGreaterThan 1000
    }

    It 'sanitizes invalid XML control characters without formula or XML injection' {
        $path = Join-Path $TestDrive 'synthetic-controls.xlsx'
        $controlValue = "safe$([char]1)<tag>&done"
        [void](New-AllevaWorkbook -Path $path -SummaryRows @([pscustomobject]@{ Metric = 'Control'; Value = $controlValue }) -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows @() -RetrievalComplete $true -WorksheetRowLimit 100)
        $archive = [System.IO.Compression.ZipFile]::OpenRead($path)
        try {
            $xml = Get-ZipEntryText -Archive $archive -Name 'xl/worksheets/sheet1.xml'
            $xml | Should Match 'safe\\u0001&lt;tag&gt;&amp;done'
            { [xml]$xml } | Should Not Throw
        } finally { $archive.Dispose() }
    }

    It 'marks incomplete retrieval and never publishes a new workbook on injected write and close failures' {
        $incompletePath = Join-Path $TestDrive 'synthetic-incomplete.xlsx'
        $incompleteResult = New-AllevaWorkbook -Path $incompletePath -SummaryRows @([pscustomobject]@{ Metric='Status'; Value='COMPLETE' }) -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows @() -RetrievalComplete $false -WorksheetRowLimit 100
        $incompleteResult.Status | Should Be 'INCOMPLETE'
        (Test-Path -LiteralPath $incompletePath) | Should Be $true
        $incompleteArchive = [System.IO.Compression.ZipFile]::OpenRead($incompletePath)
        try {
            $incompleteSummaryXml = Get-ZipEntryText -Archive $incompleteArchive -Name 'xl/worksheets/sheet1.xml'
            $incompleteSummaryXml | Should Match 'INCOMPLETE'
            $incompleteSummaryXml | Should Not Match '>COMPLETE</t>'
        } finally { $incompleteArchive.Dispose() }

        foreach ($stage in @('Workbook.BeforeCreate','Workbook.AfterWorksheets','Workbook.BeforeClose','Workbook.BeforeValidate')) {
            $path = Join-Path $TestDrive ("synthetic-failure-{0}.xlsx" -f ($stage -replace '[^A-Za-z]',''))
            $script:FailureHook = { param($actualStage) if ($actualStage -eq $stage) { throw "synthetic-failure:$actualStage" } }.GetNewClosure()
            try {
                $failureMessage = ''
                try {
                    [void](New-AllevaWorkbook -Path $path -SummaryRows @([pscustomobject]@{ Metric='Status'; Value='COMPLETE' }) -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows @() -RetrievalComplete $true -WorksheetRowLimit 100)
                } catch { $failureMessage = $_.Exception.Message }
                $failureMessage | Should Match ('synthetic-failure:{0}' -f ([regex]::Escape($stage)))
                (Test-Path -LiteralPath $path) | Should Be $false
                @(Get-ChildItem -LiteralPath $TestDrive -Filter '*.tmp' -File).Count | Should Be 0
            } finally { $script:FailureHook = $null }
        }

        $stablePath = Join-Path $TestDrive 'synthetic-existing.xlsx'
        [void](New-AllevaWorkbook -Path $stablePath -SummaryRows @([pscustomobject]@{ Metric='Status'; Value='ORIGINAL' }) -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows @() -RetrievalComplete $true -WorksheetRowLimit 100)
        $originalHash = (Get-FileHash -LiteralPath $stablePath -Algorithm SHA256).Hash
        $script:FailureHook = { param($actualStage) if ($actualStage -eq 'Workbook.BeforePublish') { throw 'synthetic-before-publish' } }
        try {
            $replaceMessage = ''
            try {
                [void](New-AllevaWorkbook -Path $stablePath -SummaryRows @([pscustomobject]@{ Metric='Status'; Value='REPLACEMENT' }) -PatientRosterRows @() -PatientFieldRows @() -TreatmentPlanRows @() -TreatmentPlanFieldRows @() -RetrievalComplete $true -WorksheetRowLimit 100)
            } catch { $replaceMessage = $_.Exception.Message }
            $replaceMessage | Should Match 'synthetic-before-publish'
            (Get-FileHash -LiteralPath $stablePath -Algorithm SHA256).Hash | Should Be $originalHash
            @(Get-ChildItem -LiteralPath $TestDrive -File | Where-Object { $_.Extension -in @('.tmp','.bak') }).Count | Should Be 0
        } finally { $script:FailureHook = $null }
    }
}

function New-SyntheticRequestException {
    param(
        [int]$StatusCode = 0,
        [string]$RetryAfter = '',
        [string]$ErrorCategory = 'SyntheticRequestFailure'
    )

    $exception = New-Object System.Exception('synthetic-request-failure')
    $exception.Data['StatusCode'] = $StatusCode
    $exception.Data['RetryAfter'] = $RetryAfter
    $exception.Data['ErrorCategory'] = $ErrorCategory
    return $exception
}

function Get-SyntheticWorkbookXmlText {
    param([Parameter(Mandatory=$true)][string]$Path)

    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        $builder = New-Object System.Text.StringBuilder
        foreach ($entry in @($archive.Entries | Where-Object { $_.FullName -like 'xl/worksheets/*.xml' })) {
            [void]$builder.Append((Get-ZipEntryText -Archive $archive -Name $entry.FullName))
        }
        return $builder.ToString()
    } finally {
        $archive.Dispose()
    }
}

function Get-SyntheticWorksheetTable {
    param(
        [Parameter(Mandatory=$true)][string]$Path,
        [Parameter(Mandatory=$true)][int]$SheetNumber
    )

    $archive = [System.IO.Compression.ZipFile]::OpenRead($Path)
    try {
        [xml]$document = Get-ZipEntryText -Archive $archive -Name ("xl/worksheets/sheet{0}.xml" -f $SheetNumber)
        $namespaces = New-Object System.Xml.XmlNamespaceManager($document.NameTable)
        $namespaces.AddNamespace('s', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main')
        $xmlRows = @($document.SelectNodes('//s:sheetData/s:row', $namespaces))
        if ($xmlRows.Count -eq 0) { return @() }

        $headers = New-Object System.Collections.Generic.List[string]
        foreach ($cell in @($xmlRows[0].SelectNodes('s:c', $namespaces))) {
            $textNode = $cell.SelectSingleNode('s:is/s:t', $namespaces)
            $headers.Add($(if ($null -eq $textNode) { '' } else { [string]$textNode.InnerText }))
        }

        $rows = New-Object System.Collections.Generic.List[object]
        for ($rowIndex = 1; $rowIndex -lt $xmlRows.Count; $rowIndex++) {
            $cells = @($xmlRows[$rowIndex].SelectNodes('s:c', $namespaces))
            $values = [ordered]@{}
            for ($columnIndex = 0; $columnIndex -lt $headers.Count; $columnIndex++) {
                $text = ''
                if ($columnIndex -lt $cells.Count) {
                    $textNode = $cells[$columnIndex].SelectSingleNode('s:is/s:t', $namespaces)
                    if ($null -ne $textNode) { $text = [string]$textNode.InnerText }
                }
                $values[$headers[$columnIndex]] = $text
            }
            $rows.Add([pscustomobject]$values)
        }
        return $rows.ToArray()
    } finally {
        $archive.Dispose()
    }
}

Describe 'Todo 4 complete roster and treatment-plan export integration' {
    It 'exports every patient leaf, all five exact name columns, and distinct list/detail treatment-plan scopes' {
        $outputRoot = Join-Path $TestDrive 'complete-export'
        $script:ExportDirectory = $outputRoot
        $script:Settings = Get-DefaultSettings
        $longFirst = 'SyntheticFirst-' + ('F' * 140)
        $longMiddle = 'SyntheticMiddle-' + ('M' * 120)
        $longLast = 'SyntheticLast-' + ('L' * 150)
        $longPreferred = 'SyntheticPreferred-' + ('P' * 130)
        $longFull = "$longFirst $longMiddle $longLast"
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') {
                return [pscustomobject]@{ items = @(
                    [pscustomobject]@{
                        id = 'patient-synthetic-001'
                        name = [pscustomobject]@{
                            clientFullName = $longFull
                            first = $longFirst
                            middle = $longMiddle
                            last = $longLast
                            preferred = $longPreferred
                        }
                        status = [pscustomobject]@{ id = '1049'; label = 'Active' }
                        dateOfBirth = '2001-02-03'
                        unknownPatientBranch = [pscustomobject]@{ nestedLeaf = 'patient-unknown-leaf' }
                    }
                ); hasMore = $false }
            }
            if ($Path -eq '/treatment-plans') {
                return [pscustomobject]@{ items = @(
                    [pscustomobject]@{
                        id = 'plan-synthetic-001'
                        clientId = 'patient-synthetic-001'
                        status = 'draft'
                        planDate = '2026-07-14'
                        listOnly = [pscustomobject]@{ nestedLeaf = 'list-only-leaf' }
                    }
                ); hasMore = $false }
            }
            throw 'unexpected-synthetic-path'
        }.GetNewClosure()
        $script:DetailProvider = {
            param($Path, $Query, $Label, $PlanId, $Attempt)
            [pscustomobject]@{
                id = $PlanId
                clientId = 'patient-synthetic-001'
                detailOnly = [pscustomobject]@{
                    nestedLeaf = 'detail-only-leaf'
                    hostile = '=SYNTHETIC_FORMULA()'
                    control = "safe$([char]1)value"
                    longValue = ('Z' * 70000)
                }
            }
        }
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) throw 'delay-was-not-expected' }

        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'COMPLETE'
            $result.PatientCount | Should Be 1
            $result.TreatmentPlanCount | Should Be 1
            $result.DetailSuccessCount | Should Be 1
            $result.DetailFailureCount | Should Be 0
            $result.MappingMissCount | Should Be 0
            $result.PatientFieldLeafCount | Should BeGreaterThan 7
            $result.TreatmentPlanListFieldLeafCount | Should BeGreaterThan 4
            $result.TreatmentPlanDetailFieldLeafCount | Should BeGreaterThan 5
            (Test-Path -LiteralPath $result.WorkbookPath -PathType Leaf) | Should Be $true
            $result.Workbook.TotalDataRowCount | Should Be $result.WorkbookDataRowCountExpected
            $result.Workbook.WorksheetCount | Should Be $result.WorkbookWorksheetCountExpected
            [IO.Path]::GetFileName($result.WorkbookPath) | Should Match '^alleva-complete-export-\d{8}-\d{6}-\d{3}-[0-9a-f]{8}-COMPLETE\.xlsx$'
            [IO.Path]::GetFileName($result.WorkbookPath) | Should Not Match 'patient|plan-synthetic'
            @(Get-ChildItem -LiteralPath $outputRoot -Filter '*.spool' -File -Force).Count | Should Be 0

            $xml = Get-SyntheticWorkbookXmlText -Path $result.WorkbookPath
            foreach ($value in @($longFull,$longFirst,$longMiddle,$longLast,$longPreferred,'patient-unknown-leaf','list-only-leaf','detail-only-leaf','list','detail')) {
                $xml | Should Match ([regex]::Escape($value))
            }
            $xml | Should Not Match '<f>'
            $xml | Should Match 'safe\\u0001value'
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
            $script:RetryDelayProvider = $null
        }
    }

    It 'links list and detail treatment-plan rows to exact roster names without guessing unknown patients' {
        $outputRoot = Join-Path $TestDrive 'patient-name-linkage'
        $script:ExportDirectory = $outputRoot
        $script:Settings = Get-DefaultSettings
        $nestedNames = [ordered]@{
            ClientFullName = 'Nested Shape Full Name'
            LegalFirstName = 'NestedFirst'
            LegalMiddleName = 'NestedMiddle'
            LegalLastName = 'NestedLast'
            PreferredName = 'NestedPreferred'
        }
        $flatNames = [ordered]@{
            ClientFullName = 'Flat Shape Full Name'
            LegalFirstName = 'FlatFirst'
            LegalMiddleName = 'FlatMiddle'
            LegalLastName = 'FlatLast'
            PreferredName = 'FlatPreferred'
        }
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') {
                return [pscustomobject]@{ items=@(
                    [pscustomobject]@{ id='patient-nested-shape'; name=[pscustomobject]@{
                        clientFullName=$nestedNames.ClientFullName; legalFirstName=$nestedNames.LegalFirstName;
                        legalMiddleName=$nestedNames.LegalMiddleName; legalLastName=$nestedNames.LegalLastName;
                        preferredName=$nestedNames.PreferredName
                    } },
                    [pscustomobject]@{ id='patient-flat-shape'; clientFullName=$flatNames.ClientFullName;
                        legalFirstName=$flatNames.LegalFirstName; legalMiddleName=$flatNames.LegalMiddleName;
                        legalLastName=$flatNames.LegalLastName; preferredName=$flatNames.PreferredName }
                ); hasMore=$false }
            }
            return [pscustomobject]@{ items=@(
                [pscustomobject]@{ id='plan-nested-shape'; clientId='patient-nested-shape'; listMarker='nested-list' },
                [pscustomobject]@{ id='plan-flat-shape'; clientId='patient-flat-shape'; listMarker='flat-list' },
                [pscustomobject]@{ id='plan-unknown-patient'; clientId='patient-unknown-shape'; listMarker='unknown-list' }
            ); hasMore=$false }
        }.GetNewClosure()
        $script:DetailProvider = {
            param($Path, $Query, $Label, $PlanId, $Attempt)
            [pscustomobject]@{ id=$PlanId; detailMarker=("detail-{0}" -f $PlanId) }
        }
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) throw 'delay-was-not-expected' }

        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.MappingMissCount | Should Be 1

            $planRows = @(Get-SyntheticWorksheetTable -Path $result.WorkbookPath -SheetNumber 4)
            $fieldRows = @(Get-SyntheticWorksheetTable -Path $result.WorkbookPath -SheetNumber 5)
            foreach ($column in @('PatientMappingStatus','ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName')) {
                (@($planRows[0].PSObject.Properties.Name) -contains $column) | Should Be $true
                (@($fieldRows[0].PSObject.Properties.Name) -contains $column) | Should Be $true
            }

            foreach ($case in @(
                [pscustomobject]@{ PlanId='plan-nested-shape'; PatientId='patient-nested-shape'; Names=$nestedNames },
                [pscustomobject]@{ PlanId='plan-flat-shape'; PatientId='patient-flat-shape'; Names=$flatNames }
            )) {
                $planRow = @($planRows | Where-Object { $_.TreatmentPlanId -eq $case.PlanId })[0]
                $planRow.PatientId | Should Be $case.PatientId
                $planRow.PatientMappingStatus | Should Be 'MAPPED'
                foreach ($nameColumn in @('ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName')) {
                    $planRow.$nameColumn | Should Be $case.Names[$nameColumn]
                }

                $linkedFields = @($fieldRows | Where-Object { $_.TreatmentPlanId -eq $case.PlanId })
                (@($linkedFields.SourceScope | Select-Object -Unique) -contains 'list') | Should Be $true
                (@($linkedFields.SourceScope | Select-Object -Unique) -contains 'detail') | Should Be $true
                foreach ($fieldRow in $linkedFields) {
                    $fieldRow.PatientId | Should Be $case.PatientId
                    $fieldRow.PatientMappingStatus | Should Be 'MAPPED'
                    foreach ($nameColumn in @('ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName')) {
                        $fieldRow.$nameColumn | Should Be $case.Names[$nameColumn]
                    }
                }
            }

            $unknownPlan = @($planRows | Where-Object { $_.TreatmentPlanId -eq 'plan-unknown-patient' })[0]
            $unknownPlan.PatientId | Should Be 'patient-unknown-shape'
            $unknownPlan.PatientMappingStatus | Should Be 'UNMAPPED'
            foreach ($nameColumn in @('ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName')) {
                $unknownPlan.$nameColumn | Should Be ''
            }
            $unknownFields = @($fieldRows | Where-Object { $_.TreatmentPlanId -eq 'plan-unknown-patient' })
            (@($unknownFields.SourceScope | Select-Object -Unique) -contains 'list') | Should Be $true
            (@($unknownFields.SourceScope | Select-Object -Unique) -contains 'detail') | Should Be $true
            foreach ($fieldRow in $unknownFields) {
                $fieldRow.PatientMappingStatus | Should Be 'UNMAPPED'
                foreach ($nameColumn in @('ClientFullName','LegalFirstName','LegalMiddleName','LegalLastName','PreferredName')) {
                    $fieldRow.$nameColumn | Should Be ''
                }
            }

            $outsideWorkbook = ($result | ConvertTo-Json -Depth 10) + [IO.Path]::GetFileName($result.WorkbookPath)
            foreach ($name in @($nestedNames.Values) + @($flatNames.Values)) {
                $outsideWorkbook | Should Not Match ([regex]::Escape([string]$name))
                [IO.Path]::GetFileName($result.WorkbookPath) | Should Not Match ([regex]::Escape([string]$name))
            }
            @(Get-ChildItem -LiteralPath $outputRoot -Filter '*.spool' -File -Force).Count | Should Be 0
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
            $script:RetryDelayProvider = $null
        }
    }

    It 'retries only timeout, 429, and 5xx with four-attempt and delay caps and no real sleep' {
        $script:Settings = Get-DefaultSettings
        $script:syntheticDetailCalls = 0
        $script:syntheticDelays = New-Object System.Collections.Generic.List[int]
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) $script:syntheticDelays.Add([int]$Seconds) }

        try {
            $script:DetailProvider = {
                param($Path, $Query, $Label, $PlanId, $Attempt)
                $script:syntheticDetailCalls++
                if ($script:syntheticDetailCalls -eq 1) { throw (New-Object System.TimeoutException('synthetic-timeout')) }
                if ($script:syntheticDetailCalls -eq 2) { throw (New-SyntheticRequestException -StatusCode 429 -RetryAfter '999' -ErrorCategory 'Http429') }
                if ($script:syntheticDetailCalls -eq 3) { throw (New-SyntheticRequestException -StatusCode 503 -ErrorCategory 'Http5xx') }
                return [pscustomobject]@{ id = $PlanId; success = $true }
            }
            $retried = Invoke-TreatmentPlanDetailWithRetry -PlanId 'plan-retry-success'
            $retried.Success | Should Be $true
            $retried.AttemptCount | Should Be 4
            $retried.RetryCount | Should Be 3
            $script:syntheticDetailCalls | Should Be 4
            ($script:syntheticDelays.ToArray() -join ',') | Should Be '1,60,4'
            ($script:syntheticDelays | Measure-Object -Sum).Sum | Should BeLessThan 181

            $script:syntheticDetailCalls = 0
            $script:syntheticDelays.Clear()
            $script:DetailProvider = {
                param($Path, $Query, $Label, $PlanId, $Attempt)
                $script:syntheticDetailCalls++
                throw (New-SyntheticRequestException -StatusCode 400 -ErrorCategory 'Http4xx')
            }
            $notRetried = Invoke-TreatmentPlanDetailWithRetry -PlanId 'plan-no-retry'
            $notRetried.Success | Should Be $false
            $notRetried.AttemptCount | Should Be 1
            $notRetried.RetryCount | Should Be 0
            $script:syntheticDetailCalls | Should Be 1
            $script:syntheticDelays.Count | Should Be 0

            $script:syntheticDetailCalls = 0
            $script:syntheticDelays.Clear()
            $script:DetailProvider = {
                param($Path, $Query, $Label, $PlanId, $Attempt)
                $script:syntheticDetailCalls++
                throw (New-SyntheticRequestException -StatusCode 429 -RetryAfter '999' -ErrorCategory 'Http429')
            }
            $exhausted = Invoke-TreatmentPlanDetailWithRetry -PlanId 'plan-retry-exhausted'
            $exhausted.Success | Should Be $false
            $exhausted.AttemptCount | Should Be 4
            $exhausted.RetryCount | Should Be 3
            ($script:syntheticDelays.ToArray() -join ',') | Should Be '60,60,60'
            ($script:syntheticDelays | Measure-Object -Sum).Sum | Should Be 180
        } finally {
            $script:DetailProvider = $null
            $script:RetryDelayProvider = $null
        }
    }

    It 'publishes an explicitly INCOMPLETE workbook and preserves partial rows when pagination or detail fails' {
        $outputRoot = Join-Path $TestDrive 'incomplete-export'
        $script:ExportDirectory = $outputRoot
        $script:Settings = Get-DefaultSettings
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') {
                if ($PageIndex -eq 0) {
                    return [pscustomobject]@{ items = @([pscustomobject]@{ id='patient-partial'; name=[pscustomobject]@{ clientFullName='Synthetic Partial'; first='Synthetic'; last='Partial' } }) }
                }
                throw 'synthetic-roster-page-failure'
            }
            return [pscustomobject]@{ items = @(
                [pscustomobject]@{ id='plan-mapped'; clientId='patient-partial'; listOnly='preserved-list' },
                [pscustomobject]@{ id='plan-unmapped'; clientId='patient-not-in-roster'; listOnly='unmapped-list' },
                [pscustomobject]@{ clientId='patient-partial'; listOnly='missing-id-list' }
            ); hasMore=$false }
        }
        $script:DetailProvider = {
            param($Path, $Query, $Label, $PlanId, $Attempt)
            if ($PlanId -eq 'plan-mapped') { return [pscustomobject]@{ id=$PlanId; detail='mapped-detail' } }
            throw (New-SyntheticRequestException -StatusCode 404 -ErrorCategory 'Http4xx')
        }
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) throw 'delay-was-not-expected' }

        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.PatientCollectionComplete | Should Be $false
            $result.DetailSuccessCount | Should Be 1
            $result.DetailFailureCount | Should Be 1
            $result.MissingPlanIdCount | Should Be 1
            $result.MappingMissCount | Should Be 1
            $result.Workbook.TotalDataRowCount | Should Be $result.WorkbookDataRowCountExpected
            $result.Workbook.WorksheetCount | Should Be $result.WorkbookWorksheetCountExpected
            [IO.Path]::GetFileName($result.WorkbookPath) | Should Match '-INCOMPLETE\.xlsx$'
            [IO.Path]::GetFileName($result.WorkbookPath) | Should Not Match '-COMPLETE\.xlsx$'
            $xml = Get-SyntheticWorkbookXmlText -Path $result.WorkbookPath
            $xml | Should Match 'INCOMPLETE'
            $xml | Should Match 'preserved-list'
            $xml | Should Match 'mapped-detail'
            $xml | Should Match 'unmapped-list'
            @(Get-ChildItem -LiteralPath $outputRoot -Filter '*.spool' -File -Force).Count | Should Be 0
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
            $script:RetryDelayProvider = $null
        }
    }

    It 'writes allowlisted event logs only, creates no transcript, and leaves settings bytes unchanged' {
        $root = Join-Path $TestDrive 'privacy-export'
        $script:ExportDirectory = Join-Path $root 'exports'
        $script:LogDirectory = Join-Path $root 'logs'
        $script:SettingsPath = Join-Path $root 'synthetic-settings.json'
        Ensure-Directory -Path $root
        $settingsText = '{"Limit":5,"ClientId":"SECRET_CLIENT_CANARY","ClientSecretProtected":"SECRET_TOKEN_CANARY"}'
        $settingsText | Set-Content -LiteralPath $script:SettingsPath -Encoding UTF8
        Import-Settings
        $beforeHash = (Get-FileHash -LiteralPath $script:SettingsPath -Algorithm SHA256).Hash
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='PATIENT_ID_CANARY'; name=[pscustomobject]@{ clientFullName='PATIENT_NAME_CANARY'; first='PATIENT_FIRST_CANARY'; last='PATIENT_LAST_CANARY' }; privateValue='PATIENT_VALUE_CANARY' }); hasMore=$false } }
            return [pscustomobject]@{ items=@([pscustomobject]@{ id='PLAN_ID_CANARY'; clientId='PATIENT_ID_CANARY'; queryCanary='QUERY_BODY_CANARY' }); hasMore=$false }
        }
        $script:DetailProvider = { param($Path, $Query, $Label, $PlanId, $Attempt) [pscustomobject]@{ id=$PlanId; detail='DETAIL_VALUE_CANARY' } }
        $script:RetryDelayProvider = { param($Seconds, $Reason, $Attempt) }

        try {
            Initialize-Logging
            $result = Invoke-CompleteAllevaExport
            Stop-Logging
            $result.Status | Should Be 'COMPLETE'
            (Get-FileHash -LiteralPath $script:SettingsPath -Algorithm SHA256).Hash | Should Be $beforeHash
            @(Get-ChildItem -LiteralPath $script:LogDirectory -Recurse -Filter '*transcript*' -File).Count | Should Be 0
            $logFiles = @(Get-ChildItem -LiteralPath $script:LogDirectory -Recurse -Filter '*.ndjson' -File)
            $logFiles.Count | Should Be 1
            $logText = Get-Content -LiteralPath $logFiles[0].FullName -Raw
            foreach ($canary in @('SECRET_CLIENT_CANARY','SECRET_TOKEN_CANARY','PATIENT_ID_CANARY','PATIENT_NAME_CANARY','PATIENT_FIRST_CANARY','PATIENT_LAST_CANARY','PATIENT_VALUE_CANARY','PLAN_ID_CANARY','QUERY_BODY_CANARY','DETAIL_VALUE_CANARY',[Environment]::UserName,[Environment]::MachineName,$root)) {
                if (-not [string]::IsNullOrWhiteSpace([string]$canary)) { $logText | Should Not Match ([regex]::Escape([string]$canary)) }
            }
            foreach ($line in @(Get-Content -LiteralPath $logFiles[0].FullName)) {
                if ([string]::IsNullOrWhiteSpace($line)) { continue }
                $entry = $line | ConvertFrom-Json
                foreach ($name in @($entry.PSObject.Properties.Name)) {
                    (@('timestamp','level','event','action','endpoint_label','status','duration_ms','page_count','raw_count','unique_count','duplicate_count','retry_count','attempt_count','record_count','total_count','active_count','detail_success_count','detail_failure_count','mapping_miss_count','worksheet_count','row_count','error_class','termination_reason','complete') -contains $name) | Should Be $true
                }
            }
        } finally {
            if (-not [string]::IsNullOrWhiteSpace([string]$script:EventLogPath)) { Stop-Logging }
            $script:PageProvider = $null
            $script:DetailProvider = $null
            $script:RetryDelayProvider = $null
        }
    }

    It 'handles a 1250-patient roster and produces a complete workbook through the real CMD self-test surface' {
        $script:ExportDirectory = Join-Path $TestDrive 'large-export'
        $script:SettingsPath = Join-Path $TestDrive 'large-settings.json'
        $script:Settings = Get-DefaultSettings
        $script:Settings['MaxPages'] = 20
        Save-Settings
        $script:PageProvider = {
            param($Path, $Query, $Label, $PageIndex)
            if ($Path -eq '/clients') {
                $cursor = [int]$Query['Cursor']
                if ($cursor -ge 1250) { return [pscustomobject]@{ items=@() } }
                $count = [Math]::Min(137, 1250 - $cursor)
                $items = New-Object System.Collections.Generic.List[object]
                for ($index = 0; $index -lt $count; $index++) {
                    $number = $cursor + $index
                    $items.Add([pscustomobject]@{ id="patient-large-$number"; name=[pscustomobject]@{ clientFullName="Synthetic Person $number"; first='Synthetic'; last="Person$number" } })
                }
                return [pscustomobject]@{ items=$items.ToArray() }
            }
            return [pscustomobject]@{ items=@(); hasMore=$false }
        }
        $script:DetailProvider = { param($Path, $Query, $Label, $PlanId, $Attempt) throw 'detail-was-not-expected' }
        try {
            $large = Invoke-CompleteAllevaExport
            $large.Status | Should Be 'COMPLETE'
            $large.PatientCount | Should Be 1250
            $large.PatientCollectionPageCount | Should BeGreaterThan 9
            $large.TreatmentPlanCount | Should Be 0
            $large.Workbook.RetainedRowCount | Should Be 0
            $large.Workbook.TotalDataRowCount | Should Be $large.WorkbookDataRowCountExpected
            @(Get-ChildItem -LiteralPath $script:ExportDirectory -Filter '*.spool' -File -Force).Count | Should Be 0
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
        }

        $cmdPath = Join-Path $repoRoot 'diag-build-tools\Run-AllevaEndUserTools.cmd'
        $cmdOutput = Join-Path $TestDrive 'cmd-complete-export'
        $cmdLogs = Join-Path $TestDrive 'cmd-complete-logs'
        $cmdSettings = Join-Path $TestDrive 'cmd-missing-settings.json'
        $cmdStdout = Join-Path $TestDrive 'cmd-complete-stdout.txt'
        $cmdStderr = Join-Path $TestDrive 'cmd-complete-stderr.txt'
        $arguments = ('/d /c call "{0}" -Action SelfTest -NoPause -ExportDirectory "{1}" -LogDirectory "{2}" -SettingsPath "{3}"' -f $cmdPath,$cmdOutput,$cmdLogs,$cmdSettings)
        $process = Start-Process -FilePath 'cmd.exe' -ArgumentList $arguments -PassThru -Wait -NoNewWindow -RedirectStandardOutput $cmdStdout -RedirectStandardError $cmdStderr
        $process.ExitCode | Should Be 0
        @(Get-ChildItem -LiteralPath $cmdOutput -Filter '*-COMPLETE.xlsx' -File).Count | Should Be 1
        @(Get-ChildItem -LiteralPath $cmdOutput -Filter '*-INCOMPLETE.xlsx' -File).Count | Should Be 0
    }

    It 'returns exit 1 without hanging when the CMD launcher is copied without its PowerShell script' {
        $sourceCmd = Join-Path $repoRoot 'diag-build-tools\Run-AllevaEndUserTools.cmd'
        $isolatedRoot = Join-Path $TestDrive 'isolated launcher path with spaces'
        New-Item -ItemType Directory -Path $isolatedRoot -Force | Out-Null
        $isolatedCmd = Join-Path $isolatedRoot 'Run-AllevaEndUserTools.cmd'
        Copy-Item -LiteralPath $sourceCmd -Destination $isolatedCmd

        $startInfo = New-Object System.Diagnostics.ProcessStartInfo
        $startInfo.FileName = 'cmd.exe'
        $startInfo.Arguments = ('/d /c call "{0}" -Action SelfTest -NoPause' -f $isolatedCmd)
        $startInfo.UseShellExecute = $false
        $startInfo.CreateNoWindow = $true
        $startInfo.RedirectStandardOutput = $true
        $startInfo.RedirectStandardError = $true
        $process = New-Object System.Diagnostics.Process
        $process.StartInfo = $startInfo
        [void]$process.Start()
        $stdoutTask = $process.StandardOutput.ReadToEndAsync()
        $stderrTask = $process.StandardError.ReadToEndAsync()
        $completed = $process.WaitForExit(10000)
        if (-not $completed) { $process.Kill(); $process.WaitForExit() }
        $stdout = $stdoutTask.Result
        [void]$stderrTask.Result

        $completed | Should Be $true
        $process.ExitCode | Should Be 1
        $stdout | Should Match 'Could not find the PowerShell script'
        $stdout | Should Not Match 'Tool closed normally'
    }
}

Describe 'Final review remediation contracts' {
    BeforeEach {
        $script:Settings = Get-DefaultSettings
        $script:Settings['ApiVersion'] = 'synthetic-v1'
        $script:RetryDelayProvider = { param($Seconds) }
    }

    AfterEach {
        $script:DetailProvider = $null
        $script:RetryDelayProvider = $null
    }

    It 'bounds configured export pagination and always starts complete exports at cursor zero' {
        $script:Settings['Cursor'] = 900
        $script:Settings['MaxPages'] = 3
        $query = Get-CompleteExportQuery
        $query.Cursor | Should Be 0
        (Get-AllevaConfiguredPageCap) | Should Be 3
    }

    It 'marks page-cap exhaustion incomplete while both export collections ignore a saved nonzero cursor' {
        $script:ExportDirectory = Join-Path $TestDrive 'page-cap'
        $script:SettingsPath = Join-Path $TestDrive 'page-cap-settings.json'
        $script:Settings['Cursor'] = 77
        $script:Settings['MaxPages'] = 1
        Save-Settings
        $script:seenExportQueries = New-Object System.Collections.Generic.List[string]
        $script:PageProvider = {
            param($Path, $Query)
            $script:seenExportQueries.Add("${Path}:$($Query['Cursor'])")
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='patient-cap'; name='Synthetic Cap' }) } }
            return [pscustomobject]@{ items=@(); hasMore=$false }
        }
        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.PatientCollectionComplete | Should Be $false
            ($script:seenExportQueries.ToArray() -join ',') | Should Be '/clients:0,/treatment-plans:0'
        } finally { $script:PageProvider = $null }
    }

    It 'retries only timeouts, 429, and 500 through 599' {
        foreach ($status in @(500, 599)) {
            $exception = New-Object System.Exception('synthetic')
            $exception.Data['StatusCode'] = $status
            (Get-AllevaDetailFailureInfo ([System.Management.Automation.ErrorRecord]::new($exception, 'synthetic', 'NotSpecified', $null))).Retryable | Should Be $true
        }
        foreach ($status in @(400, 499, 600, 999)) {
            $exception = New-Object System.Exception('synthetic')
            $exception.Data['StatusCode'] = $status
            (Get-AllevaDetailFailureInfo ([System.Management.Automation.ErrorRecord]::new($exception, 'synthetic', 'NotSpecified', $null))).Retryable | Should Be $false
        }
    }

    It 'parses hostile Retry-After values without overflow and caps them at sixty seconds' {
        (Get-AllevaRetryAfterSeconds ('9' * 500)) | Should Be 60
        (Get-AllevaRetryAfterSeconds '999999999999999999999999') | Should Be 60
        { Get-AllevaRetryAfterSeconds 'Fri, 31 Dec 9999 23:59:59 GMT' } | Should Not Throw
        (Get-AllevaRetryAfterSeconds 'Fri, 31 Dec 9999 23:59:59 GMT') | Should Be 60
    }

    It 'URI-escapes treatment-plan identifiers before requesting detail' {
        $script:capturedDetailPath = ''
        $script:DetailProvider = {
            param($Path)
            $script:capturedDetailPath = $Path
            return [pscustomobject]@{ id='plan /?#%'; patientId='patient-1' }
        }
        $result = Invoke-TreatmentPlanDetailWithRetry -PlanId 'plan /?#%'
        $result.Success | Should Be $true
        $script:capturedDetailPath | Should Be '/treatment-plans/plan%20%2F%3F%23%25'
    }

    It 'uses collision-resistant export names that contain no patient-supplied base name' {
        $one = New-AllevaExportFileName -Kind 'focused-csv' -Extension '.csv'
        $two = New-AllevaExportFileName -Kind 'focused-csv' -Extension '.csv'
        $one | Should Not Be $two
        $one | Should Match '^alleva-focused-csv-[0-9]{8}-[0-9]{6}-[0-9]{3}-[0-9a-f]{8}\.csv$'
    }

    It 'protects CSV cells from formula execution and excludes focused identifiers from filenames' {
        $script:ExportDirectory = Join-Path $TestDrive 'csv'
        $script:Settings['WriteRawJsonCompanion'] = $false
        $record = [pscustomobject][ordered]@{ PatientId='private-patient'; Value='=HYPERLINK("https://example.invalid")'; Plus='+1'; Minus='-1'; At='@x'; '=RemoteHeader'='safe'; '+RemoteHeader'='safe'; '-RemoteHeader'='safe'; '@RemoteHeader'='safe' }
        $path = Export-FlattenedCsv -Records @($record) -BaseName 'private-patient'
        [IO.Path]::GetFileName($path) | Should Not Match 'private-patient'
        $text = Get-Content -LiteralPath $path -Raw
        $text | Should Match "'=HYPERLINK"
        $text | Should Match "'\+1"
        $text | Should Match "'-1"
        $text | Should Match "'@x"
        $header = Get-Content -LiteralPath $path -First 1
        $header | Should Match "'=RemoteHeader"
        $header | Should Match "'\+RemoteHeader"
        $header | Should Match "'-RemoteHeader"
        $header | Should Match "'@RemoteHeader"
    }

    It 'stores the entire settings payload in a DPAPI envelope and migrates legacy plaintext' {
        $script:SettingsPath = Join-Path $TestDrive 'legacy-settings.json'
        $legacy = '{"AllevaApiBaseUrl":"https://secret-host.invalid/private","AllevaTokenUrl":"https://token.invalid/private","ClientId":"CLIENT_CANARY","Scope":"SCOPE_CANARY","Limit":37}'
        [IO.File]::WriteAllText($script:SettingsPath, $legacy, (New-Object Text.UTF8Encoding($false)))
        Import-Settings
        $script:Settings['ClientId'] | Should Be 'CLIENT_CANARY'
        $raw = [IO.File]::ReadAllText($script:SettingsPath)
        $raw | Should Match 'R3-ALLEVA-DPAPI-SETTINGS-V1'
        $raw | Should Not Match 'CLIENT_CANARY|secret-host|token.invalid|SCOPE_CANARY'
        Import-Settings
        $script:Settings['AllevaApiBaseUrl'] | Should Be 'https://secret-host.invalid/private'
        $display = (& { Show-Settings } 6>&1 | Out-String)
        $display | Should Not Match 'CLIENT_CANARY|secret-host|token.invalid|SCOPE_CANARY'
        @(Get-ChildItem -LiteralPath $TestDrive -File -Force | Where-Object { $_.Name -like '.legacy-settings.json.*' }).Count | Should Be 0
    }

    It 'fails closed for unknown settings envelopes and leaves no plaintext migration duplicate on publication failure' {
        $script:SettingsPath = Join-Path $TestDrive 'unknown-settings.json'
        $unknown = '{"Format":"R3-UNKNOWN-FUTURE","ProtectedPayload":"opaque","ClientId":"UNKNOWN_CANARY"}'
        [IO.File]::WriteAllText($script:SettingsPath, $unknown, (New-Object Text.UTF8Encoding($false)))
        Import-Settings
        [IO.File]::ReadAllText($script:SettingsPath) | Should Be $unknown
        $script:Settings['ClientId'] | Should Be ''

        $script:SettingsPath = Join-Path $TestDrive 'failed-migration.json'
        $legacy = '{"ClientId":"LEGACY_ONLY_CANARY","Limit":41}'
        [IO.File]::WriteAllText($script:SettingsPath, $legacy, (New-Object Text.UTF8Encoding($false)))
        $script:FailureHook = { param($Stage) if ($Stage -eq 'Settings.BeforePublish') { throw 'synthetic-settings-publish-failure' } }
        try { Import-Settings } finally { $script:FailureHook = $null }
        [IO.File]::ReadAllText($script:SettingsPath) | Should Be $legacy
        @(Get-ChildItem -LiteralPath $TestDrive -File -Force | Where-Object { $_.Name -like '.failed-migration.json.*' }).Count | Should Be 0
    }

    It 'exposes a streaming worksheet validator without worksheet DOM row queries' {
        (Get-Command Test-AllevaWorksheetEntryStreaming -ErrorAction Stop).Name | Should Be 'Test-AllevaWorksheetEntryStreaming'
        $source = (Get-Command Test-AllevaWorkbookPackage).ScriptBlock.ToString()
        $source | Should Not Match 'worksheet\.SelectNodes'
        $source | Should Match 'Test-AllevaWorksheetEntryStreaming'
    }

    It 'keeps list and detail identities independent and marks conflicts incomplete' {
        $script:ExportDirectory = Join-Path $TestDrive 'identity-conflict'
        $script:Settings['MaxPages'] = 5
        $script:PageProvider = {
            param($Path)
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='patient-a'; name=[pscustomobject]@{ clientFullName='Synthetic Alpha' } },[pscustomobject]@{ id='patient-b'; name=[pscustomobject]@{ clientFullName='Synthetic Beta' } }); hasMore=$false } }
            if ($Path -eq '/treatment-plans') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='plan-conflict'; patientId='patient-a'; listMarker='LIST_A' }); hasMore=$false } }
        }
        $script:DetailProvider = { [pscustomobject]@{ id='plan-conflict'; patientId='patient-b'; detailMarker='DETAIL_B' } }
        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.IdentityConflictCount | Should Be 1
            $xml = Get-SyntheticWorkbookXmlText -Path $result.WorkbookPath
            $xml | Should Match 'IDENTITY_CONFLICT'
            $xml | Should Match 'LIST_A'
            $xml | Should Match 'DETAIL_B'
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
        }
    }

    It 'accepts a detail-only patient identity without a premature list mapping failure' {
        $script:ExportDirectory = Join-Path $TestDrive 'detail-only-identity'
        $script:SettingsPath = Join-Path $TestDrive 'detail-only-settings.json'
        $script:Settings['MaxPages'] = 5
        Save-Settings
        $script:PageProvider = {
            param($Path)
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='patient-detail-only'; name=[pscustomobject]@{ clientFullName='Synthetic Detail Identity' } }); hasMore=$false } }
            if ($Path -eq '/treatment-plans') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='plan-detail-only'; listMarker='LIST_WITHOUT_PATIENT' }); hasMore=$false } }
        }
        $script:DetailProvider = { [pscustomobject]@{ id='plan-detail-only'; patientId='patient-detail-only'; detailMarker='DETAIL_WITH_PATIENT' } }
        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'COMPLETE'
            $result.MappingMissCount | Should Be 0
            $result.IdentityConflictCount | Should Be 0
            $xml = Get-SyntheticWorkbookXmlText -Path $result.WorkbookPath
            $xml | Should Match 'Synthetic Detail Identity'
            $xml | Should Match 'DETAIL_WITH_PATIENT'
        } finally {
            $script:PageProvider = $null
            $script:DetailProvider = $null
        }
    }

    It 'recreates its contained patient-index directory before the first shard write' {
        $script:ExportDirectory = Join-Path $TestDrive 'index-recreation'
        $index = New-AllevaEncryptedPatientIndex -Directory $script:ExportDirectory
        try {
            [IO.Directory]::Delete([string]$index.Path)
            Add-AllevaPatientIndexEntry -Index $index -PatientId 'synthetic-patient' -Names ([pscustomobject]@{ ClientFullName='Synthetic Index' })
            (Test-Path -LiteralPath ([string]$index.Path) -PathType Container) | Should Be $true
            (Get-AllevaPatientIndexEntry -Index $index -PatientId 'synthetic-patient').ClientFullName | Should Be 'Synthetic Index'
        } finally {
            Remove-AllevaEncryptedPatientIndex $index
        }
    }

    It 'continues contained cleanup and clears all keys after an earlier artifact cleanup error' {
        $script:ExportDirectory = Join-Path $TestDrive 'independent-cleanup'
        $first = New-AllevaEncryptedRowSpool -Directory $script:ExportDirectory
        $second = New-AllevaEncryptedRowSpool -Directory $script:ExportDirectory
        $index = New-AllevaEncryptedPatientIndex -Directory $script:ExportDirectory
        Close-AllevaEncryptedRowSpool $first
        Close-AllevaEncryptedRowSpool $second
        $lock = New-Object IO.FileStream([string]$first.Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::None)
        $cleanupThrew = $false
        try {
            try { Invoke-AllevaExportArtifactCleanup -Spools @($first,$second) -PatientIndex $index } catch { $cleanupThrew = $true }
        } finally {
            $lock.Dispose()
            if ([IO.File]::Exists([string]$first.Path)) { [IO.File]::Delete([string]$first.Path) }
        }
        $cleanupThrew | Should Be $true
        [IO.File]::Exists([string]$second.Path) | Should Be $false
        [IO.Directory]::Exists([string]$index.Path) | Should Be $false
        ($first.Entropy | Measure-Object -Sum).Sum | Should Be 0
        ($second.Entropy | Measure-Object -Sum).Sum | Should Be 0
        ($index.Entropy | Measure-Object -Sum).Sum | Should Be 0
        ($index.Key | Measure-Object -Sum).Sum | Should Be 0
    }

    It 'treats case-distinct list and detail patient IDs as an ordinal identity conflict' {
        $script:ExportDirectory = Join-Path $TestDrive 'case-patient-conflict'
        $script:SettingsPath = Join-Path $TestDrive 'case-patient-settings.json'
        $script:Settings['MaxPages'] = 5
        Save-Settings
        $script:PageProvider = {
            param($Path)
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='PATIENT-A'; name=[pscustomobject]@{ clientFullName='Synthetic Upper' } },[pscustomobject]@{ id='patient-a'; name=[pscustomobject]@{ clientFullName='Synthetic Lower' } }); hasMore=$false } }
            if ($Path -eq '/treatment-plans') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='plan-case-patient'; patientId='PATIENT-A'; listMarker='UPPER_LIST' }); hasMore=$false } }
        }
        $script:DetailProvider = { [pscustomobject]@{ id='plan-case-patient'; patientId='patient-a'; detailMarker='LOWER_DETAIL' } }
        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.IdentityConflictCount | Should Be 1
            $xml = Get-SyntheticWorkbookXmlText -Path $result.WorkbookPath
            $xml | Should Match 'IDENTITY_CONFLICT'
            $xml | Should Match 'UPPER_LIST'
            $xml | Should Match 'LOWER_DETAIL'
        } finally { $script:PageProvider=$null; $script:DetailProvider=$null }
    }

    It 'treats case-distinct list and detail plan IDs as an ordinal identity conflict' {
        $script:ExportDirectory = Join-Path $TestDrive 'case-plan-conflict'
        $script:SettingsPath = Join-Path $TestDrive 'case-plan-settings.json'
        $script:Settings['MaxPages'] = 5
        Save-Settings
        $script:PageProvider = {
            param($Path)
            if ($Path -eq '/clients') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='patient-plan-case'; name=[pscustomobject]@{ clientFullName='Synthetic Plan Case' } }); hasMore=$false } }
            if ($Path -eq '/treatment-plans') { return [pscustomobject]@{ items=@([pscustomobject]@{ id='PLAN-CASE'; patientId='patient-plan-case' }); hasMore=$false } }
        }
        $script:DetailProvider = { [pscustomobject]@{ id='plan-case'; patientId='patient-plan-case'; detailMarker='CASE_PLAN_DETAIL' } }
        try {
            $result = Invoke-CompleteAllevaExport
            $result.Status | Should Be 'INCOMPLETE'
            $result.IdentityConflictCount | Should Be 1
        } finally { $script:PageProvider=$null; $script:DetailProvider=$null }
    }
}
