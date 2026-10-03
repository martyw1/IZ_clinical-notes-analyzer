param([Parameter(Mandatory=$true)][string]$Ffmpeg, [string]$Python = 'python', [string]$Narrator = 'en-US-AvaMultilingualNeural')
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$output = Join-Path $PSScriptRoot 'output'
New-Item -ItemType Directory -Force -Path $output | Out-Null
$scenes = Get-Content (Join-Path $PSScriptRoot 'quick-start-scenes.json') -Raw | ConvertFrom-Json
$segments = @()
$transcript = @('# R3 Treatment Plan Audit Application: quick start', '', 'Actual app screenshots with synthetic example records and plain-language narration.', '')
$captions = @()
$elapsed = 0.0
function Stamp([double]$seconds) { [TimeSpan]::FromSeconds($seconds).ToString('hh\:mm\:ss\,fff') }
function Seconds([string]$stamp) { [TimeSpan]::ParseExact($stamp.Replace(',','.'),'hh\:mm\:ss\.fff',[Globalization.CultureInfo]::InvariantCulture).TotalSeconds }
for ($i = 0; $i -lt $scenes.Count; $i++) {
    $scene = $scenes[$i]
    $base = Join-Path $output ('scene-{0:00}' -f ($i+1))
    $voiceSignature = "$Narrator / -1%"
    $reuseVoice = (Test-Path "$base.txt") -and (Test-Path "$base.mp3") -and (Test-Path "$base.srt") -and (Test-Path "$base.voice") -and ((Get-Content "$base.voice" -Raw).Trim() -eq $voiceSignature) -and ((Get-Content "$base.txt" -Raw).Trim() -eq $scene.speech)
    if (!$reuseVoice) {
        $scene.speech | Set-Content "$base.txt" -Encoding UTF8
        & $Python -m edge_tts --voice $Narrator --rate=-1% --file "$base.txt" --write-media "$base.mp3" --write-subtitles "$base.srt"
        if ($LASTEXITCODE -ne 0) { throw "Neural narration failed for scene $i" }
        $voiceSignature | Set-Content "$base.voice" -Encoding UTF8
    }
    $audioInfo = & $Ffmpeg -hide_banner -i "$base.mp3" 2>&1 | Out-String
    $durationMatch = [regex]::Match($audioInfo,'Duration: (\d\d:\d\d:\d\d\.\d\d)')
    if (!$durationMatch.Success) { throw 'Cannot read narration duration' }
    $audioDuration = [TimeSpan]::Parse($durationMatch.Groups[1].Value,[Globalization.CultureInfo]::InvariantCulture).TotalSeconds
    $duration = [Math]::Ceiling(($audioDuration + 1.0)*30)/30
    $blocks = (Get-Content "$base.srt" -Raw) -split '\r?\n\r?\n'
    $shotStarts = @(0.0)
    foreach ($shot in $scene.shots | Select-Object -Skip 1) {
        $matching = @($blocks | Where-Object { $_ -like "*$($shot.cue)*" })
        if ($matching.Count -ne 1) { throw "Screenshot cue must match one caption: $($shot.cue)" }
        $cueTime = [regex]::Match($matching[0],'(\d\d:\d\d:\d\d,\d\d\d) -->')
        $shotStarts += (Seconds $cueTime.Groups[1].Value)
    }
    $shotStarts += $duration
    $slideList = @()
    for ($stage = 0; $stage -lt $scene.lines.Count; $stage++) {
    $bitmap = New-Object System.Drawing.Bitmap(1600,900)
    $g = [Drawing.Graphics]::FromImage($bitmap)
    $g.SmoothingMode = 'AntiAlias'
    $g.TextRenderingHint = 'AntiAliasGridFit'
    $g.Clear([Drawing.ColorTranslator]::FromHtml('#FAF5EB'))
    $white = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#203D3B'))
    $muted = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#576963'))
    $teal = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#20786F'))
    $paper = New-Object Drawing.SolidBrush([Drawing.Color]::White)
    $peach = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#F1BD95'))
    $pale = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#E5EFE8'))
    $inactive = New-Object Drawing.SolidBrush([Drawing.ColorTranslator]::FromHtml('#EBEEEA'))
    $light = New-Object Drawing.SolidBrush([Drawing.Color]::White)
    $small = New-Object Drawing.Font('Segoe UI',20)
    $title = New-Object Drawing.Font('Segoe UI',45,[Drawing.FontStyle]::Bold)
    $body = New-Object Drawing.Font('Segoe UI',24)
    $stepFont = New-Object Drawing.Font('Segoe UI',21)
    $panelTitle = New-Object Drawing.Font('Segoe UI',28,[Drawing.FontStyle]::Bold)
    $g.DrawString('R3 TREATMENT PLAN AUDIT APPLICATION',$small,$teal,80,25)
    $g.DrawString($scene.title,$panelTitle,$white,(New-Object Drawing.RectangleF(80,65,1440,65)))
    $g.DrawString('EXAMPLE RECORDS ONLY',$small,$muted,1220,25)
    $shot = $scene.shots[$stage]
    $imagePath = Join-Path $PSScriptRoot ("screenshots/$($shot.file).png")
    $screen = [Drawing.Image]::FromFile($imagePath)
    $crop = $shot.crop
    $cropWidth = [Math]::Min([int]$crop[2], $screen.Width - [int]$crop[0])
    $cropHeight = [Math]::Min([int]$crop[3], $screen.Height - [int]$crop[1])
    $scale = [Math]::Min(1440.0 / $cropWidth, 575.0 / $cropHeight)
    $drawWidth = $cropWidth * $scale
    $drawHeight = $cropHeight * $scale
    $drawX = 80 + (1440 - $drawWidth)/2
    $drawY = 145 + (575 - $drawHeight)/2
    $destination = New-Object Drawing.RectangleF($drawX,$drawY,$drawWidth,$drawHeight)
    $selection = New-Object Drawing.RectangleF($crop[0],$crop[1],$cropWidth,$cropHeight)
    $g.FillRectangle($paper,80,145,1440,575)
    $g.InterpolationMode = 'HighQualityBicubic'
    $g.DrawImage($screen,$destination,$selection,[Drawing.GraphicsUnit]::Pixel)
    if ($shot.box) {
        $box = $shot.box
        $pen = New-Object Drawing.Pen([Drawing.ColorTranslator]::FromHtml('#C97734'),4)
        $g.DrawRectangle($pen,[single]($drawX+($box[0]-$crop[0])*$scale),[single]($drawY+($box[1]-$crop[1])*$scale),[single]($box[2]*$scale),[single]($box[3]*$scale))
        $pen.Dispose()
    }
    $screen.Dispose()
    $g.DrawString($scene.lines[$stage],$stepFont,$white,(New-Object Drawing.RectangleF(80,740,1440,75)))
    $frame = "$base-step-$stage.png"
    $bitmap.Save($frame,[Drawing.Imaging.ImageFormat]::Png)
    $g.Dispose(); $bitmap.Dispose()
    foreach ($resource in @($small,$title,$body,$stepFont,$panelTitle,$white,$muted,$teal,$paper,$peach,$pale,$inactive,$light)) { $resource.Dispose() }
    $slideList += @("file 'scene-$('{0:00}' -f ($i+1))-step-$stage.png'",('duration {0}' -f (($shotStarts[$stage+1]-$shotStarts[$stage]).ToString([Globalization.CultureInfo]::InvariantCulture))))
    }
    $slideList += "file 'scene-$('{0:00}' -f ($i+1))-step-$($scene.lines.Count-1).png'"
    $slideList | Set-Content "$base-frames.txt" -Encoding ascii
    $fadeOut = ($duration-0.25).ToString([Globalization.CultureInfo]::InvariantCulture)
    & $Ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i "$base-frames.txt" -i "$base.mp3" -t $duration -vf "fps=30,scale=1280:720,format=yuv420p,fade=t=in:st=0:d=0.25,fade=t=out:st=${fadeOut}:d=0.25" -r 30 -c:v libx264 -preset fast -crf 21 -c:a aac -b:a 128k -af 'apad' "$base.mp4"
    if ($LASTEXITCODE -ne 0) { throw "Video encoding failed for scene $i" }
    $segments += "file 'scene-$('{0:00}' -f ($i+1)).mp4'"
    $transcript += @("## $($scene.title.Replace("`n",' '))", '', $scene.speech, '')
    $blocks = (Get-Content "$base.srt" -Raw) -split '\r?\n\r?\n'
    foreach ($block in $blocks) {
        $rows = $block -split '\r?\n'
        if ($rows.Count -lt 3) { continue }
        $times = [regex]::Match($rows[1],'(\d\d:\d\d:\d\d,\d\d\d) --> (\d\d:\d\d:\d\d,\d\d\d)')
        if (!$times.Success) { throw 'Unexpected neural subtitle format' }
        $from = $elapsed + (Seconds $times.Groups[1].Value)
        $to = $elapsed + (Seconds $times.Groups[2].Value)
        $captions += @(([int]($captions.Count / 4)+1).ToString(), "$(Stamp $from) --> $(Stamp $to)",($rows[2..($rows.Count-1)] -join ' ').Trim(),'')
    }
    $elapsed += $duration
    Write-Output "Finished scene $($i+1) of $($scenes.Count)"
}
$segments | Set-Content (Join-Path $output 'segments.txt') -Encoding ascii
$transcript | Set-Content (Join-Path $PSScriptRoot 'quick-start-transcript.md') -Encoding UTF8
$captions | Set-Content (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start.en.srt') -Encoding UTF8
& $Ffmpeg -hide_banner -loglevel error -y -f concat -safe 0 -i (Join-Path $output 'segments.txt') -i (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start.en.srt') -map 0:v -map 0:a -map 1 -c:v copy -c:a copy -c:s mov_text -metadata:s:s:0 language=eng -movflags +faststart (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start-selectable-captions.mp4')
if ($LASTEXITCODE -ne 0) { throw 'Final video assembly failed' }
$captionPath = (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start.en.srt').Replace('\','/').Replace(':','\:')
& $Ffmpeg -hide_banner -loglevel error -y -i (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start-selectable-captions.mp4') -vf "subtitles=filename='$captionPath':force_style='FontName=Segoe UI,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H003B3D20,BorderStyle=3,Outline=1,Shadow=0,MarginV=14'" -c:v libx264 -preset fast -crf 21 -c:a copy (Join-Path $PSScriptRoot 'R3-Treatment-Plan-Audit-Quick-Start.mp4')
if ($LASTEXITCODE -ne 0) { throw 'Captioned video encoding failed' }
Write-Output "Video duration: $([Math]::Round($elapsed,1)) seconds"
