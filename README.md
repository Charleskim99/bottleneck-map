# 병목 지도 뷰어 (Intro Funnel web draft)

Intro Funnel 스킬이 만든 결과(병목 지도 · 분야 동향 요약 · 인트로 참고문헌)를 브라우저에서 읽고, 주제마다 내 판단과 메모를 남기는 웹 앱 초안입니다. AI+X HW5 제출물.

## 구성 (화면 · 처리 · 저장 · 배포)

| 조각 | 도구 | 파일 |
|---|---|---|
| 화면 | 정적 HTML·CSS·JS, 빌드 없음 | `index.html`, `styles.css`, `app.js` |
| 처리 | 신호 단어 판정은 브라우저, AI 판정은 Vercel Python 서버 함수 | `app.js`, `api/label.py` |
| 저장 | 브라우저 localStorage(내 판단·메모·판정 기록). 계정별 저장은 다음 단계 | `app.js` |
| 데이터 | 실행 결과를 JSON으로 내보낸 정적 파일 | `build_data.py` → `data/*.json` |
| 배포 | Vercel (정적 + `api/`) | `vercel.json` |

## 로컬에서 보기

```
cd Dropbox/intro-funnel/webapp
PYTHONUTF8=1 python build_data.py          # 실행 결과 -> data/*.json (금지 용어 검사 포함)
PYTHONUTF8=1 python dev_server.py 8765     # http://localhost:8765/
```
`/api/label`은 `OPENAI_API_KEY` 환경변수가 있을 때만 LLM을 부릅니다. 없으면 501을 돌려주고 화면은 신호 단어 판정으로 대신합니다.

주소의 해시로 특정 화면을 바로 열 수 있습니다. `#tab=map&theme=BN02`는 주제 하나를 펼친 병목 지도, `#tab=label&s=문장`은 문장을 채운 판정 탭입니다(주제 id는 `data/bottlenecks.json`의 `id`).

## Vercel에 배포하기 (Node 설치 없이)

1. 이 폴더를 GitHub 저장소로 올립니다.
   ```
   git init && git add -A && git commit -m "web draft"
   git remote add origin https://github.com/<계정>/bottleneck-map.git && git push -u origin master
   ```
2. vercel.com → **Add New… → Project** → 저장소 Import → Framework Preset은 **Other** → Deploy.
3. (선택) Project → Settings → Environment Variables에 `OPENAI_API_KEY`를 넣고 Redeploy하면 AI 판정이 켜집니다. 키는 절대 코드나 프론트에 넣지 않습니다.
4. 배포 주소(`https://<프로젝트>.vercel.app`)를 보고서에 적습니다.

## 확인 항목 (영상 2·3에서 배운 것)

- 새로고침 뒤에도 내 판단·메모가 남는가 → localStorage라 같은 브라우저에서는 남습니다. 다른 기기에서는 보이지 않습니다(한계).
- 다른 사람이 내 메모를 고칠 수 있는가 → 지금은 브라우저별 저장이라 해당 없음. Supabase를 붙이면 RLS로 막아야 합니다(다음 단계).
- API 키가 프론트로 새는가 → 키는 서버 함수의 환경변수에만 있고, `app.js`에는 없습니다.

## 데이터 출처

공개 초록 문장(OpenAlex)과 레지스트리 서지(Crossref)만 담습니다. 구독 논문 본문이나 비공개 연구 내용은 없습니다. `build_data.py`가 금지 용어를 검사해 하나라도 걸리면 내보내지 않습니다.
