# Contract Sync

외주용역 계약서에서 추진 일정을 추출하고 업무 목록을 생성하는 서비스

## 주요 기능
- PDF, DOCX, HWP 계약서 파일 업로드
- Google Gemini를 활용한 일정 자동 추출 (이미지 PDF 직접 인식)
- 업무 목록 생성 및 관리
- 대시보드에서 전체 업무 현황 확인
- 워드 파일로 내보내기

## 배포

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/ZweBXA?referralCode=alphasec)

또는 아래 버튼 클릭:

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/new/template?template=https://github.com/gogeangs/Contract_Sync)

## 환경 변수 설정

배포 시 다음 환경 변수를 설정해야 합니다:

| 변수명 | 설명 |
|--------|------|
| `GEMINI_API_KEY` | Google Gemini API 키 |
| `SECRET_KEY` | 세션 암호화 키 |
| `GOOGLE_CLIENT_ID` | Google OAuth 클라이언트 ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 시크릿 |

## 로컬 실행

```bash
# 가상환경 생성
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경 변수 설정
cp .env.example .env
# .env 파일 수정

# 서버 실행
uvicorn app.main:app --reload
```

## 기술 스택
- FastAPI
- SQLAlchemy (SQLite)
- Google Gemini API
- Alpine.js + Tailwind CSS
