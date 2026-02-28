지금 프로젝트는 몰두봇이며.

LangChain v1.0 - deepagents(create_deep_agent)로 구성함

lagnchain v1.0 공식 미들웨어를 사용(Import)해서 before/after 방식으로 구현함

fastapi 사용.

하드코딩은 하지 않음.

outlook addin 으로 클라이언트가 사용함(outkook-addin)

ngrok으로 서버 국동함.

microsoft graph api를 통해 메일을 조회

메일 데이터는 sqlite3를 사용하며 데이터는 database/email.db에 migration 함

임베딩은 크로마 디비 사용, 데이터는 chroma_db에 마이그레이션 함.

prompts는 prompts폴더에서 모아서 관리, langchain 이 사용하는 skills.md도 마찬가지로 skills폴더에서 관리

openai사용함 .env에 키값 있음.

폴더 구조는 현재 설명한 application을 참고하여 이상적으로 구현함. 그리고 각 폴더에는 task.md가 있고 여기에서 각 폴더 application의 변경 이력을 상세히 관리함(CODEX가 해야 함, 코드 수정하기 전 / 후 항상 업데이트 필요)

AGENTS.MD파일을 참고해서 코드를 작성해 줘야함.

