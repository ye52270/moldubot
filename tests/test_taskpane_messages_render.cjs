const test = require('node:test');
const assert = require('node:assert/strict');

const messagesModulePath = '../clients/outlook-addin/taskpane.messages.js';

function loadMessagesModule() {
  global.window = {};
  delete require.cache[require.resolve(messagesModulePath)];
  return require(messagesModulePath);
}

test('taskpane messages renders assistant markdown emphasis', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const html = instance.buildMessageHtml('assistant', '핵심은 **중요 키워드** 입니다.', {});
  assert.equal(html.includes('rich-body'), true);
  assert.equal(html.includes('<strong>중요 키워드</strong>'), true);
});

test('taskpane messages renders markdown links as anchors', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const html = instance.buildMessageHtml('assistant', '1. [테스트 제목](https://example.com/mail/1)\n- 요약 문장', {});
  assert.equal(html.includes('href="https://example.com/mail/1"'), true);
  assert.equal(html.includes('target="_blank"'), true);
  assert.equal(html.includes('rel="noopener noreferrer"'), true);
});

test('taskpane messages renders markdown links with escaped brackets in title', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const html = instance.buildMessageHtml(
    'assistant',
    '2. [\\[SK브로드밴드\\] 조건부 액세스 정책 설정 안내 드립니다.](https://outlook.live.com/owa/?ItemID=abc)',
    {}
  );
  assert.equal(html.includes('href="https://outlook.live.com/owa/?ItemID=abc"'), true);
  assert.equal(html.includes('[SK브로드밴드] 조건부 액세스 정책 설정 안내 드립니다.'), true);
});

test('taskpane messages maps moldubot_mid link to evidence open action', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const html = instance.buildMessageHtml(
    'assistant',
    '1. [제목](https://outlook.live.com/owa/?ItemID=abc&moldubot_mid=mid-123%3D%3D)',
    {}
  );
  assert.equal(html.includes('class="rich-link evidence-open-btn"'), true);
  assert.equal(html.includes('data-action="open-evidence-mail"'), true);
  assert.equal(html.includes('data-message-id="mid-123=="'), true);
  assert.equal(html.includes('data-web-link="https://outlook.live.com/owa/?ItemID=abc"'), true);
});

test('taskpane messages renders scope status chip for assistant metadata', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const html = instance.buildMessageHtml('assistant', '요약 결과입니다.', {
    scope_label: '전체 사서함',
    scope_reason: '선택 메일에 고정하지 않고 전체 사서함에서 검색합니다.',
  });
  assert.equal(html.includes('scope-status-chip'), true);
  assert.equal(html.includes('범위: 전체 사서함'), true);
});

test('taskpane messages does not expose legacy streaming methods', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  assert.equal(typeof instance.beginStreamingAssistantMessage, 'undefined');
  assert.equal(typeof instance.appendStreamingToken, 'undefined');
  assert.equal(typeof instance.finalizeStreamingAssistantMessage, 'undefined');
});

test('taskpane messages renders markdown table and divider', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const input = [
    '### 기본 정보',
    '',
    '| 항목 | 내용 |',
    '|---|---|',
    '| 최종 발신자 | 홍길동 |',
    '| 날짜 | 2026-03-01 |',
    '',
    '---',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('class="md-table"'), true);
  assert.equal(html.includes('<th>항목</th>'), true);
  assert.equal(html.includes('<td>홍길동</td>'), true);
  assert.equal(html.includes('rich-divider'), true);
});

test('taskpane messages decodes escaped newlines in assistant text', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const html = instance.buildMessageHtml('assistant', '### 제목\\n\\n- 항목1\\n- 항목2', {});
  assert.equal(html.includes('rich-heading'), true);
  assert.equal(html.includes('<ul class="rich-list">'), true);
});

test('taskpane messages parses compact markdown without spaces', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = '#제목\n1.항목A\n2.항목B';
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('rich-heading'), true);
  assert.equal(html.includes('<ol class="rich-list ordered">'), true);
  assert.equal(html.includes('<span class="rich-ol-title">항목A</span>'), true);
});

test('taskpane messages keeps ordered numbering when sub-lines exist', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = '1.항목A\n- 설명A\n2.항목B\n- 설명B\n3.항목C';
  const html = instance.buildMessageHtml('assistant', input, {});
  const orderedListCount = (html.match(/<ol class=\"rich-list ordered\">/g) || []).length;
  const titleCount = (html.match(/class=\"rich-ol-title\"/g) || []).length;
  assert.equal(orderedListCount, 1);
  assert.equal(titleCount, 3);
  assert.equal(html.includes('class="rich-subline">- 설명A</div>'), true);
});

test('taskpane messages keeps ordered numbering across blank lines', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = '1.첫 항목\n- 설명\n\n2.둘째 항목\n- 설명\n\n3.셋째 항목';
  const html = instance.buildMessageHtml('assistant', input, {});
  const orderedListCount = (html.match(/<ol class=\"rich-list ordered\">/g) || []).length;
  const titleCount = (html.match(/class=\"rich-ol-title\"/g) || []).length;
  assert.equal(orderedListCount, 1);
  assert.equal(titleCount, 3);
});

test('taskpane messages skips mail metadata line in mail list body', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = [
    '### 📨 메일 목록',
    '1. 제목: 테스트 메일',
    '발신자: 홍길동 수신일: 2026-03-02 링크: [메일 보기](https://example.com)',
    '- 요약 항목',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('발신자:'), false);
  assert.equal(html.includes('수신일:'), false);
  assert.equal(html.includes('<span class="rich-ol-title">제목: 테스트 메일</span>'), true);
});

test('taskpane messages splits inline mail metadata into separate lines and removes link', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = [
    '### 🔎 메일 목록',
    '1. 주제: 테스트 제목',
    '보낸 사람: 박제영 수신일: 2026-02-14 요약: 테스트 요약입니다. [메일 링크](https://outlook.live.com/owa/?ItemID=abc)',
    'https://outlook.live.com/owa/?ItemID=abc&viewmodel=ReadMessageItem',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('보낸 사람: 박제영'), true);
  assert.equal(html.includes('수신일: 2026-02-14'), true);
  assert.equal(html.includes('요약: 테스트 요약입니다.'), true);
  assert.equal(html.includes('[메일 링크]'), false);
  assert.equal(html.includes('outlook.live.com/owa/?ItemID=abc'), false);
});

test('taskpane messages applies major summary heading class', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const html = instance.buildMessageHtml('assistant', '## 📌 주요 내용\n- 항목1', {});
  assert.equal(html.includes('class="rich-heading major-summary-heading"'), true);
});

test('taskpane messages renders evidence title with highlighted style and emoji', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '테스트 메일',
        received_date: '2026-03-02T00:00:00Z',
        sender_names: '홍길동',
        web_link: 'https://outlook.office.com/mail/m-1',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('📬 근거 메일'), false);
  assert.equal(html.includes('class="evidence-title rich-heading major-summary-heading"'), false);
});

test('taskpane messages hides evidence list for current mail query_type', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    query_type: 'current_mail',
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '현재메일 제목',
        received_date: '2026-03-04T01:00:00Z',
        sender_names: '박제영',
        web_link: 'https://outlook.office.com/mail/m-1',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('📬 근거 메일'), false);
  assert.equal(html.includes('evidence-block'), false);
});

test('taskpane messages renders executive brief card from answer_format core issue block', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '핵심 문제 요약' },
        { type: 'paragraph', text: '계정 보안 설정 변경으로 즉시 확인이 필요합니다.' },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '보안 알림 메일',
        received_date: '2026-03-04T01:00:00Z',
        sender_names: 'Microsoft 365',
        web_link: 'https://outlook.office.com/mail/m-1',
      },
    ],
  };

  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('executive-brief-card'), true);
  assert.equal(html.includes('한 줄 결론'), true);
  assert.equal(html.includes('위험도'), false);
  assert.equal(html.includes('inline-evidence-popover'), true);
  assert.equal(html.includes('inline-evidence-subject'), true);
});

test('taskpane messages renders code review quality badges when metadata is present', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    code_review_quality: {
      enabled: true,
      critic_used: true,
      revise_applied: true,
      web_source_count: 2,
    },
  };
  const html = instance.buildMessageHtml('assistant', '## 코드 리뷰\n```jsp\n<input />\n```', metadata);
  assert.equal(html.includes('quality-badge-row'), true);
  assert.equal(html.includes('Critic 검증'), true);
  assert.equal(html.includes('Revise 적용'), true);
  assert.equal(html.includes('출처 2건'), true);
});

test('taskpane messages adds inline evidence popover to major ordered summary items', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['프로필 변경 감지', '비밀번호 변경 권장'] },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '보안 알림 메일',
        received_date: '2026-03-04T01:00:00Z',
        sender_names: 'Microsoft 365',
        web_link: 'https://outlook.office.com/mail/m-1',
      },
    ],
  };

  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  const popoverCount = (html.match(/inline-evidence-popover/g) || []).length;
  assert.equal(popoverCount >= 2, true);
  assert.equal(html.includes('근거 메일</div>'), true);
  assert.equal(html.includes('근거 메일 · 프로필 변경 감지'), false);
});

test('taskpane messages inline evidence includes quote location and related mail evidence', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['Chrome 정책 리디렉션 검토 필요'] },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: 'Tenant Restriction 검토',
        received_date: '2026-03-04T01:00:00Z',
        sender_names: '박정호',
      },
    ],
    major_point_evidence: [
      {
        point: 'Chrome 정책 리디렉션 검토 필요',
        mail_quote: 'Chrome에서 특정 URL을 Edge로 리디렉션하는 정책 검토가 필요합니다.',
        mail_location: '본문 1단락',
        related_mails: [
          {
            message_id: 'm-2',
            subject: '브로드밴드 Web DRM 원인 분석',
            received_date: '2026-02-01',
            sender_names: '박정호',
            snippet: 'Chrome 정책 변경 이후 URL 리디렉션 이슈가 확인되었습니다.',
            web_link: 'https://outlook.office.com/mail/m-2',
          },
        ],
      },
    ],
  };

  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('메일 근거 문구'), true);
  assert.equal(html.includes('본문 1단락'), true);
  assert.equal(html.includes('관련 메일 근거'), false);
  assert.equal(html.includes('브로드밴드 Web DRM 원인 분석'), true);
  assert.equal(html.includes('기술 근거 · 웹 출처'), false);
  assert.equal(html.includes('inline-evidence-popover-compact'), true);
  assert.equal(html.includes('data-action="section-toggle"'), true);
});

test('taskpane messages maps inline evidence by major item index when title match is weak', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['파이썬', '취합'] },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-0',
        subject: '공통 근거 메일',
        received_date: '2026-03-04T01:00:00Z',
        sender_names: '공통',
        web_link: 'https://outlook.office.com/mail/m-0',
      },
    ],
    major_point_evidence: [
      {
        point: '파이썬 API 구현',
        related_mails: [
          {
            message_id: 'm-11',
            subject: '파이썬 관련 메일',
            received_date: '2026-03-06',
            sender_names: '개발팀',
            web_link: 'https://outlook.office.com/mail/m-11',
          },
        ],
      },
      {
        point: '취합자료 요청',
        related_mails: [
          {
            message_id: 'm-22',
            subject: '취합 관련 메일',
            received_date: '2026-03-05',
            sender_names: '운영팀',
            web_link: 'https://outlook.office.com/mail/m-22',
          },
        ],
      },
    ],
  };

  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('파이썬 관련 메일'), true);
  assert.equal(html.includes('취합 관련 메일'), true);
  assert.equal(html.includes('공통 근거 메일'), false);
});

test('taskpane messages wraps summary headings into section cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [['날짜', '2026-03-04']] },
        { type: 'heading', level: 2, text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['항목 A'] },
        { type: 'heading', level: 2, text: '✅ 조치 필요 사항' },
        { type: 'unordered_list', items: ['조치 1'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('summary-section section-basic'), true);
  assert.equal(html.includes('summary-section section-major'), true);
  assert.equal(html.includes('summary-section section-action'), true);
});

test('taskpane messages strips leading heading emoji inside section cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '📋 기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [['날짜', '2026-03-04']] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('summary-section section-basic'), true);
  assert.equal(html.includes('>📋 기본 정보<'), false);
  assert.equal(html.includes('>기본 정보<'), true);
});

test('taskpane messages renders recipient role section as badge cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'standard_summary',
      blocks: [
        { type: 'heading', level: 3, text: '👥 수신자 역할' },
        { type: 'ordered_list', items: ['김태호 — 문제 해결 확인자', '박정호 — 발생 시간 확인자', '박제영 — LDAP 확인 요청자', '김양수 — 참여 필요'] },
        { type: 'unordered_list', items: ['근거: 저희쪽에서는 작업한 내용이 없습니다.', '근거: 전주 수요일부터 문제 발생 인지.', '근거: LDAP 호출되는지 확인 부탁드립니다.', '근거: 전체 회신으로 메일 부탁 요청'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('summary-section section-recipient-role'), true);
  assert.equal(html.includes('recipient-role-list'), true);
  assert.equal(html.includes('recipient-role-badge tone-confirm'), true);
  assert.equal(html.includes('recipient-role-badge tone-time'), true);
  assert.equal(html.includes('recipient-role-badge tone-request'), true);
  assert.equal(html.includes('recipient-role-badge tone-participation'), true);
  assert.equal(html.includes('LDAP 호출되는지 확인 부탁드립니다.'), true);
});

test('taskpane messages ignores divider paragraph for executive brief card', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', level: 2, text: '핵심 문제 요약' },
        { type: 'paragraph', text: '요약 본문입니다.' },
        { type: 'paragraph', text: '---' },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  const executiveCount = (html.match(/executive-brief-card/g) || []).length;
  assert.equal(executiveCount, 1);
  assert.equal(html.includes('<p class="executive-brief-summary">---</p>'), false);
});

test('taskpane messages renders HIL confirm block when metadata.confirm.required is true', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    confirm: {
      required: true,
      thread_id: 'thread-hitl-1',
      confirm_token: 'interrupt-1',
      actions: [
        {
          name: 'create_outlook_todo',
          description: 'ToDo 생성 승인 요청',
        },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '승인 필요', metadata);
  assert.equal(html.includes('실행 승인 필요'), true);
  assert.equal(html.includes('Outlook 할 일 등록'), true);
  assert.equal(html.includes('data-role="hitl-confirm-progress"'), true);
  assert.equal(html.includes('data-action="hitl-confirm-approve"'), true);
  assert.equal(html.includes('data-action="hitl-confirm-reject"'), true);
  assert.equal(html.includes('data-hitl-action-name="create_outlook_todo"'), true);
});

test('taskpane messages hides evidence list for todo HIL confirm message', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    confirm: {
      required: true,
      thread_id: 'thread-hitl-2',
      confirm_token: 'interrupt-2',
      actions: [
        {
          name: 'create_outlook_todo',
          description: 'ToDo 생성 승인 요청',
          args: { title: '디자인 검토', due_date: '2026-03-05' },
        },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '테스트 메일',
        received_date: '2026-03-02T00:00:00Z',
        sender_names: '홍길동',
        web_link: 'https://outlook.office.com/mail/m-1',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '승인 필요', metadata);
  assert.equal(html.includes('📬 근거 메일'), false);
});

test('taskpane messages renders elapsed divider label', () => {
  global.document = { querySelector: () => null };
  const moduleRef = loadMessagesModule();
  const inserts = [];
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 500,
    insertAdjacentHTML: function (_where, html) { inserts.push(html); },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addElapsedDivider(63000);
  assert.equal(inserts.length, 1);
  assert.equal(inserts[0].includes('1m 3s'), true);
  assert.equal(inserts[0].includes('--- 1m 3s ---'), false);
  assert.equal(inserts[0].includes('msg-elapsed'), true);
});

test('taskpane messages splits collapsed divider and heading tokens', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const input = '이메일 요약---#기본 정보';
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('rich-divider'), true);
  assert.equal(html.includes('class="rich-heading"'), true);
});

test('taskpane messages prefers answer_format blocks when provided', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'summary',
      blocks: [
        { type: 'heading', level: 2, text: '이메일 요약' },
        { type: 'ordered_list', items: ['첫 항목', '둘째 항목'] },
        { type: 'paragraph', text: '마지막 문단' },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', 'fallback text', metadata);
  assert.equal(html.includes('<h2 class="rich-heading">이메일 요약</h2>'), true);
  assert.equal(html.includes('<ol class="rich-list ordered">'), true);
  assert.equal(html.includes('<span class="rich-ol-title">첫 항목</span>'), true);
  assert.equal(html.includes('fallback text'), false);
});

test('taskpane messages keeps numbering across fragmented answer_format ordered lists', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'current_mail',
      blocks: [
        { type: 'heading', level: 3, text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['첫 항목'] },
        { type: 'unordered_list', items: ['보조 설명'] },
        { type: 'ordered_list', items: ['둘째 항목'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('major-summary-list'), true);
  assert.equal(html.includes('첫 항목'), true);
  assert.equal(html.includes('둘째 항목'), true);
  assert.equal(html.includes('보조 설명'), true);
});

test('taskpane messages renders current_mail plain ordered list as major summary cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'current_mail',
      blocks: [
        { type: 'ordered_list', items: ['요약 1', '요약 2', '요약 3'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('major-summary-list'), true);
  assert.equal(html.includes('major-summary-index'), true);
  assert.equal(html.includes('major-summary-subline'), false);
  assert.equal(html.includes('<ol class="rich-list ordered">'), false);
});

test('taskpane messages renders current_mail plain unordered list as major summary cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'current_mail',
      blocks: [
        { type: 'unordered_list', items: ['현재 메일 핵심 이슈 한 줄'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('major-summary-list'), true);
  assert.equal(html.includes('major-summary-index'), true);
  assert.equal(html.includes('<ul class="rich-list">'), false);
});

test('taskpane messages wraps current_mail freeform bullet text into summary section card', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    query_type: 'current_mail',
    scope_label: '현재 선택 메일',
  };
  const answer = [
    '- XML 파일 송부 완료 — 프로젝트는 4월 초 오픈 예정이다.',
    '- 추가 정보 필요 시 요청 가능성 언급 — 개발 과정 소통 강조.',
    '- 추가 정보 요청 가능성 검토 / 담당:신준성 / 기한:미상',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', answer, metadata);
  assert.equal(html.includes('summary-section section-major'), true);
  assert.equal(html.includes('major-summary-heading'), true);
  assert.equal(html.includes('주요 문의사항'), true);
  assert.equal(html.includes('<ul class="rich-list">'), true);
});

test('taskpane messages maps meeting suggestion headings to boxed summary sections', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'meeting_suggestion',
      blocks: [
        { type: 'heading', level: 3, text: '회의 안건(요약)' },
        { type: 'unordered_list', items: ['Tenant Restriction 논의'] },
        { type: 'heading', level: 3, text: '논의할 주요 내용' },
        { type: 'unordered_list', items: ['Chrome 접근 Redirect 정책 점검'] },
        { type: 'heading', level: 3, text: '참석자 제안' },
        { type: 'unordered_list', items: ['참석 인원: 4명'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('summary-section section-executive'), true);
  assert.equal(html.includes('summary-section section-major'), true);
  assert.equal(html.includes('summary-section section-basic'), true);
});

test('taskpane messages maps calendar suggestion headings to boxed summary sections', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'calendar_suggestion',
      blocks: [
        { type: 'heading', level: 3, text: '일정 안건(요약)' },
        { type: 'unordered_list', items: ['[일정] Tenant Restriction 방안 논의'] },
        { type: 'heading', level: 3, text: '논의할 주요 내용' },
        { type: 'ordered_list', items: ['정책 적용 범위 확인'] },
        { type: 'heading', level: 3, text: '참석자 제안' },
        { type: 'unordered_list', items: ['이상수 <ssl@skcc.com>'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('summary-section section-executive'), true);
  assert.equal(html.includes('summary-section section-major'), true);
  assert.equal(html.includes('summary-section section-basic'), true);
});

test('taskpane messages renders tech issue section with keyword and detail popover', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'general',
      blocks: [
        { type: 'heading', level: 3, text: '🛠 기술 이슈' },
        { type: 'ordered_list', items: ['결재 상태정보변경 API 호출이 되지 않아 확인 요청.'] },
      ],
    },
    context_enrichment: {
      tech_issue_clusters: [
        {
          summary: '결재 상태정보변경 API 호출이 되지 않아 확인 요청.',
          keywords: ['API', '연동', '오류'],
          issue_type: '연동/API 이슈',
          related_mails: [
            {
              message_id: 'm-1',
              subject: 'EAI 연동 API 호출 오류',
              received_date: '2026-02-25',
              sender_names: '박제영',
              web_link: 'https://outlook.live.com/owa/?ItemID=m-1',
              snippet: '결재 상태정보변경 API 호출이 되지 않아 확인 요청.',
            },
          ],
        },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('Keyword: API, 연동, 오류'), true);
  assert.equal(html.includes('유형: 연동/API 이슈'), true);
  assert.equal(html.includes('기술 근거 상세'), true);
  assert.equal(html.includes('EAI 연동 API 호출 오류'), true);
});

test('taskpane messages renders answer_format table and quote blocks', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'current_mail',
      blocks: [
        { type: 'table', headers: ['항목', '내용'], rows: [['발신자', '홍길동']] },
        { type: 'quote', text: '긴급 확인 필요' },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('class="md-table"'), true);
  assert.equal(html.includes('<td>홍길동</td>'), true);
  assert.equal(html.includes('class="rich-quote"'), true);
  assert.equal(html.includes('긴급 확인 필요'), true);
});

test('taskpane messages ignores noise paragraph tokens in answer_format blocks', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'summary',
      blocks: [
        { type: 'paragraph', text: '---' },
        { type: 'paragraph', text: '#' },
        { type: 'paragraph', text: '정상 문장' },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('rich-divider'), true);
  assert.equal(html.includes('<p class="rich-paragraph">#</p>'), false);
  assert.equal(html.includes('정상 문장'), true);
});

test('taskpane messages skips table delimiter-like row in answer_format table', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'summary',
      blocks: [
        {
          type: 'table',
          headers: ['항목', '내용'],
          rows: [['---', '---'], ['최종 발신자', 'izocuna@sk.com']],
        },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('<td>---</td>'), false);
  assert.equal(html.includes('izocuna@sk.com'), true);
});

test('taskpane messages skips empty markdown table with only header', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  const input = [
    '| 항목 | 내용 |',
    '|---|---|',
    '',
    '다음 문단',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', input, {});
  assert.equal(html.includes('class="md-table"'), false);
  assert.equal(html.includes('다음 문단'), true);
});

test('taskpane messages fills missing value for one-cell table row', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'summary',
      blocks: [
        {
          type: 'table',
          headers: ['항목', '내용'],
          rows: [['최종 발신자']],
        },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '', metadata);
  assert.equal(html.includes('<td>최종 발신자</td>'), true);
  assert.equal(html.includes('<td>-</td>'), true);
});

test('taskpane messages ignores table block with delimiter-only headers', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
  });

  const metadata = {
    answer_format: {
      version: 'v1',
      format_type: 'summary',
      blocks: [
        { type: 'table', headers: ['---'], rows: [['최종 발신자', 'izocuna@sk.com']] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', 'fallback', metadata);
  assert.equal(html.includes('class="md-table"'), false);
});

test('taskpane messages disables report confirm controls while generating', () => {
  const moduleRef = loadMessagesModule();
  const controls = [{ disabled: false }, { disabled: false }, { disabled: false }];
  const chatArea = {
    querySelectorAll(selector) {
      assert.equal(selector.includes('report-generate-confirm'), true);
      return controls;
    },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.disableReportConfirmControls();
  assert.equal(controls.every((node) => node.disabled === true), true);
});

test('taskpane messages adds weekly report confirm card with offset selector', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addWeeklyReportConfirmCard();
  assert.equal(insertedHtml.includes('weekly-offset-select'), true);
  assert.equal(insertedHtml.includes('weekly-report-generate-confirm'), true);
});

test('taskpane messages reads selected weekly offset from confirm card', () => {
  const moduleRef = loadMessagesModule();
  const fakeChatArea = {
    querySelector(selector) {
      if (selector === '[data-role="weekly-offset-select"]') {
        return { value: '3' };
      }
      return null;
    },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  assert.equal(instance.getSelectedWeeklyOffset(), 3);
});

test('taskpane messages renders meeting room building step card', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingRoomBuildingCard(['project-107']);
  assert.equal(insertedHtml.includes('1단계'), false);
  assert.equal(insertedHtml.includes('meeting-room-card-title">건물'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-building-select"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-building-change"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-book-cancel"'), true);
});

test('taskpane messages renders meeting room floor step card', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingRoomFloorCard('project-107', [14]);
  assert.equal(insertedHtml.includes('2단계'), false);
  assert.equal(insertedHtml.includes('meeting-room-card-title">층'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-floor-select"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-floor-change"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-back-to-building"'), true);
});

test('taskpane messages renders meeting room detail step card', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingRoomDetailCard('project-107', 14, [{ room_name: '1402', capacity: 8 }]);
  assert.equal(insertedHtml.includes('3단계'), false);
  assert.equal(insertedHtml.includes('meeting-room-card-title">회의실'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-room-select"'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-attendee-input"'), false);
  assert.equal(insertedHtml.includes('data-action="meeting-room-room-change"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-back-to-floor"'), true);
});

test('taskpane messages renders meeting room schedule card', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingRoomScheduleCard('project-107', 14, '1402');
  assert.equal(insertedHtml.includes('meeting-room-card-title">일정'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-room-select" value="1402"'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-date-input"'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-attendee-input"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-back-to-room"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-book-confirm"'), true);
});

test('taskpane messages renders meeting room schedule suggestion selectors', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingRoomScheduleCard('sku-tower', 17, '1702-A', {
    date: '2026-03-04',
    start_time: '10:00',
    end_time: '11:00',
    time_candidates: [
      { date: '2026-03-04', start_time: '10:00', end_time: '11:00', label: '2026-03-04 10:00-11:00' },
      { date: '2026-03-04', start_time: '14:00', end_time: '15:00', label: '2026-03-04 14:00-15:00' },
    ],
    room_candidates: [
      { building: 'sku-tower', floor: 17, room_name: '1702-A', label: 'sku-tower 17층 1702-A' },
      { building: 'sku-tower', floor: 17, room_name: '1705', label: 'sku-tower 17층 1705' },
    ],
  });
  assert.equal(insertedHtml.includes('data-action="meeting-room-time-candidate-change"'), true);
  assert.equal(insertedHtml.includes('data-action="meeting-room-candidate-change"'), true);
  assert.equal(insertedHtml.includes('data-role="meeting-room-display"'), true);
});

test('taskpane messages renders meeting booking ready card with event id', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addMeetingBookingReadyCard('회의실 예약 완료', 'evt-123');
  assert.equal(insertedHtml.includes('data-action="meeting-open-event"'), true);
  assert.equal(insertedHtml.includes('data-event-id="evt-123"'), true);
  assert.equal(insertedHtml.includes('일정 열기'), true);
});

test('taskpane messages renders todo ready card without open shortcut', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addTodoReadyCard('할 일 등록 완료', '디자인 검토', '2026-03-05', 'https://outlook.live.com/tasks/item/task-1', 'task-1');
  assert.equal(insertedHtml.includes('data-action="todo-open-task"'), false);
  assert.equal(insertedHtml.includes('할 일 열기'), false);
  assert.equal(insertedHtml.includes('디자인 검토'), true);
});

test('taskpane messages normalizes todo ready card title message when answer has action-item markdown', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addTodoReadyCard('## 액션 아이템1. 액션 아이템을 확인하지 못했습니다.', '메일 접속 차단 설정 준비', '2026-03-05', '', 'task-2');
  assert.equal(insertedHtml.includes('할 일 등록이 완료되었습니다.'), true);
  assert.equal(insertedHtml.includes('## 액션 아이템'), false);
  assert.equal(insertedHtml.includes('액션 아이템을 확인하지 못했습니다'), false);
  assert.equal(insertedHtml.includes('disabled'), false);
});

test('taskpane messages todo ready card uses provided summarized mail-based title', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addTodoReadyCard('무시될 문구', '[ESG Data Hub 연동 관련] 메일 접속 차단 설정 준비', '2026-03-05', 'https://outlook.live.com/tasks/item/task-1', 'task-3');
  assert.equal(insertedHtml.includes('할 일 등록이 완료되었습니다.'), true);
  assert.equal(insertedHtml.includes('[ESG Data Hub 연동 관련] 메일 접속 차단 설정 준비'), true);
});

test('taskpane messages renders promise summary list as table', () => {
  const moduleRef = loadMessagesModule();
  const nodes = {
    '[data-role="promise-summary-list"]': { innerHTML: '' },
  };
  const chatArea = {
    querySelector(selector) {
      return nodes[selector] || null;
    },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  instance.renderPromiseSummaryList([
    {
      project_number: '30127872-D001',
      project_name: 'SKB 24년 Domino Upgrade',
      execution_total: 198900000,
      final_cost_total: 199118400,
    },
  ]);

  const rendered = nodes['[data-role="promise-summary-list"]'].innerHTML;
  assert.equal(rendered.includes('class="rich-table"'), true);
  assert.equal(rendered.includes('프로젝트 번호'), true);
  assert.equal(rendered.includes('data-action="promise-summary-select"'), true);
  assert.equal(rendered.includes('data-project-name="SKB 24년 Domino Upgrade"'), true);
  assert.equal(rendered.includes('30127872-D001'), true);
});

test('taskpane messages renders promise monthly breakdown as category table', () => {
  const moduleRef = loadMessagesModule();
  const nodes = {
    '[data-role="promise-summary-text"]': { textContent: '' },
    '[data-role="promise-monthly-list"]': { innerHTML: '' },
  };
  const chatArea = {
    querySelector(selector) {
      return nodes[selector] || null;
    },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
  });

  instance.renderPromiseMonthlyBreakdown({
    project_number: '30127872-D001',
    project_name: 'SKB 24년 Domino Upgrade',
    execution_total: 198900000,
    final_cost_total: 199118400,
    monthly_breakdown: [
      {
        month: 1,
        labor_cost: 10000000,
        outsourcing_cost: 2000000,
        material_cost: 3000000,
        expense_cost: 4000000,
        execution_total: 19000000,
      },
    ],
  });

  const summaryRendered = nodes['[data-role="promise-summary-text"]'].innerHTML;
  const rendered = nodes['[data-role="promise-monthly-list"]'].innerHTML;
  assert.equal(summaryRendered.includes('rich-table'), true);
  assert.equal(summaryRendered.includes('30127872-D001 · SKB 24년 Domino Upgrade'), true);
  assert.equal(summaryRendered.includes('198,900,000원'), true);
  assert.equal(summaryRendered.includes('199,118,400원'), true);
  assert.equal(rendered.includes('rich-table'), true);
  assert.equal(rendered.includes('인건비'), true);
  assert.equal(rendered.includes('외주비'), true);
  assert.equal(rendered.includes('자료비'), true);
  assert.equal(rendered.includes('경비'), true);
});

test('taskpane messages promise view mode hides top mode buttons', () => {
  const moduleRef = loadMessagesModule();
  const nodes = {
    '[data-role="promise-mode-actions"]': { style: {} },
    '[data-role="promise-view-section"]': { style: {} },
    '[data-role="promise-view-step-list"]': { style: {} },
    '[data-role="promise-view-step-detail"]': { style: {} },
    '[data-role="promise-register-section"]': { style: {} },
  };
  const chatArea = {
    querySelector(selector) {
      return nodes[selector] || null;
    },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? chatArea : null),
    escapeHtml: (value) => String(value || ''),
  });

  instance.setPromiseMode('view');
  assert.equal(nodes['[data-role="promise-mode-actions"]'].style.display, 'none');
  assert.equal(nodes['[data-role="promise-view-section"]'].style.display, '');
  assert.equal(nodes['[data-role="promise-view-step-list"]'].style.display, '');
  assert.equal(nodes['[data-role="promise-view-step-detail"]'].style.display, 'none');

  instance.setPromiseMode('none');
  assert.equal(nodes['[data-role="promise-mode-actions"]'].style.display, '');
  assert.equal(nodes['[data-role="promise-view-section"]'].style.display, 'none');
});

test('taskpane messages renders promise card with list/detail steps and back button', () => {
  const moduleRef = loadMessagesModule();
  let insertedHtml = '';
  const fakeChatArea = {
    scrollTop: 0,
    scrollHeight: 0,
    insertAdjacentHTML(_position, html) {
      insertedHtml = html;
    },
    querySelector() { return null; },
  };
  const instance = moduleRef.create({
    byId: (id) => (id === 'chatArea' ? fakeChatArea : null),
    escapeHtml: (value) => String(value || ''),
  });
  instance.addPromiseBudgetCard();
  assert.equal(insertedHtml.includes('data-role="promise-view-step-list"'), true);
  assert.equal(insertedHtml.includes('data-role="promise-view-step-detail"'), true);
  assert.equal(insertedHtml.includes('data-action="promise-detail-back"'), true);
});

test('taskpane messages renders next action recommendation buttons', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    next_actions: [
      {
        action_id: 'draft_reply',
        title: '이상수님께 회신 초안 작성',
        description: '현재 이슈 기준 회신 메일 초안 생성',
        query: '현재메일 기준으로 이상수님에게 보낼 회신 초안 작성해줘',
        priority: 'high',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('이어서 할 수 있어요'), true);
  assert.equal(html.includes('data-action="next-action-run"'), true);
  assert.equal(html.includes('data-action-id="draft_reply"'), true);
  assert.equal(html.includes('priority-high'), true);
});

test('taskpane messages renders reply draft open button when metadata provided', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    reply_draft: {
      enabled: true,
      body: '회신 초안 본문',
      button_label: '답장하기',
    },
  };
  const html = instance.buildMessageHtml('assistant', '회신 초안', metadata);
  assert.equal(html.includes('reply-mail-body-card'), true);
  assert.equal(html.includes('data-action="reply-draft-open"'), true);
  assert.equal(html.includes('답장하기'), true);
});

test('taskpane messages strips reply draft heading text from body and draft payload', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const draftText = '회신 메일 본문 초안\n\n안녕하세요, 공재환님.\n확인 감사합니다.';
  const metadata = {
    reply_draft: {
      enabled: true,
      body: draftText,
      button_label: '답변 메일 보내기',
    },
  };
  const html = instance.buildMessageHtml('assistant', draftText, metadata);
  assert.equal(html.includes('회신 메일 본문 초안'), false);
  assert.equal(html.includes('안녕하세요, 공재환님.'), true);
  assert.equal(html.includes('data-draft-body="안녕하세요, 공재환님.\n확인 감사합니다."'), true);
});

test('taskpane messages strips prefacing summary and code fence from reply draft body', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const draftText = [
    '메일 내용을 확인했습니다. 정유정이 강민창 매니저에게 보낸 메일입니다.',
    '',
    '```',
    '매니저님,',
    '',
    '정유정 팀의 제안에 대해 검토했습니다.',
    '글자 테두리를 하얀색으로 구분하는 방안은 좋은 솔루션입니다.',
    '',
    '감사합니다.',
    '```',
  ].join('\n');
  const metadata = {
    reply_draft: {
      enabled: true,
      body: draftText,
      button_label: '답변 메일 보내기',
    },
  };
  const html = instance.buildMessageHtml('assistant', draftText, metadata);
  assert.equal(html.includes('메일 내용을 확인했습니다'), false);
  assert.equal(html.includes('```'), false);
  assert.equal(html.includes('매니저님,'), true);
  assert.equal(html.includes('data-draft-body="매니저님,\n\n정유정 팀의 제안에 대해 검토했습니다.\n글자 테두리를 하얀색으로 구분하는 방안은 좋은 솔루션입니다.\n\n감사합니다."'), true);
});

test('taskpane messages renders reply draft as plain paragraphs without ordered-list template', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const draftText = [
    '메일 내용을 확인했습니다. 다음은 회신 본문입니다:',
    '',
    '```',
    '안녕하세요.',
    '',
    '1. 도메인 설정 검토',
    '2. 정책 호환성 검증',
    '',
    '감사합니다.',
    '```',
  ].join('\n');
  const metadata = {
    reply_draft: {
      enabled: true,
      body: draftText,
      button_label: '답변 메일 보내기',
    },
  };
  const html = instance.buildMessageHtml('assistant', draftText, metadata);
  assert.equal(html.includes('메일 내용을 확인했습니다'), false);
  assert.equal(html.includes('<ol class="rich-list ordered">'), false);
  assert.equal(html.includes('1. 도메인 설정 검토'), true);
  assert.equal(html.includes('2. 정책 호환성 검증'), true);
});

test('taskpane messages renders reply draft block before next actions block', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    reply_draft: {
      enabled: true,
      body: '회신 초안 본문',
      button_label: '답변 메일 보내기',
    },
    next_actions: [
      {
        action_id: 'search_related_mails',
        title: '관련 메일 추가 조회',
        description: '동일 이슈의 과거/연관 메일을 찾아 근거를 확장합니다.',
        query: '이 주제 관련 메일 최근순으로 5개 조회해줘',
        priority: 'high',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '회신 본문', metadata);
  const replyDraftIndex = html.indexOf('reply-draft-action-block');
  const nextActionsIndex = html.indexOf('next-actions-block');
  assert.equal(replyDraftIndex >= 0, true);
  assert.equal(nextActionsIndex >= 0, true);
  assert.equal(replyDraftIndex < nextActionsIndex, true);
});

test('taskpane messages extracts reply body from json-like reply draft payload', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const jsonPayload = JSON.stringify({
    format_type: 'general',
    title: '회신 메일 초안',
    answer: '',
    response_body: '안녕하세요, 공재환님.\\n\\n본문입니다.\\n\\n감사합니다.',
  });
  const metadata = {
    reply_draft: {
      enabled: true,
      body: jsonPayload,
      button_label: '답변 메일 보내기',
    },
  };
  const html = instance.buildMessageHtml('assistant', jsonPayload, metadata);
  assert.equal(html.includes('"format_type"'), false);
  assert.equal(html.includes('안녕하세요, 공재환님.'), true);
  assert.equal(html.includes('data-draft-body="안녕하세요, 공재환님.\n\n본문입니다.\n\n감사합니다."'), true);
});

test('taskpane messages renders reply tone picker block when metadata provided', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    reply_tone_picker: {
      enabled: true,
      base_query: '현재메일 기준으로 회신 초안 작성해줘',
    },
  };
  const html = instance.buildMessageHtml('assistant', '회신 톤을 선택해 주세요.', metadata);
  assert.equal(html.includes('reply-tone-picker-block'), true);
  assert.equal(html.includes('data-action="reply-tone-generate"'), true);
  assert.equal(html.includes('data-tone="formal"'), true);
  assert.equal(html.includes('data-tone="concise"'), true);
});

test('taskpane messages renders code block with language header in rich text', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const answer = [
    '## 코드 리뷰',
    '언어: python',
    '```python',
    'def login(user):',
    '    return user.is_authenticated',
    '```',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', answer, {});
  assert.equal(html.includes('rich-code-block'), true);
  assert.equal(html.includes('rich-code-head'), true);
  assert.equal(html.includes('Python'), true);
  assert.equal(html.includes('language-python'), true);
});

test('taskpane messages prefers rich markdown renderer when answer contains fenced code', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '코드 리뷰' },
        { type: 'ordered_list', items: ['```jsp'] },
      ],
    },
  };
  const answer = [
    '## 코드 리뷰',
    '```jsp',
    '<form id="loginForm"></form>',
    '```',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', answer, metadata);
  assert.equal(html.includes('rich-code-block'), true);
  assert.equal(html.includes('language-xml'), true);
  assert.equal(html.includes('JSP'), true);
  assert.equal(html.includes('<form id="loginForm"></form>'), true);
});

test('taskpane messages upgrades java fence to JSP when snippet contains JSP tags', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const answer = [
    '## 코드 리뷰',
    '```java',
    '<input id="<bean:write name="IDNAME"/>" />',
    '```',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', answer, {});
  assert.equal(html.includes('rich-code-head-lang">JSP<'), true);
  assert.equal(html.includes('language-xml'), true);
});

test('taskpane messages wraps code analysis and code review headings as summary sections', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const answer = [
    '## 코드 분석',
    '- 기능 요약: 로그인 UI',
    '',
    '## 코드 리뷰',
    '### 언어',
    '- JSP',
    '```jsp',
    '<input name="id" />',
    '```',
  ].join('\n');
  const html = instance.buildMessageHtml('assistant', answer, {});
  assert.equal(html.includes('summary-section section-code-analysis'), true);
  assert.equal(html.includes('summary-section section-code-review'), true);
  assert.equal(html.includes('rich-code-block'), true);
});

test('taskpane messages renders actions inline and does not render context tabs', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    context_enrichment: {
      reply_alert: {
        required: true,
        title: '회신 필요',
        description: '이상수님 문의 미답변 · 1일 경과',
        severity: 'medium',
      },
      thread_timeline: [
        { actor: '이상수', timestamp: '2026-02-25', label: '최초 문의' },
        { actor: '박정호', timestamp: '2026-02-26', label: '중간 답변' },
      ],
      stakeholders: [
        { name: '이상수', role: '요청자', evidence: '본문 @이상수' },
      ],
    },
    evidence_mails: [
      {
        message_id: 'm-1',
        subject: '근거 메일',
        received_date: '2026-03-04',
        sender_names: '박제영',
      },
    ],
    next_actions: [
      {
        title: '회신 초안 작성',
        description: '현재 이슈 기준 회신 초안',
        query: '회신 초안 작성해줘',
        priority: 'high',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('assistant-tabs'), false);
  assert.equal(html.includes('data-action="message-tab-select"'), false);
  assert.equal(html.includes('🔍 컨텍스트'), false);
  assert.equal(html.includes('next-actions-list'), true);
  assert.equal(html.includes('context-enrichment-block'), false);
  assert.equal(html.includes('스레드 타임라인'), false);
  assert.equal(html.includes('관계자'), false);
});

test('taskpane messages renders web source icon stack and popover list', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    web_sources: [
      {
        title: 'OpenAI Latency Optimization',
        url: 'https://platform.openai.com/docs/guides/latency-optimization',
        site_name: 'platform.openai.com',
        snippet: 'Streaming can improve perceived latency.',
        icon_text: 'P',
        favicon_url: 'https://platform.openai.com/favicon.ico',
      },
      {
        title: 'Copilot Suggested Prompts',
        url: 'https://learn.microsoft.com/en-us/microsoft-copilot-studio/configure-starter-prompts',
        site_name: 'learn.microsoft.com',
        snippet: 'Starter prompts can guide users.',
        icon_text: 'L',
      },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('web-source-popover'), true);
  assert.equal(html.includes('web-source-icon'), true);
  assert.equal(html.includes('web-source-icon-img'), true);
  assert.equal(html.includes('출처'), true);
  assert.equal(html.includes('OpenAI Latency Optimization'), true);
});

test('taskpane messages renders external info summary heading as major summary cards', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '외부 정보 요약' },
        { type: 'ordered_list', items: ['첫 번째 외부 문서', '두 번째 외부 문서'] },
        { type: 'unordered_list', items: ['요약: 핵심 원인 정리', '요약: 해결 가이드 정리'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('major-summary-list'), true);
  assert.equal(html.includes('major-summary-index'), true);
  assert.equal(html.includes('major-summary-card-sub'), true);
});

test('taskpane messages hides title section block without rendering summary mail hero', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '제목' },
        { type: 'paragraph', text: '이 문구는 본문에 직접 노출되면 안됩니다.' },
        { type: 'heading', text: '기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [
          ['최종 발신자', '박정호'],
          ['수신자', '이상수, 김태호'],
          ['날짜', '2026-02-26'],
        ] },
      ],
    },
    evidence_mails: [
      { subject: 'Tenant Restriction 방안', received_date: '2026-02-26', sender_names: '박정호' },
    ],
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('summary-mail-hero'), false);
  assert.equal(html.includes('이 문구는 본문에 직접 노출되면 안됩니다.'), false);
});

test('taskpane messages renders basic info as compact single-line meta', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [
          ['날짜', '2026-02-26 07:17Z'],
          ['최종 발신', 'izocuna'],
          ['수신자', '이상수, 김태호'],
          ['원본 발신', '박정호'],
          ['원본 문의 발신', '박정호'],
        ] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('basic-info-inline'), false);
  assert.equal(html.includes('basic-info-card'), true);
  assert.equal(html.includes('basic-info-row'), true);
  assert.equal(html.includes('2026-02-26 07:17Z'), true);
  assert.equal(html.includes('izocuna'), true);
  assert.equal(html.includes('이상수, 김태호'), true);
});

test('taskpane messages renders communication route timeline in basic info', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [
          ['날짜', '2026-03-09'],
          ['최종 발신자', '박제영 <izocuna@sk.com>'],
          ['수신자', '김태성 <tate.kim@skcc.com>'],
          ['커뮤니케이션 흐름', '2026-03-03::황규리=>서관석, unknown@partner.com%%2026-03-04::박제영=>김태성'],
        ] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('basic-info-route-timeline'), true);
  assert.equal(html.includes('basic-info-route-track'), true);
  assert.equal(html.includes('basic-info-route-node'), true);
  assert.equal(html.includes('basic-info-route-arrow'), true);
  assert.equal(html.includes('커뮤니케이션 흐름'), true);
  assert.equal(html.includes('황규리'), true);
  assert.equal(html.includes('→'), true);
  assert.equal(html.includes('03.03'), true);
  assert.equal(html.includes('03.04'), true);
  assert.equal(html.includes('unknown@partner.com'), true);
});

test('taskpane messages basic info uses korean name before email localpart', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '기본 정보' },
        { type: 'table', headers: ['항목', '내용'], rows: [
          ['날짜', '2026-03-05'],
          ['최종 발신자', '박정호/AT Infra팀/SKB (eva1397@sk.com)'],
          ['수신자', '박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK (izocuna@SKCC.COM)'],
          ['커뮤니케이션 흐름', '2026-03-05::박정호/AT Infra팀/SKB (eva1397@sk.com)=>박제영(PARK Jaeyoung)/AX Solution서비스5팀/SK (izocuna@SKCC.COM)'],
        ] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('박정호'), true);
  assert.equal(html.includes('박제영'), true);
  assert.equal(html.includes('izocuna → -'), false);
});

test('taskpane messages converts major unordered helper lines into card subtitle', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['핵심 항목 A', '핵심 항목 B'] },
        { type: 'unordered_list', items: ['보조 설명 A', '보조 설명 B'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('핵심 항목 A'), true);
  assert.equal(html.includes('핵심 항목 B'), true);
  assert.equal(html.includes('major-summary-card-sub'), true);
  assert.equal(html.includes('major-summary-index'), true);
  assert.equal(html.includes('major-summary-subline'), true);
  assert.equal(html.includes('>1</span>'), true);
  assert.equal(html.includes('>2</span>'), true);
  assert.equal(html.includes('보조 설명 A'), true);
  assert.equal(html.includes('보조 설명 B'), true);
});

test('taskpane messages groups summary metadata per mail card with received date', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['메일 제목 A', '메일 제목 B'] },
        { type: 'unordered_list', items: [
          '요약: A 이슈 요약',
          '보낸 사람: alpha@example.com',
          '수신일: 2026-03-07',
          '요약: B 이슈 요약',
          '보낸 사람: beta@example.com',
          '수신일: 2026-03-06',
        ] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('메일 제목 A'), true);
  assert.equal(html.includes('메일 제목 B'), true);
  assert.equal(html.includes('A 이슈 요약'), true);
  assert.equal(html.includes('B 이슈 요약'), true);
  assert.equal(html.includes('2026-03-07'), true);
  assert.equal(html.includes('2026-03-06'), true);
  assert.equal(html.includes('alpha@example.com'), false);
  assert.equal(html.includes('beta@example.com'), false);
  assert.equal(html.includes('major-summary-card-date'), true);
});

test('taskpane messages keeps major summary numbering across fragmented ordered blocks', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '📌 주요 내용' },
        { type: 'ordered_list', items: ['항목 1'] },
        { type: 'ordered_list', items: ['항목 2'] },
        { type: 'ordered_list', items: ['항목 3'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('>1</span>'), true);
  assert.equal(html.includes('>2</span>'), true);
  assert.equal(html.includes('>3</span>'), true);
});

test('taskpane messages renders major section even when only unordered list is provided', () => {
  const moduleRef = loadMessagesModule();
  const instance = moduleRef.create({
    byId: () => null,
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });
  const metadata = {
    answer_format: {
      blocks: [
        { type: 'heading', text: '📌 주요 내용' },
        { type: 'unordered_list', items: ['핵심 요약 A', '핵심 요약 B'] },
      ],
    },
  };
  const html = instance.buildMessageHtml('assistant', '본문', metadata);
  assert.equal(html.includes('major-summary-list'), true);
  assert.equal(html.includes('핵심 요약 A'), true);
  assert.equal(html.includes('핵심 요약 B'), true);
  assert.equal(html.includes('>1</span>'), true);
  assert.equal(html.includes('>2</span>'), true);
});

test('taskpane messages renders selected mail banner with recipient overflow label', () => {
  const moduleRef = loadMessagesModule();
  const bannerNode = { innerHTML: '', hidden: true };
  const instance = moduleRef.create({
    byId: (id) => (id === 'selectedMailBanner' ? bannerNode : null),
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
    escapeAttr: (value) => String(value || ''),
  });

  instance.renderSelectedMailBanner({
    messageId: 'm-1',
    subject: 'Tenant Restriction 방안',
    fromDisplayName: '박정호',
    recipients: ['이상수', '김태호', '박민수', '최하늘', '정유진'],
    receivedDate: '2026-02-26T07:17:16Z',
    webLink: 'https://outlook.live.com/owa/?ItemID=abc',
  });

  assert.equal(bannerNode.hidden, false);
  assert.equal(bannerNode.innerHTML.includes('박정호 → 이상수, 김태호 외 3명'), true);
  assert.equal(bannerNode.innerHTML.includes('data-action="selected-mail-open"'), true);
});

test('taskpane messages enforces selected mail banner class when rendering', () => {
  const moduleRef = loadMessagesModule();
  const bannerNode = { innerHTML: '', hidden: true, className: '' };
  const instance = moduleRef.create({
    byId: (id) => (id === 'selectedMailBanner' ? bannerNode : null),
    escapeHtml: (value) => String(value || ''),
    escapeAttr: (value) => String(value || ''),
  });

  instance.renderSelectedMailBanner({
    messageId: 'm-1',
    subject: '테스트 제목',
    fromDisplayName: '박정호',
    recipients: ['이상수', '김태호', '박민수'],
    receivedDate: '2026-02-26T07:17:16Z',
    webLink: 'https://outlook.live.com/owa/?ItemID=abc',
  });

  assert.equal(bannerNode.className, 'selected-mail-banner');
  assert.equal(bannerNode.hidden, false);
});

test('taskpane messages renders selected mail banner importance badges', () => {
  const moduleRef = loadMessagesModule();
  const bannerNode = { innerHTML: '', hidden: true, className: '' };
  const instance = moduleRef.create({
    byId: (id) => (id === 'selectedMailBanner' ? bannerNode : null),
    escapeHtml: (value) => String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;'),
    escapeAttr: (value) => String(value || ''),
  });

  instance.renderSelectedMailBanner({
    messageId: 'm-2',
    subject: '긴급 점검 요청',
    fromDisplayName: '홍길동',
    recipients: ['이상수'],
    receivedDate: '2026-03-08T00:00:00Z',
    importance: '긴급',
  });
  assert.equal(bannerNode.innerHTML.includes('selected-mail-banner-badge-urgent'), true);
  assert.equal(bannerNode.innerHTML.includes('긴급'), true);

  instance.renderSelectedMailBanner({
    messageId: 'm-3',
    subject: '확인 부탁드립니다',
    fromDisplayName: '홍길동',
    recipients: ['이상수'],
    receivedDate: '2026-03-08T00:00:00Z',
    category: '회신필요',
  });
  assert.equal(bannerNode.innerHTML.includes('selected-mail-banner-badge-reply'), true);
  assert.equal(bannerNode.innerHTML.includes('회신요망'), true);

  instance.renderSelectedMailBanner({
    messageId: 'm-4',
    subject: '중요 공지',
    fromDisplayName: '홍길동',
    recipients: ['이상수'],
    receivedDate: '2026-03-08T00:00:00Z',
    importance: '중요',
  });
  assert.equal(bannerNode.innerHTML.includes('selected-mail-banner-badge-important'), true);
  assert.equal(bannerNode.innerHTML.includes('중요'), true);

  instance.renderSelectedMailBanner({
    messageId: 'm-5',
    subject: '일반 안내',
    fromDisplayName: '홍길동',
    recipients: ['이상수'],
    receivedDate: '2026-03-08T00:00:00Z',
  });
  assert.equal(bannerNode.innerHTML.includes('selected-mail-banner-badge-normal'), true);
  assert.equal(bannerNode.innerHTML.includes('일반'), true);
});
