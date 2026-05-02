const $ = (id) => document.getElementById(id);

const state = {
  stats: null,
  memories: [],
  memoryDecisions: [],
  events: [],
  traces: [],
  selectedMemoryId: null,
  selectedTraceId: null,
  lang: localStorage.getItem("agentmemos.lang") || "en",
};

const translations = {
  en: {
    "actions.refresh": "Refresh",
    "nav.memories": "Memories",
    "nav.decisions": "Decisions",
    "nav.events": "Events",
    "nav.traces": "Traces",
    "nav.explain": "Explain",
    "nav.docs": "API Docs",
    "main.title": "Memory board",
    "overview.title": "Overview",
    "overview.events": "Events",
    "overview.memories": "Memories",
    "overview.active": "Active memories",
    "overview.traces": "Traces",
    "probe.title": "Probe",
    "probe.taskId": "Task ID",
    "probe.agentId": "Agent ID",
    "probe.role": "Role",
    "probe.query": "Query",
    "probe.run": "Run retrieval",
    "probe.empty": "No retrieval run yet.",
    "probe.running": "Running retrieval...",
    "probe.noMatches": "No matching memories.",
    "distribution.eyebrow": "CHART I · SCOPE GOVERNANCE",
    "distribution.title": "Memory distribution",
    "filters.allScopes": "All scopes",
    "filters.allTypes": "All types",
    "charts.scopes": "Scopes",
    "charts.types": "Memory types",
    "charts.status": "Memory status",
    "charts.roles": "Agent roles",
    "sections.memories": "Memories",
    "sections.events": "Events",
    "sections.traces": "Traces",
    "memoryDecision.title": "Memory decision",
    "memoryDecision.empty": "Select a memory to inspect why it was written, classified, scoped, and scored.",
    "memoryDecision.noDecision": "No write decision is recorded for this memory. It may be historical data created before this audit feature existed.",
    "memoryDecision.oneAtATime": "This panel shows one selected memory at a time. Click another memory card to switch records.",
    "memoryDecision.reason": "Reason",
    "memoryDecision.signals": "Signals",
    "memoryDecision.selectedHelp": "This panel explains the write-side decision: source event, extraction/manual path, chosen memory type, scope, confidence, and importance.",
    "traceExplain.title": "Trace explain",
    "traceExplain.empty": "Select a retrieval trace to inspect scoring, selected memories, and filtered memory reasons.",
    "traceExplain.selected": "Selected",
    "traceExplain.candidate": "Candidate",
    "traceExplain.filtered": "Filtered",
    "traceExplain.candidates": "Scored candidates",
    "traceExplain.noScored": "No scored candidates recorded for this trace.",
    "traceExplain.noFiltered": "No filtered memories for this trace.",
    "traceExplain.moreFiltered": "{count} more filtered memories are hidden.",
    "traceExplain.score": "score",
    "traceExplain.parts": "score parts",
    "traceExplain.defaultHelp": "The dashboard opens the most informative trace first: selected memories, then scored candidates, then the newest trace.",
    "legend.title": "Quick guide",
    "legend.intro": "<strong>AgentMemOS observes three things:</strong> events come in, memories are formed, traces explain retrieval.",
    "legend.memory.title": "Memory",
    "legend.memory.body1": "Structured, reusable task knowledge extracted from agent activity.",
    "legend.memory.body2": "Use it to inspect what the system currently remembers.",
    "legend.memory.scopes": "<strong>Scopes define who can see a memory.</strong>",
    "legend.memory.agentLocal": "<strong>agent-local</strong>: private scratch for one specific agent.",
    "legend.memory.taskLocal": "<strong>task-local</strong>: shared context inside one task.",
    "legend.memory.teamShared": "<strong>team-shared</strong>: team-level conclusion or risk useful to multiple agents.",
    "legend.memory.projectGlobal": "<strong>project-global</strong>: long-lived knowledge reusable across tasks.",
    "legend.memory.types": "<strong>Types define what kind of memory it is.</strong>",
    "legend.memory.working": "<strong>working</strong>: current task state, goal, constraint, or progress.",
    "legend.memory.episodic": "<strong>episodic</strong>: concrete event, tool result, finding, failure, or observation.",
    "legend.memory.procedural": "<strong>procedural</strong>: reusable practice, rule, workflow, or learned strategy.",
    "legend.memory.decisions": "<strong>Memory decision panel</strong>: click a memory to inspect why it was written, classified, scoped, and scored.",
    "legend.event.title": "Event",
    "legend.event.body1": "Raw agent runtime input, such as a tool result or review finding.",
    "legend.event.body2": "Use it to verify where a memory came from.",
    "legend.event.common": "<strong>Common types</strong>: task.created, tool.result.observed, review.finding.created, subtask.completed.",
    "legend.trace.title": "Trace",
    "legend.trace.body1": "Audit record for a retrieval request.",
    "legend.trace.body2": "Use it to see what was selected, filtered, and why.",
    "legend.trace.fields": "<strong>Fields</strong>: query, agent role, selected memories, filtered memories, reason.",
    "legend.trace.explain": "<strong>Trace explain panel</strong>: click a trace or run Probe. The top shows who retrieved what; the left column shows visible candidates and score parts; the right column shows filtered memories and why they were hidden. The dashboard opens the most informative trace first.",
    records: "records",
    entries: "entries",
    traces: "traces",
    selected: "selected",
    filtered: "filtered",
    inspect: "inspect",
    "empty.readings": "No readings yet.",
    "empty.memories": "No memories match this chart.",
    "empty.events": "No agent events yet.",
    "empty.traces": "No retrieval traces yet.",
    "status.checking": "checking",
    "status.syncing": "syncing",
    "status.offline": "offline",
    "status.ok": "ok",
  },
  zh: {
    "actions.refresh": "刷新",
    "nav.memories": "记忆",
    "nav.decisions": "决策",
    "nav.events": "事件",
    "nav.traces": "追踪",
    "nav.explain": "解释",
    "nav.docs": "接口文档",
    "main.title": "Memory 看板",
    "overview.title": "概览",
    "overview.events": "事件",
    "overview.memories": "记忆",
    "overview.active": "有效记忆",
    "overview.traces": "检索追踪",
    "probe.title": "检索测试",
    "probe.taskId": "任务 ID",
    "probe.agentId": "Agent ID",
    "probe.role": "角色",
    "probe.query": "查询",
    "probe.run": "运行检索",
    "probe.empty": "还没有运行检索。",
    "probe.running": "正在检索...",
    "probe.noMatches": "没有匹配的记忆。",
    "distribution.eyebrow": "图表 I · 作用域治理",
    "distribution.title": "记忆分布",
    "filters.allScopes": "全部作用域",
    "filters.allTypes": "全部类型",
    "charts.scopes": "作用域",
    "charts.types": "记忆类型",
    "charts.status": "记忆状态",
    "charts.roles": "Agent 角色",
    "sections.memories": "记忆",
    "sections.events": "事件",
    "sections.traces": "检索追踪",
    "memoryDecision.title": "记忆写入决策",
    "memoryDecision.empty": "选择一条记忆，查看它为什么被写入、分类、设定作用域和评分。",
    "memoryDecision.noDecision": "这条记忆没有写入决策记录，可能是审计功能出现前创建的历史数据。",
    "memoryDecision.oneAtATime": "这个面板一次展示一条被选中的 memory。点击其他 memory 卡片可以切换记录。",
    "memoryDecision.reason": "原因",
    "memoryDecision.signals": "信号",
    "memoryDecision.selectedHelp": "这个面板解释写入侧决策：来源事件、抽取/手动路径、选择的记忆类型、作用域、可信度和重要性。",
    "traceExplain.title": "检索解释",
    "traceExplain.empty": "选择一条检索追踪，查看评分、选中记忆和过滤原因。",
    "traceExplain.selected": "已选中",
    "traceExplain.candidate": "候选",
    "traceExplain.filtered": "已过滤",
    "traceExplain.candidates": "候选评分",
    "traceExplain.noScored": "这条追踪没有记录候选评分。",
    "traceExplain.noFiltered": "这条追踪没有过滤记忆。",
    "traceExplain.moreFiltered": "还有 {count} 条被过滤记忆已收起。",
    "traceExplain.score": "分数",
    "traceExplain.parts": "分项",
    "traceExplain.defaultHelp": "看板会优先打开信息量最高的 trace：先选有命中的，再选有候选评分的，最后才选最新 trace。",
    "legend.title": "快速说明",
    "legend.intro": "<strong>AgentMemOS 主要观测三类对象：</strong>事件进入系统，事件沉淀为记忆，追踪记录解释检索过程。",
    "legend.memory.title": "Memory（记忆）",
    "legend.memory.body1": "从 agent 活动中抽取出来的结构化、可复用任务知识。",
    "legend.memory.body2": "用它查看系统当前记住了什么。",
    "legend.memory.scopes": "<strong>Scopes 定义谁能看到这条记忆。</strong>",
    "legend.memory.agentLocal": "<strong>agent-local</strong>：某个具体 agent 的私有草稿或局部经验。",
    "legend.memory.taskLocal": "<strong>task-local</strong>：只在当前任务内共享的上下文。",
    "legend.memory.teamShared": "<strong>team-shared</strong>：多个 agent 都应该参考的团队结论、风险或共识。",
    "legend.memory.projectGlobal": "<strong>project-global</strong>：跨任务长期复用的项目级知识。",
    "legend.memory.types": "<strong>Types 定义这条记忆是什么性质。</strong>",
    "legend.memory.working": "<strong>working</strong>：当前任务状态、目标、约束或进度。",
    "legend.memory.episodic": "<strong>episodic</strong>：具体事件、工具结果、发现、失败或观察。",
    "legend.memory.procedural": "<strong>procedural</strong>：可复用做法、规则、流程或策略。",
    "legend.memory.decisions": "<strong>Memory decision 面板</strong>：点击一条记忆，查看它为什么被写入、分类、设定作用域和评分。",
    "legend.event.title": "Event（事件）",
    "legend.event.body1": "agent runtime 写入的原始输入，例如工具结果、review 反馈或任务状态变化。",
    "legend.event.body2": "用它确认某条记忆来自哪里。",
    "legend.event.common": "<strong>常见类型</strong>：task.created、tool.result.observed、review.finding.created、subtask.completed。",
    "legend.trace.title": "Trace（追踪）",
    "legend.trace.body1": "一次 memory retrieval 的审计记录。",
    "legend.trace.body2": "用它查看检索时选中了什么、过滤了什么、为什么这样处理。",
    "legend.trace.fields": "<strong>核心字段</strong>：query、agent role、selected memories、filtered memories、reason。",
    "legend.trace.explain": "<strong>Trace explain 面板</strong>：点击一条 trace 或运行 Probe。顶部看是谁在什么任务里检索；左侧看可见候选及分项得分；右侧看被过滤的记忆和过滤原因。看板会默认打开信息量最高的 trace。",
    records: "条记录",
    entries: "条事件",
    traces: "条追踪",
    selected: "选中",
    filtered: "过滤",
    inspect: "查看",
    "empty.readings": "暂无读数。",
    "empty.memories": "没有匹配当前筛选的记忆。",
    "empty.events": "暂无 agent 事件。",
    "empty.traces": "暂无检索追踪。",
    "status.checking": "检查中",
    "status.syncing": "同步中",
    "status.offline": "离线",
    "status.ok": "正常",
  },
};

function t(key) {
  return translations[state.lang][key] ?? translations.en[key] ?? key;
}

function applyLanguage() {
  document.documentElement.lang = state.lang === "zh" ? "zh-CN" : "en";
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-html]").forEach((el) => {
    el.innerHTML = t(el.dataset.i18nHtml);
  });
  const target = state.lang === "zh" ? "en" : "zh";
  $("langBtn").dataset.langTarget = target;
  $("langBtn").textContent = state.lang === "zh" ? "EN" : "中文";
  if ($("retrieveResult").dataset.state === "empty") {
    setText("retrieveResult", t("probe.empty"));
  }
  if (state.stats) {
    renderBars("scopeBars", state.stats.scope_counts);
    renderBars("typeBars", state.stats.type_counts);
    renderBars("statusBars", state.stats.status_counts);
    renderBars("roleBars", state.stats.role_counts);
    renderMemories();
    renderMemoryDecision();
    renderEvents();
    renderTraces();
    renderTraceExplain();
  }
}

function fmtDate(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  return date.toLocaleString([], { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

function renderBars(id, counts) {
  const el = $(id);
  const entries = Object.entries(counts || {});
  if (!entries.length) {
    el.innerHTML = `<div class="empty">${t("empty.readings")}</div>`;
    return;
  }
  const max = Math.max(...entries.map(([, count]) => count), 1);
  el.innerHTML = entries
    .map(([name, count]) => `
      <div class="bar-row">
        <span>${name}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(count / max) * 100}%"></div></div>
        <strong>${count}</strong>
      </div>
    `)
    .join("");
}

function memoryTags(memory) {
  const scopeClass = `scope-${memory.scope}`;
  return [
    `<span class="tag ${scopeClass}">${memory.scope}</span>`,
    `<span class="tag">${memory.memory_type}</span>`,
    `<span class="tag">${memory.status}</span>`,
    `<span class="tag">conf ${Math.round(memory.confidence * 100)}%</span>`,
    `<span class="tag">imp ${Math.round(memory.importance * 100)}%</span>`,
  ].join("");
}

function memoryById(memoryId) {
  return state.memories.find((memory) => memory.memory_id === memoryId);
}

function decisionsForMemory(memoryId) {
  return state.memoryDecisions.filter((decision) => decision.memory_id === memoryId);
}

function primaryDecisionForMemory(memoryId) {
  return decisionsForMemory(memoryId)[0] || null;
}

function pickDecisionMemory(memories) {
  const byId = new Map(memories.map((memory) => [memory.memory_id, memory]));
  const extracted = state.memoryDecisions.find(
    (decision) => decision.decision_type === "extracted" && byId.has(decision.memory_id)
  );
  if (extracted) return byId.get(extracted.memory_id);
  const decided = state.memoryDecisions.find((decision) => byId.has(decision.memory_id));
  return (decided && byId.get(decided.memory_id)) || memories[0] || null;
}

function pickInformativeTrace(traces) {
  return (
    traces.find((trace) => (trace.selected_memories || []).length > 0)
    || traces.find((trace) => (trace.scored_memories || []).length > 0)
    || traces[0]
    || null
  );
}

function renderMemories() {
  const list = $("memoryList");
  const scope = $("scopeFilter").value;
  const type = $("typeFilter").value;
  const memories = state.memories.filter((memory) => {
    return (!scope || memory.scope === scope) && (!type || memory.memory_type === type);
  });
  setText("memoryCount", `${memories.length} ${t("records")}`);

  if (!memories.length) {
    list.innerHTML = `<div class="empty">${t("empty.memories")}</div>`;
    return;
  }

  list.innerHTML = memories
    .map((memory) => {
      const decision = primaryDecisionForMemory(memory.memory_id);
      const decisionType = decision?.decision_type || "no-decision";
      return `
      <article class="memory-card ${memory.memory_id === state.selectedMemoryId ? "active-memory" : ""} decision-${decisionType}" data-memory-id="${memory.memory_id}">
        <div class="coord">
          ${fmtDate(memory.created_at)}<br>
          ${memory.task_id || "global"}<br>
          ${memory.agent_id || "system"}
        </div>
        <div>
          <div class="memory-title">${escapeHtml(memory.summary)}</div>
          <div class="memory-body">${escapeHtml(memory.content)}</div>
          <div class="tag-row">${memoryTags(memory)}<span class="tag decision-tag decision-tag-${decisionType}">${decisionType}</span></div>
        </div>
      </article>
    `;
    })
    .join("");
}

function renderDecisionMetric(label, value) {
  return `
    <div class="decision-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderSignals(signals) {
  const entries = Object.entries(signals || {});
  if (!entries.length) return `<div class="empty">${t("empty.readings")}</div>`;
  return entries
    .map(([key, value]) => `
      <div class="signal-row">
        <span>${escapeHtml(key)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>
    `)
    .join("");
}

function renderMemoryDecision(memory = memoryById(state.selectedMemoryId)) {
  const body = $("memoryDecisionBody");
  if (!body) return;
  if (!memory) {
    setText("memoryDecisionId", state.lang === "zh" ? "未选择 memory" : "no memory selected");
    body.className = "decision-empty";
    body.textContent = t("memoryDecision.empty");
    return;
  }

  state.selectedMemoryId = memory.memory_id;
  setText("memoryDecisionId", memory.memory_id);
  const decisions = decisionsForMemory(memory.memory_id);
  body.className = "memory-decision";
  if (!decisions.length) {
    body.innerHTML = `
      <div class="trace-summary">
        <div>
          <div class="trace-query">${escapeHtml(memory.summary)}</div>
          <div class="log-meta">${memory.memory_type} · ${memory.scope} · ${memory.agent_id || "system"} · ${memory.task_id || "global"}</div>
        </div>
      </div>
      <div class="trace-help">${escapeHtml(t("memoryDecision.oneAtATime"))}</div>
      <div class="decision-empty inline">${escapeHtml(t("memoryDecision.noDecision"))}</div>
    `;
    return;
  }

  body.innerHTML = decisions
    .map((decision) => `
      <article class="decision-card">
        <div class="trace-summary">
          <div>
            <div class="trace-query">${escapeHtml(memory.summary)}</div>
            <div class="log-meta">${decision.decision_type} · ${decision.source_event_id || "manual"} · ${fmtDate(decision.created_at)}</div>
          </div>
          <div class="trace-counts">
            <span class="tag">${decision.chosen_memory_type}</span>
            <span class="tag scope-${decision.chosen_scope}">${decision.chosen_scope}</span>
          </div>
        </div>
        <div class="trace-help">${escapeHtml(t("memoryDecision.selectedHelp"))} ${escapeHtml(t("memoryDecision.oneAtATime"))}</div>
        <div class="decision-metrics">
          ${renderDecisionMetric("confidence", Number(decision.confidence || 0).toFixed(2))}
          ${renderDecisionMetric("importance", Number(decision.importance || 0).toFixed(2))}
          ${renderDecisionMetric("type", decision.chosen_memory_type)}
          ${renderDecisionMetric("scope", decision.chosen_scope)}
        </div>
        <div class="decision-grid">
          <section>
            <h3>${t("memoryDecision.reason")}</h3>
            <div class="trace-reason">${escapeHtml(decision.reason)}</div>
          </section>
          <section>
            <h3>${t("memoryDecision.signals")}</h3>
            <div class="signal-list">${renderSignals(decision.signals)}</div>
          </section>
        </div>
      </article>
    `)
    .join("");
}

function scorePartsHtml(scoreParts) {
  const entries = Object.entries(scoreParts || {});
  if (!entries.length) return "";
  const max = Math.max(...entries.map(([, value]) => Number(value) || 0), 0.001);
  return entries
    .map(([name, value]) => `
      <div class="score-part">
        <span>${escapeHtml(name)}</span>
        <div class="bar-track compact-track"><div class="bar-fill" style="width:${((Number(value) || 0) / max) * 100}%"></div></div>
        <strong>${Number(value).toFixed(4)}</strong>
      </div>
    `)
    .join("");
}

function renderTraceExplain(trace = state.traces.find((item) => item.trace_id === state.selectedTraceId)) {
  const body = $("traceExplainBody");
  if (!body) return;
  if (!trace) {
    setText("traceExplainId", state.lang === "zh" ? "未选择 trace" : "no trace selected");
    body.className = "trace-explain-empty";
    body.textContent = t("traceExplain.empty");
    return;
  }

  state.selectedTraceId = trace.trace_id;
  setText("traceExplainId", trace.trace_id);
  body.className = "trace-explain";
  const scored = trace.scored_memories || [];
  const filtered = trace.filtered_memories || [];
  const visibleFiltered = filtered.slice(0, 10);
  const hiddenFilteredCount = Math.max(filtered.length - visibleFiltered.length, 0);
  body.innerHTML = `
    <div class="trace-summary">
      <div>
        <div class="trace-query">${escapeHtml(trace.query)}</div>
        <div class="log-meta">${trace.agent_role} · ${trace.agent_id} · ${trace.task_id} · ${fmtDate(trace.created_at)}</div>
      </div>
      <div class="trace-counts">
        <span class="tag">${t("selected")} ${trace.selected_memories.length}</span>
        <span class="tag">${t("filtered")} ${filtered.length}</span>
      </div>
    </div>
    <div class="trace-help">${escapeHtml(t("traceExplain.defaultHelp"))}</div>
    <div class="trace-reason">${escapeHtml(trace.reason)}</div>
    <div class="trace-columns">
      <section>
        <h3>${t("traceExplain.candidates")}</h3>
        <div class="candidate-list">
          ${
            scored.length
              ? scored.map((item) => {
                  const memory = memoryById(item.memory_id);
                  return `
                    <article class="candidate-card ${item.selected ? "candidate-selected" : ""}">
                      <div class="candidate-head">
                        <span class="tag">${item.selected ? t("traceExplain.selected") : t("traceExplain.candidate")}</span>
                        <strong>${t("traceExplain.score")} ${Number(item.score || 0).toFixed(4)}</strong>
                      </div>
                      <div class="memory-title">${escapeHtml(memory?.summary || item.memory_id)}</div>
                      <div class="memory-body">${escapeHtml(memory?.content || `${item.scope} · ${item.memory_type}`)}</div>
                      <div class="score-parts-label">${t("traceExplain.parts")}</div>
                      <div class="score-parts">${scorePartsHtml(item.score_parts)}</div>
                    </article>
                  `;
                }).join("")
              : `<div class="empty">${t("traceExplain.noScored")}</div>`
          }
        </div>
      </section>
      <section>
        <h3>${t("traceExplain.filtered")}</h3>
        <div class="filtered-list">
          ${
            filtered.length
              ? `${visibleFiltered.map((memoryId) => {
                  const memory = memoryById(memoryId);
                  const reason = trace.filter_reasons?.[memoryId] || trace.reason;
                  return `
                    <article class="filtered-card">
                      <div class="memory-title">${escapeHtml(memory?.summary || memoryId)}</div>
                      <div class="memory-body">${escapeHtml(reason)}</div>
                      <div class="tag-row"><span class="tag">${escapeHtml(memoryId)}</span></div>
                    </article>
                  `;
                }).join("")}
                ${hiddenFilteredCount ? `<div class="filtered-more">${escapeHtml(t("traceExplain.moreFiltered").replace("{count}", hiddenFilteredCount))}</div>` : ""}`
              : `<div class="empty">${t("traceExplain.noFiltered")}</div>`
          }
        </div>
      </section>
    </div>
  `;
}

function renderEvents() {
  setText("eventCount", `${state.events.length} ${t("entries")}`);
  const el = $("eventList");
  if (!state.events.length) {
    el.innerHTML = `<div class="empty">${t("empty.events")}</div>`;
    return;
  }
  el.innerHTML = state.events
    .map((event) => `
      <div class="log-row">
        <div class="log-time">${fmtDate(event.created_at)}</div>
        <div>
          <div class="log-title">${event.event_type}</div>
          <div class="log-meta">${event.agent_role} · ${event.agent_id} · ${event.task_id}</div>
          <div class="memory-body">${escapeHtml(event.content)}</div>
        </div>
      </div>
    `)
    .join("");
}

function renderTraces() {
  setText("traceCount", `${state.traces.length} ${t("traces")}`);
  const el = $("traceList");
  if (!state.traces.length) {
    el.innerHTML = `<div class="empty">${t("empty.traces")}</div>`;
    return;
  }
  el.innerHTML = state.traces
    .map((trace) => `
      <div class="log-row trace-row ${trace.trace_id === state.selectedTraceId ? "active-trace" : ""}" data-trace-id="${trace.trace_id}">
        <div class="log-time">${fmtDate(trace.created_at)}<br>${trace.trace_id}</div>
        <div>
          <div class="log-title">${escapeHtml(trace.query)}</div>
          <div class="log-meta">${trace.agent_role} · ${t("selected")} ${trace.selected_memories.length} · ${t("filtered")} ${trace.filtered_memories.length}</div>
          <div class="memory-body">${escapeHtml(trace.reason)}</div>
          <button class="btn trace-inspect" type="button" data-trace-id="${trace.trace_id}">${t("inspect")}</button>
        </div>
      </div>
    `)
    .join("");
  renderTraceExplain();
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refresh() {
  setText("serviceStatus", t("status.syncing"));
  const [health, stats, memories, memoryDecisions, events, traces] = await Promise.all([
    api("/health"),
    api("/dashboard/stats"),
    api("/memories?limit=200"),
    api("/memory-decisions?limit=200"),
    api("/events?limit=80"),
    api("/traces?limit=80"),
  ]);

  state.stats = stats;
  state.memories = memories;
  state.memoryDecisions = memoryDecisions;
  state.events = events;
  state.traces = traces;
  const selectedMemoryStillExists = memories.some((memory) => memory.memory_id === state.selectedMemoryId);
  if (!selectedMemoryStillExists) {
    state.selectedMemoryId = pickDecisionMemory(memories)?.memory_id || null;
  }
  const selectedStillExists = traces.some((trace) => trace.trace_id === state.selectedTraceId);
  if (!selectedStillExists) {
    state.selectedTraceId = pickInformativeTrace(traces)?.trace_id || null;
  }

  setText("serviceStatus", t(`status.${health.status}`));
  setText("lastUpdated", new Date().toLocaleTimeString());
  setText("totalEvents", stats.total_events);
  setText("totalMemories", stats.total_memories);
  setText("activeMemories", stats.active_memories);
  setText("totalTraces", stats.total_traces);
  renderBars("scopeBars", stats.scope_counts);
  renderBars("typeBars", stats.type_counts);
  renderBars("statusBars", stats.status_counts);
  renderBars("roleBars", stats.role_counts);
  renderMemories();
  renderMemoryDecision();
  renderEvents();
  renderTraces();
  renderTraceExplain();
}

async function runRetrieval(event) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const payload = {
    task_id: form.get("task_id"),
    agent_id: form.get("agent_id"),
    agent_role: form.get("agent_role"),
    query: form.get("query"),
    allowed_scopes: ["agent-local", "task-local", "team-shared", "project-global"],
  };
  $("retrieveResult").dataset.state = "result";
  setText("retrieveResult", t("probe.running"));
  try {
    const result = await api("/retrieve", { method: "POST", body: JSON.stringify(payload) });
    state.selectedTraceId = result.trace_id;
    setText("retrieveResult", `trace: ${result.trace_id}\n\n${result.packed_context || t("probe.noMatches")}`);
    await refresh();
  } catch (error) {
    setText("retrieveResult", error.message);
  }
}

$("refreshBtn").addEventListener("click", refresh);
$("langBtn").addEventListener("click", () => {
  state.lang = $("langBtn").dataset.langTarget;
  localStorage.setItem("agentmemos.lang", state.lang);
  applyLanguage();
});
$("scopeFilter").addEventListener("change", renderMemories);
$("typeFilter").addEventListener("change", renderMemories);
$("retrieveForm").addEventListener("submit", runRetrieval);
$("memoryList").addEventListener("click", (event) => {
  const target = event.target.closest("[data-memory-id]");
  if (!target) return;
  state.selectedMemoryId = target.dataset.memoryId;
  renderMemories();
  renderMemoryDecision();
  document.getElementById("memoryDecision").scrollIntoView({ behavior: "smooth", block: "start" });
});
$("traceList").addEventListener("click", (event) => {
  const target = event.target.closest("[data-trace-id]");
  if (!target) return;
  state.selectedTraceId = target.dataset.traceId;
  renderTraces();
  document.getElementById("traceExplain").scrollIntoView({ behavior: "smooth", block: "start" });
});
function setLegendOpen(open) {
  $("legendPopover").hidden = !open;
  $("legendBackdrop").hidden = !open;
  $("legendBtn").setAttribute("aria-expanded", String(open));
}
$("legendBtn").addEventListener("click", () => {
  setLegendOpen($("legendPopover").hidden);
});
$("legendBackdrop").addEventListener("click", () => setLegendOpen(false));
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    setLegendOpen(false);
  }
});

refresh().catch((error) => {
  setText("serviceStatus", t("status.offline"));
  setText("retrieveResult", error.message);
});

$("retrieveResult").dataset.state = "empty";
applyLanguage();
