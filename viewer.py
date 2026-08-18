# -*- coding: utf-8 -*-
"""בונה דף HTML עצמאי לעיון במאגר (RTL, עם סינון וחיפוש)."""
import json, os, html
import db, export

OUT = os.path.join(os.path.dirname(__file__), "exports", "viewer.html")

TPL = """<!doctype html><html lang="he" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>מאגר שאלוני בגרות במתמטיקה</title>
<style>
:root{--bg:#faf8f4;--card:#fff;--ink:#1c2733;--muted:#65748a;--line:#e3ddd2;
      --accent:#2f5d7c;--accent2:#c0603a;--chip:#eef2f6;}
@media(prefers-color-scheme:dark){:root{--bg:#141a20;--card:#1c242c;--ink:#e8edf2;
      --muted:#93a2b4;--line:#2b3540;--accent:#7fb0d0;--accent2:#e08a60;--chip:#243039;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
     font:16px/1.65 "Assistant","Segoe UI",system-ui,sans-serif}
header{background:var(--accent);color:#fff;padding:22px 20px}
header h1{margin:0;font-size:22px;font-weight:600}
header p{margin:6px 0 0;opacity:.85;font-size:14px}
.wrap{max-width:1060px;margin:0 auto;padding:20px}
.bar{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:18px}
.bar input,.bar select{padding:9px 12px;border:1px solid var(--line);border-radius:8px;
     background:var(--card);color:var(--ink);font-size:14px;font-family:inherit}
.bar input{flex:1;min-width:220px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:18px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi b{display:block;font-size:22px;color:var(--accent)}
.kpi span{font-size:12px;color:var(--muted)}
.q{background:var(--card);border:1px solid var(--line);border-radius:12px;
   padding:16px 18px;margin-bottom:12px}
.meta{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}
.chip{background:var(--chip);color:var(--muted);border-radius:99px;padding:3px 10px;font-size:12px}
.chip.t{background:var(--accent);color:#fff}
.chip.d{background:var(--accent2);color:#fff}
.body{white-space:pre-wrap;margin:0 0 10px}
.parts{border-inline-start:3px solid var(--line);padding-inline-start:14px;margin-top:10px}
.part{margin-bottom:10px}
.part b{color:var(--accent2)}
.skills{font-size:13px;color:var(--muted);margin-top:8px}
.figs{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}\n.fig{max-width:260px;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff;padding:6px}\n.count{color:var(--muted);font-size:13px;margin-bottom:10px}
.empty{text-align:center;color:var(--muted);padding:50px}
.mth{font-family:"Cambria Math","Latin Modern Math",Georgia,serif;direction:ltr;
     display:inline-block;unicode-bidi:isolate}
.frac{display:inline-flex;flex-direction:column;vertical-align:-0.5em;
      text-align:center;font-size:.9em;margin:0 .15em}
.frac .num{border-bottom:1.2px solid currentColor;padding:0 .25em}
.frac .den{padding:0 .25em}
.sqrt{border-top:1.2px solid currentColor;padding:0 .15em}
footer{text-align:center;color:var(--muted);font-size:13px;padding:26px}
</style></head><body>
<header><h1>מאגר שאלוני הבגרות במתמטיקה</h1>
<p>__SUB__</p></header>
<div class="wrap">
<div class="kpis">__KPIS__</div>
<div class="bar">
  <input id="q" placeholder="חיפוש חופשי בנוסח השאלה…">
  <select id="units"><option value="">כל הרמות</option>
    <option value="3">3 יח"ל</option><option value="4">4 יח"ל</option>
    <option value="5">5 יח"ל</option></select>
  <select id="topic"><option value="">כל הנושאים</option>__TOPICS__</select>
  <select id="diff"><option value="">כל רמות הקושי</option>
    <option>1</option><option>2</option><option>3</option><option>4</option><option>5</option></select>
  <select id="year"><option value="">כל השנים</option>__YEARS__</select>
</div>
<div id="count" class="count"></div>
<div id="list"></div></div>
<footer>נבנה מ-__NP__ שאלוני בגרות · מקורות: משרד החינוך + ארכיון האינטרנט</footer>
<script>
const DATA = __DATA__;
__JS__
</script></body></html>"""


def build():
    con = db.connect()
    qs = json.loads(open(export.export_json(con)[0], encoding="utf-8").read())
    s = db.stats(con)
    topics = sorted({q["topic"] for q in qs if q.get("topic")})
    years = sorted({q["year"] for q in qs if q.get("year")}, reverse=True)
    kpis = [("שאלונים", s["papers"]), ("הורדו", s["fetched"]),
            ("שאלות", s["questions"]), ("סעיפים", s["parts"]),
            ("שנים", f"{s['year_min']}–{s['year_max']}")]
    h = (TPL
         .replace("__DATA__", json.dumps(qs, ensure_ascii=False))
         .replace("__JS__", open(os.path.join(os.path.dirname(__file__),
                                 "assets", "viewer.js"), encoding="utf-8").read())
         .replace("__TOPICS__", "".join(f"<option>{html.escape(t)}</option>" for t in topics))
         .replace("__YEARS__", "".join(f"<option>{y}</option>" for y in years))
         .replace("__KPIS__", "".join(
             f'<div class="kpi"><b>{v}</b><span>{k}</span></div>' for k, v in kpis))
         .replace("__NP__", str(s["papers"]))
         .replace("__SUB__", f"{s['papers']} שאלונים · {s['questions']} שאלות מסווגות · "
                             f"{s['year_min']}–{s['year_max']}"))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(h)
    print(f"  ✓ {OUT}")
    return OUT


if __name__ == "__main__":
    build()
