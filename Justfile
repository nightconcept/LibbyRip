# Convert an MP3 (with embedded chapters/metadata) to M4B
m4b mp3file:
    #!/bin/bash
    set -euo pipefail
    input="{{mp3file}}"
    [ -f "$input" ] || { echo "Error: File not found: $input"; exit 1; }
    ext="${input##*.}"
    [ "$ext" = "mp3" ] || [ "$ext" = "MP3" ] || { echo "Error: File must be an .mp3"; exit 1; }
    output="${input%.$ext}.m4b"
    ffmpeg -i "$input" -c:a aac -b:a 128k -vn -map_metadata 0 -map_chapters 0 -f ipod "$output"
    echo "Created: $output"
