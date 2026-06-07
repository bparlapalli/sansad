@echo off
REM Run this from: C:\Users\bhara\OneDrive\Desktop\paramasrota\sansad\
REM Double-click or run in CMD to stage, commit, and push all changes.

cd /d "%~dp0"

echo [1/4] Staging files...
git add .gitignore CLAUDE.md ^
  app/admin.py app/app.py app/digest.py app/query.py main.py ^
  app/search_bp.py ^
  app/templates/base.html app/templates/search.html app/templates/speaker.html ^
  app/templates/sessions.html app/templates/speakers_list.html app/templates/stats.html ^
  core/db.py ^
  ai_content.sql export_for_ai.py run_stats.py seed_parties.py ^
  test_queries.py test_sarvam_ai_parser_hindi.py ^
  docs/screenshots/

echo [2/4] Status check...
git status --short

echo [3/4] Committing...
git commit -m "feat: unified search, speakers fix, AI profiles, virtiofs fix, docs + screenshots (2026-06-06)"

echo [4/4] Pushing to origin/main...
git push origin main

echo.
echo Done. Check above for any errors.
pause
