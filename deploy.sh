#!/usr/bin/env bash
# בנייה, קומיט, דחיפה ופריסה — פקודה אחת.
#   ./deploy.sh "הודעת קומיט"
#   ./deploy.sh "הודעה" --no-commit     פריסה בלבד
set -euo pipefail
cd "$(dirname "$0")"

MSG="${1:-עדכון האתר}"
SKIP_COMMIT=false
[[ "${2:-}" == "--no-commit" ]] && SKIP_COMMIT=true

echo "▸ בונה את האתר"
python3 build_site.py

if [[ "$SKIP_COMMIT" == false ]] && [[ -n "$(git status --porcelain)" ]]; then
  echo "▸ קומיט ודחיפה"
  git add -A
  git -c user.email=tomtsadaka@gmail.com -c user.name=TomTsadaka commit -q -m "$MSG

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
  git push -q origin main
else
  echo "▸ אין שינויים לקומיט"
fi

echo "▸ פורס לוורסל"
( cd site && npx --yes vercel@latest deploy --prod --yes >/dev/null 2>&1 )

echo "▸ מאמת"
sleep 12
URL="https://bagrut-math-archive.vercel.app"
for p in "/" "/data/scans.json"; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL$p")
  printf "   %-22s %s\n" "$p" "$CODE"
  [[ "$CODE" == "200" ]] || { echo "   ✗ הפריסה נכשלה"; exit 1; }
done
N=$(curl -s "$URL/data/scans.json" | python3 -c "import json,sys;print(len(json.load(sys.stdin)))")
echo "   ✓ $URL — $N שאלות"
