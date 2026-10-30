/* ===========================================================
   서가(SEОGA) — 데모 데이터
   ※ 도서 메타데이터(제목/저자/출판사)는 실제 정보,
     가용성·종료 예정일은 전부 시뮬레이션 데이터입니다.
   =========================================================== */

const PLATFORMS = {
  millie:    { name: '밀리의 서재', short: '밀리',   kind: 'sub' },
  ridiselect:{ name: '리디셀렉트',  short: '리디셀', kind: 'sub' },
  sam:       { name: '교보 sam',    short: 'sam',   kind: 'sub' },
  willa:     { name: '윌라',        short: '윌라',   kind: 'sub' },
  aladin:    { name: '알라딘',      short: '알라딘', kind: 'buy' },
  yes24:     { name: '예스24',      short: '예스24', kind: 'buy' },
  kyobo:     { name: '교보문고',    short: '교보',   kind: 'buy' },
  ridi:      { name: '리디',        short: '리디',   kind: 'buy' },
  library:   { name: '도서관 전자책', short: '도서관', kind: 'free' },
  gongu:     { name: '공개 도서',   short: '무료',   kind: 'free' },
};

const SUB_KEYS = ['millie', 'ridiselect', 'sam', 'willa'];

/* --- 취향 태그 사전 ------------------------------------------ */
const TAGS = ['한국소설','일본소설','중국소설','문학','고전','SF','미스터리','스릴러',
              '에세이','인문','철학','과학','역사','사회','심리','자기계발','경제','여행','로맨스'];
const MOODS = ['가벼운','따뜻한','사색','서정적','무거운','자극','지적','실험적','문장이좋은','감정'];

/* --- 도서 데이터 -------------------------------------------- */
/* av: { 플랫폼: {s:'on'} | {s:'ending', d:남은일수} | {buy:가격} | {wait:대기인원} } */
const BOOKS = [
  {
    id: 'chae', title: '채식주의자', author: '한강', publisher: '창비',
    cover_url: 'https://image.yes24.com/goods/108422348/L', year: 2007, pages: 272,
    tags: ['한국소설', '문학'], moods: ['무거운', '실험적', '문장이좋은'],
    blurb: '어느 날 꿈을 꾼 뒤 육식을 거부하기 시작한 영혜와, 그를 둘러싼 세 사람의 시선. 노벨문학상 수상 이후 다시 읽히는 문제작.',
    av: { millie: { s: 'on' }, sam: { s: 'ending', d: 27 }, ridi: { buy: 14400 }, aladin: { buy: 14400 }, library: { wait: 2 } },
    hot: true,
  },
  {
    id: 'jagbyeol', title: '작별하지 않는다', author: '한강', publisher: '문학동네',
    cover_url: 'https://image.yes24.com/goods/103495056/L', year: 2021, pages: 332,
    tags: ['한국소설', '문학'], moods: ['무거운', '문장이좋은', '감정'],
    blurb: '제주 4·3의 기억을 안고 눈 내리는 섬으로 향하는 세 사람. 상실과 애도의 시간을 견디는 문장들.',
    av: { sam: { s: 'on' }, willa: { s: 'on' }, aladin: { buy: 15800 } },
  },
  {
    id: 'sonyeon', title: '소년이 온다', author: '한강', publisher: '창비',
    cover_url: 'https://image.yes24.com/goods/176969335/L', year: 2014, pages: 216,
    tags: ['한국소설', '문학', '역사'], moods: ['무거운', '감정'],
    blurb: '1980년 5월 광주, 계엄군에 맞선 소년 동호와 그 곁의 사람들. 여러 목소리로 이어지는 기억의 기록.',
    av: { millie: { s: 'ending', d: 9 }, sam: { s: 'on' }, library: { wait: 4 }, aladin: { buy: 12600 } },
  },
  {
    id: 'pyeonuijeom', title: '불편한 편의점', author: '김호연', publisher: '나무옆의자',
    cover_url: 'https://image.yes24.com/goods/101506482/L', year: 2021, pages: 316,
    tags: ['한국소설'], moods: ['따뜻한', '가벼운', '감정'],
    blurb: '서울역 골목 편의점에 야간 알바로 나타난 노숙인 독고. 기묘하게 이어지는 손님들의 사정.',
    av: { millie: { s: 'on' }, ridiselect: { s: 'on' }, sam: { s: 'on' }, willa: { s: 'on' }, library: { wait: 1 }, aladin: { buy: 13500 } },
    hot: true,
  },
  {
    id: 'among', title: '아몬드', author: '손원평', publisher: '다즐링',
    cover_url: 'https://image.yes24.com/goods/119697570/L', year: 2017, pages: 264,
    tags: ['한국소설'], moods: ['따뜻한', '감정', '가벼운'],
    blurb: '감정을 느끼지 못하는 소년 윤재가 세상과 부딪히며 조금씩 타인을 이해하게 되는 성장의 기록.',
    av: { millie: { s: 'on' }, sam: { s: 'on' }, library: { wait: 6 }, aladin: { buy: 12600 } },
    hot: true,
  },
  {
    id: 'guui', title: '구의 증명', author: '최진영', publisher: '은행나무',
    cover_url: 'https://image.yes24.com/goods/118578901/L', year: 2015, pages: 192,
    tags: ['한국소설'], moods: ['무거운', '실험적', '감정'],
    blurb: '구가 죽은 뒤 남겨진 사랑의 문장들. 짧지만 오래 남는 소설.',
    av: { millie: { s: 'ending', d: 17 }, sam: { s: 'on' }, aladin: { buy: 10800 } },
  },
  {
    id: 'pagwa', title: '파과', author: '구병모', publisher: '위즈덤하우스',
    cover_url: 'https://image.yes24.com/goods/125761518/L', year: 2018, pages: 268,
    tags: ['한국소설', '스릴러'], moods: ['자극', '무거운'],
    blurb: '예순다섯 살 살수 조각과, 그를 움직이는 사람들. 노년의 몸으로 벌이는 마지막 청부.',
    av: { millie: { s: 'on' }, sam: { s: 'ending', d: 21 }, willa: { s: 'on' }, aladin: { buy: 14000 } },
    hot: true,
  },
  {
    id: 'bit', title: '우리가 빛의 속도로 갈 수 없다면', author: '김초엽', publisher: '허블',
    cover_url: 'https://image.yes24.com/goods/77220299/L', year: 2019, pages: 308,
    tags: ['SF', '한국소설'], moods: ['지적', '따뜻한', '사색'],
    blurb: '우주와 가까운 미래를 배경으로, 사람 사이의 거리와 다정함을 그린 일곱 편의 SF 단편.',
    av: { millie: { s: 'on' }, ridiselect: { s: 'on' }, library: { wait: 3 }, aladin: { buy: 12600 } },
    hot: true,
  },
  {
    id: 'ongsil', title: '지구 끝의 온실', author: '김초엽', publisher: '자이언트북스',
    cover_url: 'https://image.yes24.com/goods/103026125/L', year: 2021, pages: 392,
    tags: ['SF', '한국소설'], moods: ['지적', '서정적'],
    blurb: '멸망 이후의 세계, 살아남은 식물과 사람들. 폐허에서 피어난 온실 하나를 둘러싼 이야기.',
    av: { willa: { s: 'on' }, aladin: { buy: 14800 } },
  },
  {
    id: 'balgeunbam', title: '밝은 밤', author: '최은영', publisher: '문학동네',
    cover_url: 'https://image.yes24.com/goods/102687133/L', year: 2021, pages: 372,
    tags: ['한국소설', '문학'], moods: ['따뜻한', '감정', '사색'],
    blurb: '증조모에서 나까지 이어지는 네 세대 여성의 삶. 서로를 미처 알지 못했던 시간을 되짚는다.',
    av: { willa: { s: 'on' }, library: { wait: 2 }, aladin: { buy: 13500 } },
  },
  {
    id: 'wanjeonhan', title: '완전한 행복', author: '정유정', publisher: '은행나무',
    cover_url: 'https://image.yes24.com/goods/101908580/L', year: 2021, pages: 460,
    tags: ['한국소설', '스릴러'], moods: ['자극', '무거운'],
    blurb: '자신의 행복을 위해 타인을 지워나가는 여자. 통제욕이 배어든 서늘한 서사.',
    av: { sam: { s: 'on' }, aladin: { buy: 16200 } },
  },
  {
    id: 'palgyeong', title: '82년생 김지영', author: '조남주', publisher: '민음사',
    cover_url: 'https://image.yes24.com/goods/104673344/L', year: 2016, pages: 192,
    tags: ['한국소설', '사회'], moods: ['무거운', '지적'],
    blurb: '1982년에 태어난 한 여자의 삶을 담담하게 좇으며, 우리가 당연하게 넘긴 것들을 되묻는다.',
    av: { willa: { s: 'on' }, library: { wait: 7 }, aladin: { buy: 11700 } },
    hot: true,
  },
  {
    id: 'yeohang', title: '여행의 이유', author: '김영하', publisher: '문학동네',
    cover_url: 'https://image.yes24.com/goods/125905365/L', year: 2019, pages: 232,
    tags: ['에세이', '여행'], moods: ['따뜻한', '사색'],
    blurb: '작가 김영하가 여행에서 얻은 것들. 떠남과 돌아옴, 낯섦이 시간이 되는 방식에 대한 산문.',
    av: { millie: { s: 'on' }, willa: { s: 'on' }, aladin: { buy: 12600 } },
  },
  {
    id: 'salgja', title: '살인자의 기억법', author: '김영하', publisher: '문학동네',
    cover_url: 'https://image.yes24.com/goods/91901136/L', year: 2013, pages: 276,
    tags: ['한국소설', '스릴러'], moods: ['자극', '실험적'],
    blurb: '알츠하이머에 걸린 은퇴한 연쇄살인범의 일기. 기억이 흐려지는 동안에도 본능은 사라지지 않는다.',
    av: { willa: { s: 'on' }, library: { wait: 1 }, aladin: { buy: 11700 } },
  },
  {
    id: 'sopen', title: '마흔에 읽는 쇼펜하우어', author: '강용수', publisher: '유노북스',
    cover_url: 'https://image.yes24.com/goods/122437089/L', year: 2023, pages: 280,
    tags: ['인문', '철학', '자기계발'], moods: ['지적', '사색', '가벼운'],
    blurb: '염세주의 철학자 쇼펜하우어의 문장으로 중년의 삶을 다시 읽어내는 인문 교양서.',
    av: { ridiselect: { s: 'on' }, sam: { s: 'on' }, aladin: { buy: 16200 } },
    hot: true,
  },
  {
    id: 'seino', title: '세이노의 가르침', author: '세이노', publisher: '데이원',
    cover_url: 'https://image.yes24.com/goods/117014613/L', year: 2023, pages: 736,
    tags: ['자기계발', '경제'], moods: ['지적', '자극'],
    blurb: '오랜 시간 자수성가를 이야기해온 저자가 직설적으로 던지는 돈과 삶에 대한 조언.',
    av: { sam: { s: 'on' }, library: { wait: 9 }, aladin: { buy: 7200 } },
    hot: true,
  },
  {
    id: 'sapiens', title: '사피엔스', author: '유발 하라리', publisher: '김영사',
    cover_url: 'https://image.yes24.com/goods/23030284/L', year: 2015, pages: 636,
    tags: ['인문', '역사', '과학'], moods: ['지적'],
    blurb: '인류가 어떻게 지구를 지배하게 되었는지, 허구의 이야기가 집단을 묶는 힘이라는 관점으로 푼다.',
    av: { willa: { s: 'on' }, aladin: { buy: 26820 } },
  },
  {
    id: 'chonggyunsoe', title: '총, 균, 쇠', author: '재레드 다이아몬드', publisher: '문학사상',
    cover_url: 'https://image.yes24.com/goods/118794738/L', year: 1998, pages: 752,
    tags: ['인문', '역사', '과학'], moods: ['지적'],
    blurb: '문명의 격차는 왜 생겼는가. 지리와 환경이라는 조건에서 그 답을 찾는 대작.',
    av: { aladin: { buy: 29700 }, kyobo: { buy: 29700 } },
  },
  {
    id: 'jeongui', title: '정의란 무엇인가', author: '마이클 샌델', publisher: '와이즈베리',
    cover_url: 'https://image.yes24.com/goods/36160037/L', year: 2010, pages: 488,
    tags: ['인문', '철학', '사회'], moods: ['지적', '사색'],
    blurb: '하버드의 명강의. 실제 법정 사건과 사례를 통해 공정함과 옳음의 기준을 함께 묻는다.',
    av: { willa: { s: 'on' }, aladin: { buy: 18000 } },
  },
  {
    id: 'mulgogi', title: '물고기는 존재하지 않는다', author: '룰루 밀러', publisher: '곰출판',
    cover_url: 'https://image.yes24.com/goods/105526047/L', year: 2021, pages: 372,
    tags: ['과학', '에세이'], moods: ['지적', '사색', '감정'],
    blurb: '집착이 삶을 무너뜨린 과학자의 이야기와, 혼돈을 질서로 정리하려는 우리의 본능에 대하여.',
    av: { millie: { s: 'ending', d: 13 }, sam: { s: 'on' }, willa: { s: 'on' }, aladin: { buy: 15800 } },
    hot: true,
  },
  {
    id: 'pyeongbeom', title: '이토록 평범한 미래', author: '김연우', publisher: '문학동네', year: 2022, pages: 208,
    tags: ['에세이', 'SF'], moods: ['사색', '지적', '서정적'],
    blurb: 'SF를 읽고 쓰며 미래를 상상해온 저자의 산문. 다정한 기술과 평범한 미래에 대한 기록.',
    av: { willa: { s: 'on' }, aladin: { buy: 12600 } },
  },
  {
    id: 'mius', title: '미움받을 용기', author: '기시미 이치로', publisher: '인플루엔셜',
    cover_url: 'https://image.yes24.com/goods/152360765/L', year: 2014, pages: 332,
    tags: ['자기계발', '심리'], moods: ['위로', '지적', '따뜻한'],
    blurb: '아들러 심리학을 대화 형식으로 풀어낸 책. 타인의 기대에서 벗어나는 법에 대한 이야기.',
    av: { sam: { s: 'on' }, willa: { s: 'on' }, library: { wait: 3 }, aladin: { buy: 14400 } },
  },
  {
    id: 'jukeum', title: '죽음의 수용소에서', author: '빅터 프랭클', publisher: '청아출판사',
    cover_url: 'https://image.yes24.com/goods/103338434/L', year: 2005, pages: 268,
    tags: ['심리', '인문'], moods: ['무거운', '사색'],
    blurb: '수용소에서 살아남은 정신과 의사가 발견한 것. 고통 속에서도 의미를 찾는 인간의 힘.',
    av: { willa: { s: 'on' }, aladin: { buy: 12600 } },
  },
  {
    id: 'eorinwangja', title: '어린 왕자', author: '생텍쥐페리', publisher: '민음사',
    cover_url: 'https://image.yes24.com/goods/22431294/L', year: 1943, pages: 152,
    tags: ['고전', '문학'], moods: ['따뜻한', '가벼운', '서정적'],
    blurb: '사막에 불시착한 조종사와 별에서 온 어린 왕자. 어른이 되어 잊어버린 것들에 대한 우화.',
    av: { gongu: { s: 'on' }, millie: { s: 'on' }, library: { wait: 0 }, aladin: { buy: 7200 } },
    hot: true,
  },
  {
    id: '1984', title: '1984', author: '조지 오웰', publisher: '민음사',
    cover_url: 'https://image.yes24.com/goods/372300/L', year: 1949, pages: 424,
    tags: ['고전', 'SF', '사회'], moods: ['무거운', '지적', '자극'],
    blurb: '모든 것을 감시하는 체제 아래에서, 진실을 기록하려는 한 남자의 마지막 시도.',
    av: { gongu: { s: 'on' }, willa: { s: 'on' }, aladin: { buy: 12600 } },
  },
  {
    id: 'demian', title: '데미안', author: '헤르만 헤세', publisher: '민음사',
    cover_url: 'https://image.yes24.com/goods/176787/L', year: 1919, pages: 240,
    tags: ['고전', '문학'], moods: ['사색', '문장이좋은', '무거운'],
    blurb: '밝은 세계와 어두운 세계 사이에서 자신의 길을 찾아가는 소년 싱클레어의 성장 기록.',
    av: { sam: { s: 'on' }, library: { wait: 2 }, aladin: { buy: 9000 } },
  },
  {
    id: 'noway', title: '노르웨이의 숲', author: '무라카미 하루키', publisher: '민음사',
    cover_url: 'https://image.yes24.com/goods/73782100/L', year: 1987, pages: 424,
    tags: ['일본소설', '문학', '로맨스'], moods: ['서정적', '무거운', '감정'],
    blurb: '죽은 친구와 그를 사랑했던 두 여자. 1960년대 말 도쿄에서의 상실과 첫사랑에 대한 이야기.',
    av: { millie: { s: 'on' }, sam: { s: 'on' }, aladin: { buy: 14400 } },
  },
  {
    id: 'pyeonuijoningan', title: '편의점 인간', author: '무라사키 미치코', publisher: '자음과모음', year: 2016, pages: 184,
    tags: ['일본소설'], moods: ['실험적', '가벼운', '자극'],
    blurb: '편의점에서의 규칙이 완벽한 시민이 되어준 여자. 정상이라는 것의 경계를 흔드는 소설.',
    av: { millie: { s: 'ending', d: 4 }, sam: { s: 'on' }, aladin: { buy: 10800 } },
  },
  {
    id: 'namiya', title: '나미야 잡화점의 기적', author: '히가시노 게이고', publisher: '현대문학',
    cover_url: 'https://image.yes24.com/goods/116586056/L', year: 2012, pages: 452,
    tags: ['일본소설', '미스터리'], moods: ['따뜻한', '감정', '자극'],
    blurb: '폐가가 된 잡화점에 답장이 필요한 고민 상담 편지가 배달된다. 세월을 건너 이어지는 인연.',
    av: { willa: { s: 'on' }, aladin: { buy: 13500 } },
    hot: true,
  },
  {
    id: 'samche', title: '삼체', author: '류츠신', publisher: '자음과모음',
    cover_url: 'https://image.yes24.com/goods/107477481/L', year: 2008, pages: 476,
    tags: ['SF', '중국소설'], moods: ['지적', '자극'],
    blurb: '문명과의 첫 접촉, 우주를 향한 인류의 신호. 하드 SF의 새로운 기준을 세운 1부.',
    av: { millie: { s: 'on' }, sam: { s: 'ending', d: 2 }, aladin: { buy: 16200 } },
    hot: true,
  },
  {
    id: 'hailmary', title: '프로젝트 헤일메리', author: '앤디 위어', publisher: '알에이치코리아',
    cover_url: 'https://image.yes24.com/goods/101375755/L', year: 2021, pages: 604,
    tags: ['SF'], moods: ['지적', '따뜻한'],
    blurb: '태양을 구하기 위해 우주로 간 과학자가 기억을 잃은 채 깨어난다. 문제 풀이로 위기를 넘는 SF.',
    av: { millie: { s: 'ending', d: 6 }, willa: { s: 'on' }, aladin: { buy: 16200 } },
    hot: true,
  },
  {
    id: 'dune', title: '듄', author: '프랭크 허버트', publisher: '황금가지', year: 1965, pages: 672,
    tags: ['SF', '고전'], moods: ['무거운', '지적'],
    blurb: '사막 행성 아라키스를 둘러싼 제국과 귀족의 다툼. 60년이 지나도 유효한 우주 서사의 정전.',
    av: { willa: { s: 'on' }, aladin: { buy: 25200 } },
  },
  {
    id: 'klara', title: '클라라와 태양', author: '가즈오 이시구로', publisher: '비채',
    cover_url: 'https://image.yes24.com/goods/98349603/L', year: 2021, pages: 400,
    tags: ['SF', '문학'], moods: ['서정적', '사색', '무거운'],
    blurb: 'AI 로봇 클라라의 시선으로 본 인간의 사랑과 외로움. 다정함이 서늘함으로 바뀌는 순간.',
    av: { willa: { s: 'on' }, aladin: { buy: 14800 } },
  },
  {
    id: 'hamat', title: '하마터면 열심히 살 뻔했다', author: '하완', publisher: '웅진지식하우스',
    cover_url: 'https://image.yes24.com/goods/126673723/L', year: 2017, pages: 288,
    tags: ['에세이'], moods: ['가벼운', '위로', '따뜻한'],
    blurb: '실수투성이 청춘의 기록. 힘 빼고 살아도 괜찮다고 말해주는 유쾌한 에세이.',
    av: { millie: { s: 'on' }, aladin: { buy: 12600 } },
  },
  {
    id: 'trend2026', title: '트렌드 코리아 2026', author: '김난도 외', publisher: '미래의창', year: 2025, pages: 400,
    tags: ['경제', '사회'], moods: ['지적'],
    blurb: '올해의 소비 키워드와 시장의 흐름을 데이터로 읽어내는 연간 트렌드 리포트.',
    av: { ridiselect: { s: 'on' }, sam: { s: 'on' }, ridi: { buy: 18000 }, aladin: { buy: 18000 } },
  },
  {
    id: 'oneulbam', title: '오늘 밤, 세계에서 이 사랑이 사라진다 해도', author: '이치조 미사키', publisher: '모모',
    cover_url: 'https://image.yes24.com/goods/102360203/L', year: 2021, pages: 288,
    tags: ['일본소설', '로맨스'], moods: ['따뜻한', '감정', '가벼운'],
    blurb: '매주 기억을 잃는 소년과, 그를 계속 사랑하기로 하는 소녀의 이야기.',
    av: { millie: { s: 'on' }, willa: { s: 'on' }, aladin: { buy: 13500 } },
  },
  {
    id: 'seupdeu', title: '스프링 스노우', author: '김혜나', publisher: '은행나무', year: 2022, pages: 248,
    tags: ['한국소설', '에세이'], moods: ['서정적', '사색', '문장이좋은'],
    blurb: '겨울에서 봄으로 넘어가는 계절의 감각을 기록한 짧은 산문. 하루의 온도를 세밀하게 붙잡는다.',
    av: { ridiselect: { s: 'on' }, aladin: { buy: 14000 } },
  },
  {
    id: 'chilhwa', title: '칠화', author: '김혜나', publisher: '은행나무', year: 2023, pages: 300,
    tags: ['한국소설'], moods: ['서정적', '감정'],
    blurb: '상처를 감당하는 방식에 대한 소설. 조용한 문장들이 오래 남는다.',
    av: { aladin: { buy: 14800 }, kyobo: { buy: 14800 } },
  },
];

/* --- 상황별 컬렉션 ------------------------------------------ */
const COLLECTIONS = [
  {
    id: 'night', title: '잠들기 전 30분', desc: '내일이 아까워지지 않는, 짧고 다정한 책',
    pick: (b) => b.pages <= 300 && b.moods.some((m) => ['따뜻한', '사색', '서정적'].includes(m)),
  },
  {
    id: 'commute', title: '출퇴근 20분', desc: '한 정거장마다 끊어 읽기 좋은 호흡',
    pick: (b) => b.tags.includes('에세이') || b.pages <= 280,
  },
  {
    id: 'weekend', title: '주말에 통으로', desc: '하루를 통째로 내줄 두꺼운 몰입',
    pick: (b) => b.pages >= 400,
  },
  {
    id: 'think', title: '생각이 많아지는 밤', desc: '조용한 서사, 오래 남는 문장',
    pick: (b) => b.moods.some((m) => ['문장이좋은', '사색', '서정적'].includes(m)),
  },
  {
    id: 'science', title: '과학이 재밌어지는 순간', desc: '교양이 필요할 때 꺼내는 책',
    pick: (b) => b.tags.some((t) => ['과학', 'SF', '인문'].includes(t)),
  },
  {
    id: 'korean', title: '지금의 한국소설', desc: '지금 가장 많이 읽히는 한국 소설',
    pick: (b) => b.tags.includes('한국소설'),
  },
];

/* --- 취향 찾기 질문 ----------------------------------------- */
const TASTE_FLOW = [
  {
    id: 'mood', q: '요즘, 어떤 책이 당기나요?',
    opts: [
      { label: '지쳐서 아무 생각 없고 싶어요', w: { 가벼운: 3, 따뜻한: 2, 위로: 3 } },
      { label: '뭔가 자극이 필요해요', w: { 자극: 3, 스릴러: 2, 미스터리: 2 } },
      { label: '조용히 곱씹고 싶어요', w: { 사색: 3, 서정적: 2, 문장이좋은: 2 } },
      { label: '머리를 쓰고 싶어요', w: { 지적: 3, 인문: 2, 과학: 2 } },
    ],
  },
  {
    id: 'time', q: '주로 언제 읽나요?',
    opts: [
      { label: '출퇴근 20분', w: { _pagesMax: 300, 가벼운: 1 } },
      { label: '잠들기 전', w: { _pagesMax: 280, 따뜻한: 1, 사색: 1 } },
      { label: '주말에 통으로', w: { _pagesMin: 380, 지적: 1 } },
      { label: '틈날 때 조금씩', w: { _essay: 3 } },
    ],
  },
  {
    id: 'like', q: '책에서 가장 좋아하는 건?',
    opts: [
      { label: '인물의 감정', w: { 감정: 3, 문학: 2, 한국소설: 1 } },
      { label: '문장과 분위기', w: { 문장이좋은: 3, 서정적: 3, 사색: 1 } },
      { label: '사실과 지식', w: { 지적: 3, 과학: 2, 인문: 2 } },
      { label: '반전과 사건', w: { 자극: 3, 스릴러: 2, 미스터리: 2 } },
    ],
  },
  {
    id: 'hate', q: '이건 좀 피하고 싶어요',
    opts: [
      { label: '무겁고 우울한 건 싫어요', w: {}, ban: { 무거운: 1 } },
      { label: '두꺼운 책은 부담돼요', w: {}, ban: { _thick: 1 } },
      { label: '번역투가 어색해요', w: {}, ban: { _foreign: 1 } },
      { label: '딱히 없어요, 다 좋아요', w: {} },
    ],
  },
];
