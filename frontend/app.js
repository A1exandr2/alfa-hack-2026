"use strict";
const root = document.querySelector("#app");
const state = {
  token: sessionStorage.getItem("credit-token"),
  user: null,
  company: null,
  financials: null,
  history: null,
  products: [],
  applications: [],
  busy: false,
  submitting: null,
  loadError: null,
  registry: null,
  creditConnection: null,
};
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (value) =>
  value == null ? "Нет данных" : new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(
    Number(value || 0),
  ) + " ₽";
const date = (value) =>
  value
    ? new Date(value).toLocaleDateString("ru-RU", {
        day: "numeric",
        month: "long",
        year: "numeric",
      })
    : "—";
const time = (value) => value ? new Date(value).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "—";
const statusNames = {
  DRAFT: "Черновик",
  DATA_CHECK: "Проверка данных",
  NEED_MORE_DATA: "Нужны данные",
  SCORING: "Оценка риска",
  MANUAL_REVIEW: "Ручная проверка",
  DECISION: "Предварительно одобрено",
  REJECTED: "Отказ",
};
const fieldNames = {
  revenue_annual: "Выручка за год",
  profit_annual: "Прибыль за год",
  expenses_annual: "Расходы за год",
  employees: "Сотрудники",
  current_debt: "Текущая задолженность",
};
const eventNames = {
  APPLICATION_CREATED: "Заявка создана",
  APPLICATION_UPDATED: "Заявка обновлена",
  APPLICATION_SUBMITTED: "Заявка отправлена",
  APPLICATION_DATA_CHECK_STARTED: "Проверка данных",
  APPLICATION_DATA_CHECKED: "Данные проверены",
  APPLICATION_DATA_REQUIRED: "Запрошены дополнительные данные",
  APPLICATION_SCORING_STARTED: "Начата оценка риска",
  APPLICATION_SCORED: "Оценка риска завершена",
  APPLICATION_DECISION_CREATED: "Решение сохранено",
  APPLICATION_REVIEW_RECORDED: "Решение специалиста сохранено",
  APPLICATION_RESUBMITTED: "Заявка отправлена повторно",
};
const icons = {
  home: '<path d="m3 9 7-6 7 6v8H3Z"/><path d="M8 17v-6h4v6"/>',
  products:
    '<rect x="3" y="4" width="14" height="12" rx="2"/><path d="M3 8h14M6 12h3"/>',
  applications:
    '<rect x="5" y="3" width="11" height="15" rx="2"/><path d="M8 7h5M8 11h5M8 15h3"/>',
  company:
    '<path d="M3 18V5h10v13M13 10h4v8M1 18h18M6 8h1M10 8h1M6 12h1M10 12h1"/>',
  documents: '<path d="M5 2h7l4 4v12H5Z"/><path d="M12 2v5h4M8 11h5M8 14h5"/>',
  financials: '<path d="M3 17h15M5 14V9M10 14V4M15 14V7"/>',
};
icons.admin = '<path d="M12 3 3 7v5c0 5 9 9 9 9s9-4 9-9V7l-9-4Z"/><path d="m8 12 3 3 5-6"/>';
const icon = (key) =>
  `<span class="icon"><svg viewBox="0 0 20 20" aria-hidden="true">${icons[key] || icons.home}</svg></span>`;
const brand =
  '<a href="#/" class="brand" aria-label="Альфа бизнес — главная"><span class="brand-mark"><svg width="32" height="40" viewBox="0 0 32 40" aria-hidden="true" fill="currentColor"><path fill-rule="evenodd" d="M12 0h8l12 31h-8l-2-6H10l-2 6H0L12 0Zm0 19h8L16 8l-4 11Z"/><path d="M1 36h30v4H1z"/></svg></span><span><strong>альфа</strong><small>бизнес</small></span></a>';
const pill = (status) =>
  `<span class="pill ${status === "DECISION" ? "green" : status === "REJECTED" ? "red" : status === "MANUAL_REVIEW" || status === "NEED_MORE_DATA" ? "amber" : ""}">${esc(statusNames[status] || status)}</span>`;
function notice(text, kind = "info") {
  const el = document.querySelector("#notice");
  el.textContent = text;
  el.dataset.kind = kind;
  el.setAttribute("role", kind === "error" ? "alert" : "status");
  el.style.display = "block";
  clearTimeout(notice.timer);
  notice.timer = setTimeout(() => (el.style.display = "none"), 6000);
}
class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}
function friendlyApiError(data, status) {
  const translations = {
    "User with this email already exists":
      "Аккаунт с этой почтой уже существует. Войдите или укажите другую почту.",
    "Email already registered":
      "Аккаунт с этой почтой уже существует. Войдите или укажите другую почту.",
    "Invalid email or password":
      "Неверная почта или пароль. Проверьте введённые данные.",
    "Invalid or missing authentication token":
      "Сессия завершена. Войдите снова.",
    "Reviewer role required": "Это действие доступно только специалисту.",
    "Administrator role required": "Это действие доступно только администратору.",
    "Company already linked": "Компания уже привязана к вашему аккаунту.",
    "User is already linked to another company":
      "К аккаунту уже привязана другая компания.",
    "Company is not linked":
      "Сначала привяжите компанию по ИНН в разделе «Компания».",
    "Company must be linked before creating an application":
      "Сначала привяжите компанию по ИНН в разделе «Компания».",
    "Company registry is not configured":
      "Реестр пока не подключён. Для загрузки реальных реквизитов администратор должен настроить доступ к источнику данных.",
    "No product matches requested amount and term":
      "Для этой суммы и срока подходящего продукта нет. Измените сумму или срок.",
    "Company not found": "Компания не найдена. Проверьте ИНН.",
    "Company provider returned mismatched INN":
      "Не удалось подтвердить ИНН. Проверьте номер и попробуйте снова.",
    "Company could not be linked":
      "Не удалось привязать компанию. Попробуйте ещё раз.",
    "Financial data could not be saved":
      "Не удалось сохранить финансовые данные. Повторите попытку.",
    "Credit history source is not configured": "Источник кредитной истории пока не подключён.",
    "Credit history consent is required": "Нужно согласие на запрос кредитного отчёта.",
    "Explicit credit report consent is required": "Подтвердите согласие на запрос кредитного отчёта.",
    "Credit history could not be saved":
      "Не удалось сохранить кредитную историю. Повторите попытку.",
    "Active credit product not found":
      "Этот продукт больше не доступен. Выберите другой в каталоге.",
    "Application not found": "Заявка не найдена. Откройте раздел «Мои заявки».",
    "Only draft applications can be edited":
      "Эта заявка уже отправлена. Редактирование недоступно.",
    "Application cannot be submitted in its current state":
      "Заявка уже рассматривается или завершена. Обновите её статус.",
    "Application is not awaiting a reviewer decision":
      "Заявка сейчас не ожидает ручной проверки. Обновите страницу.",
    "Application data is incomplete":
      "Для отправки заявки нужно дополнить данные компании.",
    "Application risk scoring could not be completed":
      "Не удалось завершить оценку заявки. Проверьте её статус и повторите попытку позже.",
    "Application decision not found":
      "Решение ещё не готово. Обновите статус заявки позже.",
  };
  if (typeof data?.detail === "string" && translations[data.detail])
    return translations[data.detail];
  if (Array.isArray(data?.detail)) {
    const names = {
      ...fieldNames,
      email: "Электронная почта",
      password: "Пароль",
      full_name: "Имя и фамилия",
      inn: "ИНН",
      requested_amount: "Сумма кредита",
      term_months: "Срок кредита",
      purpose: "Цель кредита",
      additional_info: "Дополнительные сведения",
      comment: "Комментарий",
      product_id: "Кредитный продукт",
    };
    return data.detail
      .map((item) => {
        const key = item.loc?.at(-1);
        const label = names[key] || "Поле формы";
        if (item.type === "missing") return `${label}: заполните это поле.`;
        if (key === "password" && item.type === "string_too_short")
          return "Пароль должен содержать минимум 8 символов.";
        if (key === "inn") return "Укажите ИНН из 10 или 12 цифр.";
        if (item.type === "string_too_long")
          return `${label}: сократите текст (максимум ${item.ctx?.max_length || 500} символов).`;
        if (item.type === "greater_than_equal")
          return `${label}: значение должно быть не меньше ${item.ctx?.ge ?? 0}.`;
        if (item.type === "greater_than")
          return `${label}: значение должно быть больше ${item.ctx?.gt ?? 0}.`;
        return `${label}: проверьте правильность заполнения.`;
      })
      .join(" ");
  }
  if ([400, 408, 413, 415, 422, 429, 409, 404].includes(status) && typeof data?.detail === "string" && /[а-яё]/i.test(data.detail)) return data.detail;
  if (status === 401) return "Не удалось войти. Проверьте почту и пароль.";
  if (status === 403) return "У вас нет доступа к этому действию.";
  if (status === 404) return "Данные не найдены. Обновите страницу.";
  if (status === 409)
    return "Данные уже изменились. Обновите страницу и проверьте результат.";
  if (status === 422 || status === 400)
    return "Проверьте заполненные поля, сумму и срок кредита.";
  if (status === 429)
    return "Слишком много попыток. Подождите немного и повторите.";
  return "Сервис временно недоступен. Попробуйте ещё раз немного позже.";
}
async function api(path, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), options.timeoutMs || 180000);
  try {
    const response = await fetch("/api/v1" + path, {
      ...options,
      headers: {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
        ...(state.token ? { Authorization: "Bearer " + state.token } : {}),
        ...options.headers,
      },
      signal: controller.signal,
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      if (response.status === 401 && state.token) {
        sessionStorage.removeItem("credit-token");
        state.token = null;
        state.user = null;
        location.hash = "/login";
      }
      const message = friendlyApiError(data, response.status);
      throw new ApiError(message, response.status, data);
    }
    return data;
  } catch (error) {
    if (error.name === "AbortError")
      throw new Error(
        options.timeoutMessage || "Ответ занял слишком много времени. Проверьте статус заявки перед повторной отправкой.",
      );
    if (error instanceof TypeError)
      throw new Error(
        "Нет связи с сервером. Проверьте подключение и попробуйте снова.",
      );
    throw error;
  } finally {
    clearTimeout(timer);
  }
}
const post = (path, data) =>
  api(path, {
    method: "POST",
    ...(data !== undefined ? { body: JSON.stringify(data) } : {}),
  });
async function optional(path) {
  try {
    return await api(path);
  } catch (e) {
    if (e.status === 404) return null;
    throw e;
  }
}
async function load() {
  state.loadError = null;
  state.user = await api("/auth/me");
  const [company, products, applications, registry] = await Promise.all([
    optional("/company"),
    api("/credit-products"),
    api("/applications"),
    optional("/company/registry-status"),
  ]);
  state.company = company;
  state.registry = registry;
  state.products = products;
  state.applications = applications;
  state.financials = null;
  state.history = null;
  state.creditConnection = null;
  if (company) {
    [state.financials, state.history, state.creditConnection] = await Promise.all([
      optional("/company/financials"),
      optional("/company/credit-history"),
      optional("/company/credit-history/connection"),
    ]);
  }
}
function header(title, subtitle, action = "") {
  return `<div class="page-head"><div><h1>${title}</h1><p>${subtitle}</p></div>${action}</div>`;
}
function shell(content, page) {
  const nav = [
    ["home", "Главная", "/"],
    ["products", "Кредитные продукты", "/products"],
    ["applications", "Мои заявки", "/applications"],
    ["company", "Компания", "/company"],
    ["documents", "Документы", "/documents"],
  ];
  if (staffRoles.has(state.user?.role)) nav[1] = ["admin", "Управление", "/admin"];
  return `<div class="layout"><aside class="sidebar">${brand}<div class="eyebrow">Рабочее пространство</div><nav class="nav" aria-label="Основная навигация">${nav.map(([key, label, url]) => `<a href="#${url}" aria-label="${esc(label)}" data-mobile-label="${esc(({home:"Главная",products:"Кредиты",applications:"Заявки",company:"Компания",documents:"Документы",admin:"Управление"})[key] || label)}" ${page === key ? 'class="active" aria-current="page"' : ""}>${icon(key)}<span class="nav-label">${label}</span></a>`).join("")}</nav><div class="sidebar-bottom"><h3>Один кабинет.<br>Больше возможностей.</h3><p>На вашей стороне.</p></div></aside><main class="workspace"><header class="topbar"><div><div class="company-title">${esc(state.company?.name || "Кабинет предпринимателя")}</div><small>${state.company ? "ИНН " + esc(state.company.inn) : "Компания пока не привязана"}</small></div><div class="user-menu"><button class="bell" data-action="notifications" aria-label="Уведомления"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4"/></svg><span data-unread hidden></span></button><button class="avatar" data-action="account" aria-label="Ваш аккаунт">${esc(
    (state.user?.full_name || "")
      .split(" ")
      .slice(0, 2)
      .map((s) => s[0])
      .join(""),
  )}</button></div></header>${content}<footer class="page-footer"><span>Альфа · Бизнес начинается с вас.</span><span>Демонстрационный кабинет · Условия не являются офертой</span></footer></main></div>`;
}
function auth(register = false) {
  return `<main class="auth"><header class="auth-header">${brand}<span class="eyebrow">Для тех, кто делает</span><span class="muted">Кабинет предпринимателя</span></header><section class="auth-card"><div class="eyebrow">Кабинет бизнеса</div><h1>${register ? "Создайте аккаунт." : "С возвращением."}</h1><p class="muted" style="font-size:12px">${register ? "Первый шаг к большим планам." : "Войдите, чтобы продолжить с главного."}</p><nav class="tabs" aria-label="Авторизация"><a href="#/login" class="${register ? "" : "active"}">Войти</a><a href="#/register" class="${register ? "active" : ""}">Регистрация</a></nav><form data-form="${register ? "register" : "login"}"><div data-error role="alert"></div>${register ? '<label class="field">Имя и фамилия<input name="full_name" autocomplete="name" placeholder="Иван Иванов" required maxlength="255"></label>' : ""}<label class="field">${register ? "Электронная почта" : "Почта или логин"}<input name="email" type="${register ? "email" : "text"}" inputmode="email" autocomplete="${register ? "email" : "username"}" autocapitalize="none" spellcheck="false" placeholder="${register ? "you@company.ru" : "Почта или логин"}" required maxlength="320"></label><label class="field">Пароль<span class="password-input"><input name="password" type="password" autocomplete="${register ? "new-password" : "current-password"}" placeholder="${register ? "Не менее 8 символов" : "Ваш пароль"}" required minlength="${register ? 8 : 1}" maxlength="128" ${register ? 'aria-describedby="password-feedback"' : ""}><button type="button" class="password-toggle" data-action="toggle-password" aria-label="Показать пароль" title="Показать пароль" aria-pressed="false"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/><path class="eye-slash" d="m4 4 16 16"/></svg></button></span></label>${register ? '<div class="password-feedback" id="password-feedback" aria-live="polite"><div class="password-meter" aria-hidden="true"><span></span></div><p data-password-label>Сложность пароля: введите пароль</p><p class="hint">От 8 символов. Используйте буквы, цифры и символы.</p></div>' : ""}<button class="primary wide" type="submit">${register ? "Создать аккаунт" : "Войти в кабинет"} <span aria-hidden="true">↗</span></button></form><p class="auth-note">Ваше пространство для работы с бизнесом</p></section><footer class="auth-footer"><strong>На вашей стороне.</strong><span>Альфа · Бизнес начинается с вас.</span><span class="eyebrow">Кабинет предпринимателя</span></footer></main>`;
}
function companyRequired(title, message) {
  return (
    header(title, message) +
    '<section class="card empty"><h2>Добавьте вашу компанию.</h2><p>Привяжите ИНН, чтобы работать с данными своего бизнеса.</p><a class="primary" href="#/company">Привязать компанию ↗</a></section>'
  );
}
function linkCompany() {
  return (
    header(
      "Познакомимся с вашим бизнесом.",
      "Привяжите компанию по ИНН, чтобы продолжить работу с заявками.",
    ) +
    `<section class="card link-card empty"><div class="symbol">▦</div><h2>Всё начинается с вашей компании.</h2><p>Данные организации и финансовые показатели<br>появятся после привязки.</p><form data-form="link"><div data-error role="alert"></div><label class="field">ИНН компании<input name="inn" inputmode="numeric" pattern="[0-9]{10}([0-9]{2})?" minlength="10" maxlength="12" placeholder="10 или 12 цифр" required></label><button class="primary wide">Привязать компанию ↗</button></form><p class="hint" style="margin-top:25px">Сведения загружаются из демонстрационного источника.</p></section>`
  );
}
const productById = (id) => state.products.find((p) => p.id === id);
function productCard(p, index = 0, compact = false) {
  const category = /развит|инвест/i.test(p.name) ? "investment" : /оборот/i.test(p.name) ? "working_capital" : "urgent";
  return `<a href="#/new?purpose=${category}" class="card product interactive-card ${index === 0 ? "featured" : ""}"><div class="eyebrow">${/развит|инвест/i.test(p.name) ? "Для развития" : /оборот/i.test(p.name) ? "Для оборота" : "Для срочных задач"}</div><h2>${esc(p.name)}</h2><p>${esc(p.description)}</p>${compact ? "" : '<div class="eyebrow" style="margin-top:18px">Сумма</div>'}<div class="amount">до ${money(p.max_amount)}</div><dl><div><dt>Срок</dt><dd>до ${esc(p.max_term_months)} месяцев</dd></div><div><dt>Ставка</dt><dd>от ${esc(percent(p.interest_rate))}</dd></div></dl><span class="product-cta ${index === 0 ? "primary" : "secondary"}">${compact ? "Оформить заявку" : "Подать заявку"} ↗</span></a>`;
}
function metric(label, value, note) {
  return `<article class="card metric"><p>${label}</p><strong>${value}</strong><small>${note}</small></article>`;
}
function home() {
  const intro =
    header(
      "Кредитный кабинет для вашего бизнеса.",
      "От знакомства с компанией до понятного решения по заявке — в одном месте.",
      `<a class="primary" href="#/${state.company ? "new" : "company"}">${state.company ? "Выбрать кредит" : "Добавить компанию"} ↗</a>`,
    ) +
    `<section class="platform-intro"><div class="section-heading"><h2>Как работает платформа</h2></div><div class="grid intro-grid"><a class="card intro-card" href="#/company"><span class="step-number">1</span><h3>Расскажите о компании</h3><p>Привяжите ИНН и проверьте сведения о бизнесе. Финансовые показатели находятся внутри раздела «Компания».</p><span class="intro-card-link">Открыть компанию <span aria-hidden="true">→</span></span></a><a class="card intro-card" href="#/new"><span class="step-number">2</span><h3>Заполните одну заявку</h3><p>Укажите сумму, срок и задачу бизнеса. Система подберёт подходящий продукт и рассчитает предварительные условия.</p><span class="intro-card-link">Рассчитать условия <span aria-hidden="true">→</span></span></a><a class="card intro-card" href="#/applications"><span class="step-number">3</span><h3>Получите объяснение</h3><p>Модель анализирует данные заявки. Решение, условия ручной проверки и история сохраняются в кабинете.</p><span class="intro-card-link">Мои заявки <span aria-hidden="true">→</span></span></a></div><section class="banner"><div><span class="eyebrow">Альфа · Бизнес</span><h2>Ваши планы. Один понятный маршрут.</h2><p>Кабинет помогает подготовить данные бизнеса, выбрать продукт и следить за рассмотрением. Это демонстрационный проект в стиле Альфа-Банка: он не выдаёт кредиты и не заменяет решение банка.</p></div><a class="secondary" href="https://alfabank.ru/sme/" target="_blank" rel="noopener noreferrer">Альфа-Банк для бизнеса ↗</a></section></section>`;
  if (!state.company) return intro;
  const f = state.financials;
  return (
    intro +
    '<div class="section-heading"><h2>Показатели вашей компании</h2></div>' +
    `<section class="grid metrics">${metric("Выручка за год", f ? money(f.revenue_annual) : "—", "За отчётный период")}${metric("Прибыль за год", f ? money(f.profit_annual) : "—", "По данным компании")}${metric("Сотрудники", f?.employees != null ? esc(f.employees) : "Нет данных", "Команда вашей компании")}${metric("Текущая задолженность", f ? money(f.current_debt) : "—", "По данным компании")}</section><section class="card finance-overview interactive-card"><div class="section-heading" style="margin:0 0 15px"><div><h2>Финансы в движении</h2><p class="hint" style="margin:8px 0">Финансовые показатели за отчётный период</p></div><a class="stretched-link finance-link" href="#/company/financials">Все показатели ↗</a></div>${
      f
        ? `<div class="chart">${[
            ["Выручка", f.revenue_annual],
            ["Прибыль", f.profit_annual],
            ["Расходы", f.expenses_annual],
            ["Задолженность", f.current_debt],
          ]
            .map(
              ([label, v], i) =>
                `<div class="bar-column"><span class="hint">${money(v)}</span><div class="bar ${i === 0 ? "current" : ""}" style="height:${v == null ? 0 : Math.max(3, Math.min(85, (Math.abs(v) / Math.max(1, f.revenue_annual || 0, f.expenses_annual || 0)) * 85))}%"></div><small>${label}</small></div>`,
            )
            .join(
              "",
            )}</div><p class="hint" style="margin:20px 0 0">Источник: ${esc(sourceLabel(f.source))}${f.report_year ? " · " + esc(f.report_year) + " г." : ""} · Обновлено ${date(f.updated_at)}</p>`
        : '<p class="muted">Финансовые показатели пока не загружены.</p>'
    }</section><div class="section-heading"><h2>Под задачи вашего бизнеса</h2><a href="#/products">Все продукты ↗</a></div><section class="grid products compact-products">${state.products
      .slice(0, 3)
      .map((p, i) => productCard(p, i, true))
      .join("")}</section>`
  );
}
function products() {
  return (
    header(
      "Для следующего шага.",
      "Ознакомьтесь с базовыми условиями. Любая кнопка откроет единую заявку — продукт подберём по вашей задаче.",
    ) +
    `<section class="grid products">${state.products.map((p, i) => productCard(p, i)).join("")}</section><section class="banner"><h2>Ваши планы — в центре внимания.</h2><p>Заполните одну заявку. Её статус и решение появятся в личном кабинете.</p></section><p class="hint" style="margin-top:20px">Каталог демонстрационный. Индивидуальные условия определяются после рассмотрения заявки.</p>`
  );
}
const dataList = (rows) =>
  `<dl class="data-list">${rows.map(([label, value]) => `<div><dt>${label}</dt><dd>${esc(value ?? "—")}</dd></div>`).join("")}</dl>`;
function companyTabs(finance = false) {
  return `<nav class="tablinks" aria-label="Разделы компании"><a href="#/company" ${finance ? "" : 'class="active" aria-current="page"'}>Основная информация</a><a href="#/company/financials" ${finance ? 'class="active" aria-current="page"' : ""}>Финансовые данные</a></nav>`;
}
const companyStatus = (value) =>
  ({
    ACTIVE: "Действует",
    LIQUIDATING: "В процессе ликвидации",
    LIQUIDATED: "Ликвидирована",
    BANKRUPT: "Банкротство",
    REORGANIZING: "Реорганизация",
  })[value] || value;
function company() {
  const c = state.company;
  return (
    header("Компания в деталях.", "Проверьте данные перед подачей заявки.") +
    companyTabs() +
    `<section class="card"><div class="section-heading" style="margin:0 0 15px"><h2>Данные компании</h2><span class="pill ${c.status === "ACTIVE" ? "green" : ""}">${esc(companyStatus(c.status))}</span></div><p class="hint">${c.data_source === "DEMO" ? "Демонстрационный источник: реквизиты не запрашиваются в реестрах. Отсутствующие сведения не подтверждены." : "Реквизиты из внешнего источника: " + esc(c.data_source)}</p>${dataList(
      [
        ["Название", c.name],
        ["Полное название", c.full_name || "Не предоставлено источником"],
        ["ИНН", c.inn],
        ["КПП", c.kpp || "Не предоставлен источником"],
        ["Юридический адрес", c.address || "Не предоставлен источником"],
        ["ОГРН", c.ogrn || "Не предоставлен источником"],
        ["Дата регистрации", date(c.registration_date)],
        ["Статус", companyStatus(c.status)],
        ["ОКВЭД", c.okved || "Не предоставлен источником"],
        ["Руководитель", c.director_name || "Не предоставлен источником"],
      ],
    )}</section><div class="actions"><a class="primary" href="#/products">К выбору продукта ↗</a><a class="secondary" href="#/company/financials">Финансовые данные</a><button class="secondary" data-action="refresh-company">${state.registry?.configured ? "Обновить реквизиты" : "Подключение реестра"}</button><button class="secondary" data-action="show-unlink">Отвязать компанию</button></div><section class="card registry-info" hidden><h3>Откуда берутся реквизиты компании</h3><p>ЕГРЮЛ и ЕГРИП — государственные реестры юридических лиц и индивидуальных предпринимателей. Наше приложение может получать реквизиты из них через API DaData по ИНН: название, ОГРН, КПП, адрес, руководителя и ОКВЭД.</p><p>${state.registry?.configured ? "Источник подключён. Обновление загрузит доступные реквизиты; ранее поданные заявки останутся без изменений." : "Сейчас источник не подключён. Администратору нужно настроить серверный доступ к DaData. До подключения отображаются демонстрационные данные."}</p><p class="hint">Кнопка не обновляет финансовую отчётность и кредитную историю — для них нужны отдельные источники.</p><a class="secondary" href="https://egrul.nalog.ru/" target="_blank" rel="noopener noreferrer">Проверить сведения на сайте ФНС ↗</a><button class="ghost" data-action="close-registry-info">Закрыть</button></section><section class="card unlink-confirm" hidden><h3>Отвязать компанию от аккаунта?</h3><p>Вы сможете добавить другую компанию. Существующие заявки и их история сохранятся. Запись компании не удаляется у других пользователей.</p><div class="actions"><button class="primary" data-action="unlink-company">Отвязать</button><button class="secondary" data-action="cancel-unlink">Отмена</button></div></section>`
  );
}
function sourceLabel(source) {
  return ({ DOCUMENT_USER_CONFIRMED:'Из документа · проверено пользователем, не источником', DADATA:'DaData', DEMO:'Демонстрационные данные', USER_INPUT:'Введено пользователем · не подтверждено', USER_VERIFIED:'Введено пользователем · не подтверждено', MIXED:'Несколько источников', UNAVAILABLE:'Источник не предоставил данные', CONSENT_REQUIRED:'Нужно согласие на запрос отчёта', BKI_GATEWAY:'Подключённый источник БКИ' })[source] || 'Источник не указан';
}
function financials() {
  const f = state.financials;
  const h = state.history;
  const locked = sessionStorage.getItem('credit-onboarding') ? 'confirm' : 'true';
  return header('Цифры, за которыми ваш бизнес.', 'Проверьте доступные данные и дополните сведения из вашей отчётности.') + companyTabs(true) +
    `<p class="source-explainer">${esc(sourceLabel(f?.source))}. Пустое поле означает, что сведений нет. Ноль указывайте только при подтверждённом отсутствии суммы. Ручные данные требуют проверки специалистом. DaData не предоставляет кредитную историю БКИ.</p><section class="columns"><form class="card form-card" data-form="financials" data-locked="${locked}"><h2>Финансовые данные</h2><p class="hint">Загружено ${date(f?.updated_at)} · Период: ${f?.report_year || 'не указан'}</p><div data-error role="alert"></div><div class="form-row"><label class="field">Год отчётности<input readonly type="number" name="report_year" min="1900" max="${new Date().getFullYear()}" step="1" value="${esc(f?.report_year ?? '')}" placeholder="Например, ${new Date().getFullYear()-1}"></label>${Object.entries(fieldNames).map(([key,label]) => {
      const meta=f?.field_sources?.[key];
      const source=typeof meta === 'object' ? meta?.source : meta;
      return `<label class="field">${label}${key === 'employees' ? '' : ' · ₽'}<input readonly name="${key}" type="number" ${key === 'profit_annual' ? '' : 'min="0"'} step="${key === 'employees' ? '1' : '0.01'}" value="${esc(f?.[key] ?? '')}" placeholder="Нет данных"><span class="hint">${esc(sourceLabel(source || (f?.[key] != null ? f?.source : 'UNAVAILABLE')))}${meta?.report_year ? ' · '+esc(meta.report_year)+' г.' : ''}</span></label>`;
    }).join('')}</div><div class="actions"><a class="secondary" href="#/documents">Загрузить отчётность ↑</a><button type="button" class="secondary" data-action="edit-financials">Изменить показатели</button><button type="button" class="secondary" data-action="refresh-financials">Обновить из источника ↻</button><button class="primary finance-save">${sessionStorage.getItem('credit-onboarding') ? 'Сохранить и продолжить ↗' : 'Сохранить изменения'}</button></div></form><form class="card form-card" data-form="credit-history" data-locked="true"><h2>Кредитная история</h2><p class="hint">${esc(sourceLabel(h?.source))} · ${date(h?.updated_at)}</p><p>${state.creditConnection?.configured ? 'Отчёт запрашивается из отдельного источника БКИ с вашим согласием.' : 'Источник БКИ пока не подключён.'} Можно указать сведения из собственного кредитного отчёта: они останутся неподтверждёнными и потребуют проверки.</p>${state.creditConnection?.configured ? state.creditConnection.consent_active ? '<div class="actions"><button type="button" class="secondary" data-action="refresh-credit">Запросить отчёт БКИ</button><button type="button" class="ghost" data-action="revoke-credit-consent">Отозвать согласие</button></div>' : '<label class="credit-consent"><input type="checkbox" data-credit-consent> Согласен на запрос кредитного отчёта указанной компании для рассмотрения кредитной заявки. Согласие действует 180 дней, его можно отозвать.</label><button type="button" class="secondary" data-action="grant-credit-consent">Разрешить запрос отчёта</button>' : ''}<div data-error role="alert"></div>${Object.entries({active_credits:'Активные кредиты',closed_credits:'Закрытые кредиты',overdue_count:'Количество просрочек',overdue_amount:'Сумма просрочек · ₽'}).map(([key,label]) => `<label class="field">${label}<input readonly type="number" name="${key}" min="0" step="${key === 'overdue_amount' ? '0.01' : '1'}" value="${esc(h?.[key] ?? '')}" placeholder="Нет данных"></label>`).join('')}<div class="actions"><button type="button" class="secondary" data-action="edit-financials">Указать сведения</button><button class="primary">Сохранить сведения</button></div></form></section>`;
}

const percent = (value) =>
  new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(
    Number(value),
  ) + "% годовых";
function loanEstimate(amount, months, rate) {
  const principal = Number(amount),
    term = Number(months),
    monthly = Number(rate) / 1200;
  if (
    !Number.isFinite(principal) ||
    !Number.isInteger(term) ||
    principal <= 0 ||
    term <= 0 ||
    !Number.isFinite(monthly) ||
    monthly < 0
  )
    return null;
  const payment =
    monthly === 0
      ? principal / term
      : (principal * monthly) / (1 - Math.pow(1 + monthly, -term));
  return {
    payment,
    total: payment * term,
    interest: payment * term - principal,
  };
}
function quotedTerms(pricing) {
  return `<h3>${esc(pricing.product_name)}</h3><p class="status-note">${esc(pricing.selection_reason)}</p>${dataList(
    [
      ["Сумма", money(pricing.requested_amount)],
      ["Срок", pricing.term_months + " месяцев"],
      ["Расчётная ставка", percent(pricing.annual_rate)],
      ["Платёж в месяц", "≈ " + money(pricing.monthly_payment)],
      ["Проценты за весь срок", "≈ " + money(pricing.total_interest)],
      ["Всего к возврату", "≈ " + money(pricing.total_repayment)],
    ],
  )}<details class="tariff-rules"><summary>Как рассчитана ставка</summary>${dataList(
    [
      ["Базовая ставка", percent(pricing.base_rate)],
      ["Надбавка за сумму", "+" + pricing.amount_adjustment + " п.п."],
      ["Надбавка за срок", "+" + pricing.term_adjustment + " п.п."],
      ["Версия правил", pricing.rules_version],
    ],
  )}<p class="hint">Сумма: до 1 млн — +0 п.п.; свыше 1 до 5 млн — +0,5 п.п.; свыше 5 млн — +1 п.п. Срок: до 12 мес. — +0 п.п.; 13–36 мес. — +0,5 п.п.; более 36 мес. — +1 п.п. Это демонстрационные правила проекта.</p></details><p class="hint">${esc(pricing.disclaimer)}</p>`;
}
function estimatedTerms(amount, months, product, pricing = null) {
  if (pricing) return quotedTerms(pricing);
  if (!product)
    return '<p class="hint">Ставка выбранного продукта недоступна. Уточните условия в каталоге.</p>';
  const estimate = loanEstimate(amount, months, product.interest_rate);
  return (
    dataList([
      ["Ставка по каталогу", "от " + percent(product.interest_rate)],
      [
        "Платёж в месяц",
        estimate ? "≈ " + money(estimate.payment) : "Укажите сумму и срок",
      ],
      [
        "Проценты за весь срок",
        estimate ? "≈ " + money(estimate.interest) : "—",
      ],
      ["Всего к возврату", estimate ? "≈ " + money(estimate.total) : "—"],
    ]) +
    '<p class="hint">Примерный расчёт равными ежемесячными платежами по минимальной ставке каталога. Без комиссий, страховок и дополнительных услуг. Индивидуальная ставка и график пока не определены.</p>'
  );
}
function applicationForm(p, existing = null) {
  const requestedCategory = new URLSearchParams(location.hash.split("?")[1] || "").get("purpose") || sessionStorage.getItem("credit-selected-purpose");
  const category = existing?.purpose_category || (["investment", "working_capital", "urgent"].includes(requestedCategory) ? requestedCategory : "other");
  if (!existing) sessionStorage.removeItem("credit-selected-purpose");
  const minAmount = Math.min(...state.products.map((p) => p.min_amount));
  const maxAmount = Math.max(...state.products.map((p) => p.max_amount));
  const minTerm = Math.min(...state.products.map((p) => p.min_term_months));
  const maxTerm = Math.max(...state.products.map((p) => p.max_term_months));
  return (
    header(
      "Одна заявка. Подходящие условия.",
      "Укажите сумму, срок и цель. Мы подберём продукт и покажем предварительную ставку.",
    ) +
    `<div class="columns"><form class="card form-card" data-form="application" ${existing ? `data-id="${esc(existing.id)}"` : ""}><h2>Параметры кредита</h2><div data-error role="alert"></div><div class="form-row"><label class="field">Сумма кредита · ₽<input name="requested_amount" type="number" min="${minAmount}" max="${maxAmount}" step="0.01" value="${esc(existing?.requested_amount ?? minAmount)}" required><span class="hint">От ${money(minAmount)} до ${money(maxAmount)}</span></label><label class="field">Срок кредита · месяцев<input name="term_months" type="number" min="${minTerm}" max="${maxTerm}" step="1" value="${esc(existing?.term_months ?? minTerm)}" required><span class="hint">От ${minTerm} до ${maxTerm} месяцев</span></label></div><label class="field">На что нужен кредит<select name="purpose_category">${[
      ["investment", "Оборудование и развитие бизнеса"],
      ["working_capital", "Закупки и оборотные средства"],
      ["urgent", "Срочные небольшие расходы"],
      ["other", "Другая задача / подобрать по условиям"],
    ]
      .map(
        ([key, label]) =>
          `<option value="${key}" ${category === key ? "selected" : ""}>${label}</option>`,
      )
      .join(
        "",
      )}</select></label><label class="field">Опишите цель кредита<textarea name="purpose" maxlength="500" required placeholder="Что планируете приобрести или развивать?">${esc(existing?.purpose || "")}</textarea></label><label class="field">Дополнительные сведения · необязательно<textarea name="additional_info" maxlength="1000" placeholder="Стоимость проекта, собственные средства, ожидаемый результат и источник погашения">${esc(existing?.additional_info || "")}</textarea></label><p class="hint">Подбор продукта и расчёт ставки выполняет backend по демоправилам. Модель объясняет решение, но не назначает проценты.</p><div class="actions"><button class="primary" name="intent" value="submit" disabled>Отправить заявку ↗</button><button class="secondary" name="intent" value="draft" disabled>Сохранить черновик</button></div></form><aside class="card summary"><div class="eyebrow">Умный подбор · предварительный расчёт</div><section class="estimate" id="quote-content" aria-live="polite"><p class="status-note">Подбираем доступный продукт…</p></section><p class="hint">Расчёт не означает одобрение кредита. Итог рассмотрения появится в разделе «Мои заявки».</p></aside></div>`
  );
}
let quoteGeneration = 0,
  quoteTimer;
async function updateQuote() {
  const form = root.querySelector('[data-form="application"]');
  if (!form) return;
  const generation = ++quoteGeneration;
  const buttons = form.querySelectorAll('button[name="intent"]');
  form.dataset.quoteReady = "false";
  buttons.forEach((b) => (b.disabled = true));
  const content = root.querySelector("#quote-content");
  const amount = form.elements.requested_amount,
    term = form.elements.term_months;
  if (!amount.validity.valid || !term.validity.valid) {
    content.textContent = "Укажите допустимую сумму и срок для расчёта.";
    return;
  }
  content.innerHTML = '<p class="status-note">Рассчитываем условия…</p>';
  try {
    const pricing = await post("/applications/quote", {
      requested_amount: amount.value,
      term_months: Number(term.value),
      purpose_category: form.elements.purpose_category.value,
    });
    if (generation !== quoteGeneration || !form.isConnected) return;
    content.innerHTML = quotedTerms(pricing);
    form.dataset.quoteReady = "true";
    buttons.forEach((b) => (b.disabled = false));
  } catch (e) {
    if (generation !== quoteGeneration || !form.isConnected) return;
    content.textContent = e.message;
    if (
      e.status === 422 &&
      e.body?.detail === "No product matches requested amount and term"
    ) {
      const byAmount = state.products.filter(
        (p) =>
          Number(amount.value) >= p.min_amount &&
          Number(amount.value) <= p.max_amount,
      );
      const byTerm = state.products.filter(
        (p) =>
          Number(term.value) >= p.min_term_months &&
          Number(term.value) <= p.max_term_months,
      );
      const tips = [];
      if (byAmount.length)
        tips.push(
          `Для суммы ${money(amount.value)} доступны сроки: ${byAmount.map((p) => `${p.min_term_months}–${p.max_term_months} мес.`).join(", ")}.`,
        );
      if (byTerm.length)
        tips.push(
          `Для срока ${term.value} мес. доступная сумма начинается от ${money(Math.min(...byTerm.map((p) => p.min_amount)))}.`,
        );
      const tip = document.createElement("p");
      tip.className = "hint";
      tip.textContent = tips.join(" ");
      content.append(tip);
    }
  }
}
function applications() {
  return (
    header(
      "Ваши планы — в работе.",
      "Все заявки, их статусы и решения — в одном месте.",
      '<a class="primary" href="#/new">Новая заявка ↗</a>',
    ) +
    `<div class="application-tools"><label>Поиск заявок<input type="search" data-application-search placeholder="Номер, продукт или цель" value="${esc(applicationFilters.search)}"></label><label>Статус<select data-application-status>${[["", "Все статусы"], ...Object.entries(statusNames)].map(([key,label]) => `<option value="${key}" ${applicationFilters.status === key ? "selected" : ""}>${label}</option>`).join("")}</select></label><label>Сортировка<select data-application-sort>${[["new", "Сначала новые"],["old", "Сначала старые"],["amount", "Сначала большая сумма"],["amount-asc", "Сначала меньшая сумма"],["term-asc", "Сначала короткий срок"],["term-desc", "Сначала длинный срок"]].map(([key,label]) => `<option value="${key}" ${applicationFilters.sort === key ? "selected" : ""}>${label}</option>`).join("")}</select></label></div>` +
    (filteredApplications().length
      ? `<section class="card table-wrap application-table"><table aria-label="Ваши заявки"><thead><tr><th scope="col">Продукт / заявка</th><th scope="col">Сумма</th><th scope="col">Срок</th><th scope="col">Предварительная ставка</th><th scope="col">Статус</th><th scope="col">Дата</th><th scope="col">Действие</th></tr></thead><tbody>${filteredApplications().map((a) => `<tr><td data-label="Продукт / заявка">${esc(a.pricing?.product_name || productById(a.product_id)?.name || "Кредит")}<div class="hint">№${esc(a.id.slice(0, 8))}</div></td><td data-label="Сумма">${money(a.requested_amount)}</td><td data-label="Срок">${a.term_months} мес.</td><td data-label="Предварительная ставка">${a.pricing ? percent(a.pricing.annual_rate) : productById(a.product_id) ? "от " + percent(productById(a.product_id).interest_rate) + " (каталог)" : "Нет данных"}</td><td data-label="Статус">${pill(a.status)}</td><td data-label="Дата">${date(a.created_at)}<small class="application-time">${time(a.created_at)}</small></td><td data-label="Действие"><a href="#/applications/${a.id}">Открыть ↗</a></td></tr>`).join("")}</tbody></table></section>`
      : `<section class="card empty"><h2>${state.applications.length ? "Ничего не найдено" : "Большие планы начинаются с первого шага."}</h2><p>${state.applications.length ? "Измените поисковый запрос или статус." : "Здесь появятся ваши заявки и результаты рассмотрения."}</p><a class="primary" href="#/products">Выбрать продукт ↗</a></section>`)
  );
}
async function details(id) {
  const a = await api("/applications/" + id);
  const [events, decision] = await Promise.all([
    api("/applications/" + id + "/history"),
    optional("/applications/" + id + "/decision"),
  ]);
  const p = productById(a.product_id);
  const submitting = state.submitting === id;
  const reviewed = events.find(
    (e) => e.event_type === "APPLICATION_REVIEW_RECORDED",
  );
  const missingEvent = events
    .filter((e) => e.event_type === "APPLICATION_DATA_REQUIRED")
    .at(-1);
  const missingFields = missingEvent?.details?.required_fields || [];
  const effectiveOutcome = reviewed
    ? reviewed.details.review_outcome
    : decision?.outcome;
  const title =
    effectiveOutcome === "APPROVED"
      ? "Хорошие новости для ваших планов."
      : effectiveOutcome === "REJECTED"
        ? "Решение по вашей заявке."
        : decision
          ? "Давайте уточним детали."
          : "Ваша заявка уже в работе.";
  let result = header(
    title,
    `Заявка №${esc(id.slice(0, 8))} · ${esc(p?.name || "Кредит")}`,
  );
  if (submitting)
    result +=
      '<div class="loading"><span class="spinner"></span><span>Модель рассматривает заявку. Можно перейти к другим страницам — результат сохранится в кабинете.</span></div>';
  if (decision)
    result += `<section class="card" style="margin-bottom:24px"><div class="decision-head"><div class="decision-symbol ${effectiveOutcome === "REJECTED" ? "rejected" : effectiveOutcome === "CONDITIONAL_APPROVAL" ? "review" : ""}">${effectiveOutcome === "APPROVED" ? "✓" : effectiveOutcome === "REJECTED" ? "×" : "↗"}</div><div><h2>${effectiveOutcome === "APPROVED" ? "Предварительно одобрено" : effectiveOutcome === "REJECTED" ? "Заявка отклонена" : "Требуется ручная проверка"}</h2><p>${reviewed ? "Учтено решение специалиста. Первоначальная оценка модели сохранена ниже." : decision.source === "AI" ? "Предварительное решение · Демонстрационный режим" : "Резервные правила · Ответ модели недоступен"}</p></div></div><p style="font-size:14px">${esc(decision.explanation)}</p><div class="columns"><div>${decision.conditions.length ? `<h3 style="font-size:16px">Что нужно уточнить</h3><ul class="factor-list">${decision.conditions.map((v) => `<li>${esc(v)}</li>`).join("")}</ul>` : '<h3 style="font-size:16px">Условия выбранного продукта</h3>'}${estimatedTerms(a.requested_amount, a.term_months, p, a.pricing)}${
      state.user.role === "REVIEWER"
        ? `<details class="reviewer-scoring"><summary>Внутренняя оценка для специалиста</summary>${dataList(
            [
              [
                "Уровень риска",
                { Low: "Низкий", Medium: "Средний", High: "Высокий" }[
                  decision.risk_level
                ],
              ],
              ["Оценка риска", decision.risk_score + " / 100"],
            ],
          )}<ul class="factor-list">${decision.top_factors.map((v) => `<li>${esc(v)}</li>`).join("")}</ul></details>`
        : ""
    }</div><div><h3 style="font-size:16px">Следующий шаг</h3><p class="status-note">${esc(decision.next_step)}</p>${dataList(
      [
        [
          "Подобранный продукт",
          a.pricing?.product_name || p?.name || decision.recommended_product,
        ],
      ],
    )}</div></div>${effectiveOutcome === "APPROVED" ? '<p class="hint">Кредитное предложение, документы и принятие условий пока не доступны. Здесь отображается предварительное решение.</p>' : ""}</section>`;
  result += `<div class="columns"><section class="card"><div class="section-heading" style="margin:0 0 15px"><h2>${esc(p?.name || "Параметры заявки")}</h2>${pill(a.status)}</div>${dataList(
    [
      ["Сумма кредита", money(a.requested_amount)],
      ["Срок", a.term_months + " месяцев"],
      ["Компания", state.company.name],
      ["Дата подачи", date(a.created_at)],
      ["Цель", a.purpose],
      ...(a.additional_info
        ? [["Дополнительные сведения", a.additional_info]]
        : []),
    ],
  )}<div class="actions"><button class="secondary" data-action="refresh">Обновить статус ↻</button>${["DRAFT", "NEED_MORE_DATA"].includes(a.status) && !submitting ? `<a class="primary" href="#/edit/${id}">${a.status === "DRAFT" ? "Продолжить заявку" : "Исправить заявку"} ↗</a>` : ""}<a class="ghost" href="#/applications">К моим заявкам</a></div>${a.status === "NEED_MORE_DATA" ? `<p class="hint">Для продолжения дополните данные: ${missingFields.map((v) => esc(fieldNames[v.split(".").at(-1)] || ({"financials.report_year":"Год отчётности","company.registration_date":"Дата регистрации компании","credit_history.active_credits":"Активные кредиты","credit_history.closed_credits":"Закрытые кредиты","credit_history.overdue_count":"Количество просрочек","credit_history.overdue_amount":"Сумма просрочек"})[v] || v)).join(", ") || "финансовые показатели компании"}. Затем отправьте заявку повторно.</p><a class="secondary" href="#/company/financials">Дополнить финансовые данные</a>` : ""}</section><aside class="card"><h2>Как движется заявка</h2><ol class="timeline">${events.map((e) => `<li>${esc(eventNames[e.event_type] || statusNames[e.to_status] || "Обновление заявки")}<small>${date(e.occurred_at)} · ${new Date(e.occurred_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</small></li>`).join("")}</ol></aside></div>`;
  if (state.user.role === "REVIEWER" && a.status === "MANUAL_REVIEW")
    result += `<form class="card" style="margin-top:24px" data-form="review" data-id="${id}"><h2>Решение специалиста</h2><div data-error role="alert"></div><label class="field">Решение<select name="outcome"><option value="APPROVED">Одобрить</option><option value="REJECTED">Отклонить</option></select></label><label class="field">Комментарий<textarea name="comment" maxlength="1000"></textarea></label><button class="primary">Сохранить решение</button></form>`;
  return result;
}
let generation = 0;
async function render() {
  const current = ++generation;
  const path = (location.hash.slice(1) || "/").split("?")[0];
  if (!state.token) {
    root.innerHTML = auth(path === "/register");
    prepareMobileInputs(root);
    return;
  }
  if (!state.user) {
    root.innerHTML = '<div class="initial">Загружаем ваш кабинет…</div>';
    try {
      await load();
    } catch (e) {
      if (current !== generation) return;
      if (!state.token) {
        render();
        return;
      }
      root.innerHTML = shell(
        header("Не удалось загрузить кабинет.", esc(e.message)) +
          '<button class="primary" data-action="reload">Попробовать снова</button>',
        "home",
      );
      return;
    }
  }
  if (current !== generation) return;
  try {
    let content,
      page = "home";
    if (path === "/admin" || path.startsWith("/admin/")) {
      content = await adminPage(path); page = "admin";
    } else if (path === "/products") {
      content = products();
      page = "products";
    } else if (path === "/company") {
      content = state.company ? company() : linkCompany();
      page = "company";
    } else if (path === "/financials" || path === "/company/financials") {
      content = state.company
        ? financials()
        : companyRequired(
            "Финансовые данные",
            "Финансовые показатели появятся после привязки компании.",
          );
      page = "company";
    } else if (path === "/documents") {
      content = documentsPage();
      page = "documents";
    } else if (path === "/applications") {
      state.applications = await api("/applications");
      content = applications();
      page = "applications";
    } else if (path === "/new" || path.startsWith("/new/")) {
      const p = state.products[0];
      if (!p)
        throw new Error("Продукт не найден. Выберите продукт из каталога.");
      if (!state.company) {
        sessionStorage.setItem("credit-selected-product", p.id);
        const purpose = new URLSearchParams(location.hash.split("?")[1] || "").get("purpose");
        if (["investment", "working_capital", "urgent"].includes(purpose)) sessionStorage.setItem("credit-selected-purpose", purpose);
      }
      content = state.company
        ? applicationForm(p)
        : companyRequired(
            "Новая заявка",
            "Чтобы подать заявку, сначала привяжите компанию по ИНН.",
          );
      page = "products";
    } else if (path.startsWith("/edit/")) {
      const a = await api(
        "/applications/" + encodeURIComponent(path.split("/")[2]),
      );
      if (!["DRAFT", "NEED_MORE_DATA"].includes(a.status))
        throw new Error("Эту заявку уже нельзя редактировать.");
      content = applicationForm(productById(a.product_id), a);
      page = "applications";
    } else if (path.startsWith("/applications/")) {
      page = "applications";
      root.innerHTML = shell(
        '<div class="initial">Загружаем заявку…</div>',
        page,
      );
      content = await details(encodeURIComponent(path.split("/")[2]));
    } else content = home();
    if (current === generation) {
      root.innerHTML = shell(content, page);
      prepareMobileInputs(root);
      if (root.querySelector('[data-form="application"]')) updateQuote();
      updateUnreadBadge();
      refreshNotifications();
    }
  } catch (e) {
    if (current === generation)
      root.innerHTML = shell(
        header("Не удалось открыть страницу.", esc(e.message)) +
          '<a class="secondary" href="#/applications">К моим заявкам</a>',
        "applications",
      );
  }
}
async function submitApplication(id) {
  state.submitting = id;
  location.hash = "/applications/" + id;
  await render();
  try {
    const result = await post("/applications/" + id + "/submit");
    notice(
      result.status === "NEED_MORE_DATA"
        ? "Нужно дополнить данные компании."
        : "Рассмотрение завершено. Решение сохранено.",
    );
  } catch (e) {
    notice(e.message);
  } finally {
    state.submitting = null;
    try {
      state.applications = await api("/applications");
    } catch {}
    await render();
  }
}
function updatePassword(input) {
  const value = input.value;
  const feedback = root.querySelector("#password-feedback");
  if (!feedback) return;
  const length = [...value].length;
  input.setCustomValidity(
    length < 8 ? "Пароль должен содержать минимум 8 символов." : "",
  );
  const variety = [
    /[a-zа-яё]/i.test(value),
    /[A-ZА-ЯЁ]/.test(value) && /[a-zа-яё]/.test(value),
    /[0-9]/.test(value),
    /[^a-zа-яё0-9]/i.test(value),
  ].filter(Boolean).length;
  const common =
    /^(?:12345678|123456789|password|qwerty|пароль)/i.test(value) ||
    /^(.)\1+$/.test(value);
  const strength =
    length < 8
      ? 0
      : common || variety < 2
        ? 1
        : length >= 12 && variety >= 3
          ? 3
          : 2;
  feedback.dataset.strength = strength;
  feedback.querySelector("[data-password-label]").textContent = !length
    ? "Минимум 8 символов"
    : length < 8
      ? `Ещё ${8 - length} символов — минимум 8`
      : [
          "",
          "Сложность: низкая",
          "Сложность: нормальная",
          "Сложность: высокая",
        ][strength];
  const button = input.form.querySelector('button[type="submit"]');
  if (button) button.disabled = length < 8;
}
root.addEventListener("input", (event) => {
  const input = event.target;
  if (input.validity?.valid) {
    input.removeAttribute("aria-invalid");
    const error = input.closest("form")?.querySelector("[data-error]");
    if (error?.dataset.validationField === input.name) {
      error.textContent = "";
      error.className = "";
      delete error.dataset.validationField;
    }
  }
  if (event.target.matches('[data-form="register"] [name="password"]'))
    updatePassword(event.target);
  const form = event.target.closest('[data-form="application"]');
  if (!form) return;
  if (
    ["requested_amount", "term_months", "purpose_category"].includes(
      event.target.name,
    )
  ) {
    ++quoteGeneration;
    form.dataset.quoteReady = "false";
    form
      .querySelectorAll('button[name="intent"]')
      .forEach((b) => (b.disabled = true));
    clearTimeout(quoteTimer);
    quoteTimer = setTimeout(updateQuote, 300);
  }
});
root.addEventListener(
  "invalid",
  (event) => {
    event.preventDefault();
    const input = event.target,
      form = input.closest("form"),
      error = form?.querySelector("[data-error]");
    if (!error) return;
    const label =
      input.closest("label")?.childNodes[0]?.textContent?.trim() || "Поле";
    const message = input.validity.valueMissing
      ? `${label}: заполните это поле.`
      : input.validity.typeMismatch
        ? "Укажите корректный адрес электронной почты."
        : input.validity.rangeUnderflow
          ? `${label}: минимальное значение ${input.min}.`
          : input.validity.rangeOverflow
            ? `${label}: максимальное значение ${input.max}.`
            : input.validity.tooShort
              ? `${label}: минимум ${input.minLength} символов.`
              : `${label}: проверьте введённое значение.`;
    error.textContent = message;
    error.className = "error";
    error.dataset.validationField = input.name;
    input.setAttribute("aria-invalid", "true");
  },
  true,
);
root.addEventListener("change", (event) => {
  if (
    event.target.matches('[data-form="application"] [name="purpose_category"]')
  ) {
    clearTimeout(quoteTimer);
    updateQuote();
  }
});
root.addEventListener("submit", async (event) => {
  const form = event.target.closest("form[data-form]");
  if (!form) return;
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  const values = Object.fromEntries(new FormData(form));
  const buttons = [...form.querySelectorAll("button")];
  buttons.forEach((b) => (b.disabled = true));
  const error = form.querySelector("[data-error]");
  error.textContent = "";
  error.className = "";
  try {
    const type = form.dataset.form;
    if (type === "application" && state.submitting) {
      throw new Error(
        "Дождитесь завершения текущего рассмотрения. Результат появится в разделе «Мои заявки».",
      );
    }
    if (type === "register" && [...values.password].length < 8) {
      updatePassword(form.elements.password);
      throw new Error("Пароль должен содержать минимум 8 символов.");
    }
    if (type === "login" || type === "register") {
      const result = await post("/auth/" + type, values);
      state.token = result.access_token;
      sessionStorage.setItem("credit-token", state.token);
      state.user = null;
      await load();
      location.hash = staffRoles.has(state.user?.role) ? "/admin" : "/";
      await render();
    } else if (type === "link") {
      await post("/company/link", values);
      await load();
      sessionStorage.setItem("credit-onboarding", "1");
      notice(
        "Компания добавлена. Проверьте финансовые показатели перед заявкой.",
      );
      location.hash = "/company/financials";
      await render();
    } else if (type === "financials" || type === "credit-history") {
      const previous = type === "financials" ? state.financials : state.history;
      const changes = Object.fromEntries(Object.entries(values).filter(([key,value]) => value.trim() !== "" && (previous?.[key] == null || Number(value) !== Number(previous[key]))).map(([key,value]) => [key,Number(value)]));
      if (Object.keys(changes).length) await api("/company/" + type, {
        method: "PATCH", body: JSON.stringify(changes),
      });
      await load();
      notice("Финансовые данные сохранены");
      if (type === "financials" && sessionStorage.getItem("credit-onboarding")) {
        sessionStorage.removeItem("credit-onboarding");
        const selected = sessionStorage.getItem("credit-selected-product");
        sessionStorage.removeItem("credit-selected-product");
        location.hash = "/new";
      }
      await render();
    } else if (type === "application") {
      if (form.dataset.quoteReady !== "true")
        throw new Error("Дождитесь расчёта подходящих условий.");
      const payload = {
        ...values,
        term_months: Number(values.term_months),
      };
      let a;
      if (form.dataset.id)
        a = await api("/applications/" + form.dataset.id, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
      else a = await post("/applications", payload);
      state.applications = await api("/applications");
      if (event.submitter?.value === "draft") {
        notice("Черновик сохранён");
        location.hash = "/applications/" + a.id;
        await render();
      } else {
        state.busy = false;
        await submitApplication(a.id);
      }
    } else if (type === "review") {
      await post("/applications/" + form.dataset.id + "/review", {
        outcome: values.outcome,
        comment: values.comment || null,
      });
      notice("Решение специалиста сохранено");
      await render();
    }
  } catch (e) {
    error.textContent = e.message;
    error.className = "error";
    if (
      form.dataset.form === "register" &&
      e.status === 409 &&
      [
        "User with this email already exists",
        "Email already registered",
      ].includes(e.body?.detail)
    ) {
      const login = document.createElement("a");
      login.href = "#/login";
      login.className = "error-link";
      login.textContent = "Войти в аккаунт →";
      error.append(document.createElement("br"), login);
    }
    if (!(e instanceof ApiError) || e.status >= 500 || e.status === 429)
      notice(e.message, "error");
  } finally {
    state.busy = false;
    buttons.forEach((b) => (b.disabled = false));
  }
});
root.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-action]");
  if (!button) return;
  if (button.dataset.action === "close-registry-info") {
    root.querySelector(".registry-info").hidden = true;
    return;
  }
  if (["grant-credit-consent", "revoke-credit-consent", "refresh-credit"].includes(button.dataset.action)) {
    const action = button.dataset.action;
    if (action === "grant-credit-consent" && !root.querySelector('[data-credit-consent]')?.checked) {
      notice("Подтвердите согласие на запрос кредитного отчёта.", "error"); return;
    }
    button.disabled = true;
    try {
      if (action === "grant-credit-consent") await post("/company/credit-history/consent", {accepted:true,text_version:"credit-report-v1"});
      else if (action === "revoke-credit-consent") await api("/company/credit-history/consent", {method:"DELETE"});
      else await post("/company/credit-history/refresh");
      await load(); await render();
      notice(action === "refresh-credit" ? "Кредитный отчёт обновлён." : action === "grant-credit-consent" ? "Согласие сохранено. Теперь можно запросить отчёт." : "Согласие отозвано. Новые запросы к БКИ заблокированы.");
    } catch (e) { notice(e.message, "error"); button.disabled = false; }
    return;
  }
  if (button.dataset.action === "refresh-financials") {
    button.disabled = true;
    try {
      const data = await post("/company/financials/refresh");
      await load();
      notice(data.source === "UNAVAILABLE" ? "Финансовый источник пока не подключён." : "Загружены доступные показатели. Ручные данные сохранены.");
      await render();
    } catch (e) { notice(e.message, "error"); button.disabled = false; }
    return;
  }
  if (button.dataset.action === "refresh-company") {
    if (!state.registry?.configured) {
      root.querySelector(".registry-info").hidden = false;
      root
        .querySelector(".registry-info")
        .scrollIntoView?.({ behavior: "smooth", block: "nearest" });
      return;
    }
    button.disabled = true;
    try {
      await post("/company/refresh");
      await load();
      notice("Реквизиты обновлены из реестра.");
      await render();
    } catch (e) {
      notice(e.message, "error");
      button.disabled = false;
    }
    return;
  }
  if (button.dataset.action === "edit-financials") {
    const form = button.closest("form");
    form.dataset.locked = "false";
    form.querySelectorAll("input").forEach((input) => (input.readOnly = false));
    button.hidden = true;
    form.querySelector("input").focus();
    return;
  }
  if (
    button.dataset.action === "show-unlink" ||
    button.dataset.action === "cancel-unlink"
  ) {
    root.querySelector(".unlink-confirm").hidden =
      button.dataset.action === "cancel-unlink";
    if (button.dataset.action === "show-unlink")
      root
        .querySelector(".unlink-confirm")
        .scrollIntoView?.({ behavior: "smooth", block: "center" });
    return;
  }
  if (button.dataset.action === "unlink-company") {
    button.disabled = true;
    try {
      await api("/company", { method: "DELETE" });
      sessionStorage.removeItem("credit-onboarding");
      sessionStorage.removeItem("credit-selected-product");
    sessionStorage.removeItem("credit-selected-purpose");
      await load();
      notice("Компания отвязана. История заявок сохранена.");
      await render();
    } catch (e) {
      notice(e.message, "error");
      button.disabled = false;
    }
    return;
  }
  if (button.dataset.action === "toggle-password") {
    const input = button.closest(".password-input").querySelector("input");
    const show = input.type === "password";
    input.type = show ? "text" : "password";
    button.setAttribute("aria-pressed", String(show));
    button.setAttribute(
      "aria-label",
      show ? "Скрыть пароль" : "Показать пароль",
    );
    button.title = show ? "Скрыть пароль" : "Показать пароль";
    input.focus();
    return;
  }
  if (button.dataset.action === "logout") {
    sessionStorage.removeItem("credit-token");
    sessionStorage.removeItem("credit-onboarding");
    sessionStorage.removeItem("credit-selected-product");
    sessionStorage.removeItem("credit-selected-purpose");
    Object.assign(state, {
      token: null,
      user: null,
      company: null,
      financials: null,
      history: null,
      products: [],
      applications: [],
    });
    location.hash = "/login";
    await render();
  } else if (button.dataset.action === "reload") {
    state.user = null;
    await render();
  } else if (button.dataset.action === "refresh") {
    button.disabled = true;
    await render();
  }
});
window.addEventListener("hashchange", async (event) => {
  const companyTab = (url) =>
    ["/company", "/company/financials", "/financials"].includes(
      new URL(url).hash.slice(1),
    );
  const preserveScroll = companyTab(event.oldURL) && companyTab(event.newURL);
  const scrollPosition = window.scrollY;
  await render();
  if (preserveScroll) {
    window.scrollTo({ top: scrollPosition, behavior: "instant" });
    return;
  }
  window.scrollTo({
    top: 0,
    behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches
      ? "instant"
      : "smooth",
  });
});
const applicationFilters = { search: "", status: "", sort: "new" };
function filteredApplications() {
  const query = applicationFilters.search.trim().toLocaleLowerCase("ru");
  return state.applications.filter(a => (!applicationFilters.status || a.status === applicationFilters.status) &&
    `${a.id} ${a.pricing?.product_name || productById(a.product_id)?.name || ""} ${a.purpose || ""}`.toLocaleLowerCase("ru").includes(query))
    .sort((a,b) => applicationFilters.sort === "amount" ? Number(b.requested_amount)-Number(a.requested_amount) :
      applicationFilters.sort === "amount-asc" ? Number(a.requested_amount)-Number(b.requested_amount) :
      applicationFilters.sort === "term-asc" ? a.term_months-b.term_months :
      applicationFilters.sort === "term-desc" ? b.term_months-a.term_months :
      (new Date(b.created_at)-new Date(a.created_at)) * (applicationFilters.sort === "old" ? -1 : 1));
}
function updateApplicationList() {
  const search = root.querySelector('[data-application-search]');
  const focused = document.activeElement === search;
  const selection = search?.selectionStart;
  const content = document.createElement('div');
  content.innerHTML = applications();
  root.querySelector('.application-tools')?.replaceWith(content.querySelector('.application-tools'));
  root.querySelector('.table-wrap, .empty')?.replaceWith(content.querySelector('.table-wrap, .empty'));
  if (focused) {
    const next = root.querySelector('[data-application-search]');
    next.focus(); next.setSelectionRange(selection, selection);
  }
}
root.addEventListener('input', event => {
  if (event.target.matches('[data-application-search]')) {
    applicationFilters.search = event.target.value;
    updateApplicationList();
  }
});
root.addEventListener('change', event => {
  if (event.target.matches('[data-application-status], [data-application-sort]')) {
    applicationFilters[event.target.matches('[data-application-status]') ? 'status' : 'sort'] = event.target.value;
    updateApplicationList();
  }
});
function documentsPage() {
  return documentUploadPanel() + header('Всё важное под рукой.', 'Скачайте сведения из кабинета в формате JSON. Это выгрузки данных, а не банковские договоры.') +
    `<div class="grid document-grid">${[['company','Карточка компании','Реквизиты и сведения о компании'],['financials','Финансовые показатели','Показатели и доступные сведения о кредитной истории'],['applications','Мои заявки','Заявки, параметры, решения и история событий']].map(([key,title,text]) => `<article class="card"><span class="eyebrow">JSON</span><h2>${title}</h2><p>${text}</p><button class="secondary" data-export="${key}" ${key !== 'applications' && !state.company ? 'disabled' : ''}>Скачать файл ↓</button>${key !== 'applications' && !state.company ? '<p class="hint">Сначала привяжите компанию.</p>' : ''}</article>`).join('')}</div>`;
}
async function exportData(kind) {
  let data;
  if (kind === 'company') data = await api('/company');
  else if (kind === 'financials') {
    const [financials, credit_history] = await Promise.all([optional('/company/financials'), optional('/company/credit-history')]);
    data = { financials, credit_history };
  } else {
    const list = await api('/applications');
    data = [];
    // Limit concurrency and preserve the complete application snapshots and decisions.
    for (const application of list) {
      const [details, history, decision] = await Promise.all([
        api('/applications/' + application.id), api('/applications/' + application.id + '/history'), optional('/applications/' + application.id + '/decision')]);
      data.push({ ...details, history, decision });
    }
  }
  const blob = new Blob([JSON.stringify({ exported_at: new Date().toISOString(), format_version: 1, data }, null, 2)], {type:'application/json;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a'); link.href = url;
  link.download = `credit-${kind}-${new Date().toISOString().slice(0,10)}.json`;
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
let notificationEvents = [];
let notificationOwner = null;
let notificationsLoading = false;
function readNotificationIds() {
  try { return new Set(JSON.parse(localStorage.getItem('credit-read-' + state.user?.id) || '[]')); }
  catch { return new Set(); }
}
function updateUnreadBadge() {
  if (notificationOwner !== state.user?.id) notificationEvents = [];
  const read = readNotificationIds();
  const count = notificationEvents.filter(e => !read.has(e.id)).length;
  const badge = root.querySelector('[data-unread]');
  if (badge) { badge.hidden = !count; badge.textContent = count > 99 ? '99+' : String(count); }
  root.querySelector('[data-action="notifications"]')?.setAttribute('aria-label', count ? `Уведомления: ${count} непрочитанных` : 'Уведомления: новых нет');
}
async function refreshNotifications() {
  if (!state.token || !state.user || notificationsLoading || document.hidden) return;
  notificationsLoading = true;
  const owner = state.user.id;
  try {
    const list = await api('/applications');
    const events = [];
    for (let i=0; i<list.length; i+=5) {
      const batch = await Promise.all(list.slice(i,i+5).map(async a =>
        (await api('/applications/' + a.id + '/history')).map(e => ({...e, application_id:a.id}))));
      events.push(...batch.flat());
    }
    if (state.user?.id !== owner || !state.token) return;
    notificationOwner = owner;
    notificationEvents = events.filter(e => e.to_status && e.to_status !== e.from_status)
      .sort((a,b) => new Date(b.occurred_at)-new Date(a.occurred_at) || (b.sequence || 0)-(a.sequence || 0));
    updateUnreadBadge();
  } catch { /* Keep last successful events and retry on the next poll. */ }
  finally { notificationsLoading = false; }
}
function showModal(title, body) {
  document.querySelector('.cabinet-dialog')?.close();
  const dialog = document.createElement('dialog'); dialog.className = 'cabinet-dialog';
  dialog.innerHTML = `<div class="dialog-title"><h2 id="cabinet-dialog-title">${title}</h2><button class="dialog-close" aria-label="Закрыть">×</button></div><div class="dialog-body">${body}</div>`;
  dialog.setAttribute('aria-labelledby', 'cabinet-dialog-title');
  const trigger = document.activeElement;
  const previousInert = root.inert;
  const previousOverflow = document.documentElement.style.overflow;
  const previousBodyOverflow = document.body.style.overflow;
  root.inert = true;
  document.documentElement.style.overflow = 'hidden';
  document.body.style.overflow = 'hidden';
  dialog.addEventListener('close', () => {
    root.inert = previousInert;
    document.documentElement.style.overflow = previousOverflow;
    document.body.style.overflow = previousBodyOverflow;
    dialog.remove(); trigger?.focus();
  });
  dialog.querySelector('.dialog-close').onclick = () => dialog.close();
  dialog.addEventListener('click', e => { if (e.target === dialog) { const r=dialog.getBoundingClientRect(); if(e.clientX<r.left || e.clientX>r.right || e.clientY<r.top || e.clientY>r.bottom) dialog.close(); } });
  prepareMobileInputs(dialog);
  document.body.append(dialog); dialog.showModal();
  return dialog;
}
function showNotifications() {
  const read = readNotificationIds();
  const unreadCount = notificationEvents.filter(e => !read.has(e.id)).length;
  const dialog = showModal('Уведомления', notificationEvents.length ?
    `<div class="notification-toolbar"><span data-unread-summary>${unreadCount ? `${unreadCount} непрочитанных` : 'Все события прочитаны'}</span><button class="read-all" data-read-all ${unreadCount ? '' : 'disabled'}>Прочитать все ✓</button></div><ul class="notification-list">${notificationEvents.map(e => {
      const kind = e.to_status === 'DECISION' ? 'success' : e.to_status === 'REJECTED' ? 'declined' : e.to_status === 'NEED_MORE_DATA' ? 'attention' : 'progress';
      const glyph = {success:'✓', declined:'×', attention:'!', progress:'↗'}[kind];
      return `<li class="${read.has(e.id) ? '' : 'unread'}"><a href="#/applications/${esc(e.application_id)}" data-read-event="${esc(e.id)}"><span class="event-icon ${kind}" aria-hidden="true">${glyph}</span><div class="event-content"><div class="event-heading"><strong>${esc(statusNames[e.to_status] || eventNames[e.event_type] || 'Заявка обновлена')}</strong>${!read.has(e.id) ? '<span class="unread-dot" aria-label="Не прочитано"></span>' : ''}</div><span class="event-reference">Заявка №${esc(e.application_id.slice(0,8))}</span><small>${date(e.occurred_at)} · ${time(e.occurred_at)}</small></div><span class="event-arrow" aria-hidden="true">›</span></a></li>`;
    }).join('')}</ul>` :
    '<div class="notification-empty"><span class="event-icon progress" aria-hidden="true">✓</span><h3>Пока нет событий</h3><p>Сообщим здесь, когда изменится статус вашей заявки.</p></div>');
  dialog.classList.add('notifications-dialog');
  dialog.addEventListener('click', e => {
    const item = e.target.closest('[data-read-event]');
    if (!item && !e.target.closest('[data-read-all]')) return;
    if (item) read.add(item.dataset.readEvent); else notificationEvents.forEach(n => read.add(n.id));
    try { localStorage.setItem('credit-read-' + state.user.id, JSON.stringify([...read])); }
    catch { notice('Не удалось сохранить отметки о прочтении в браузере.', 'error'); }
    updateUnreadBadge();
    if (item) dialog.close(); else { dialog.querySelectorAll('.unread').forEach(n => n.classList.remove('unread')); dialog.querySelectorAll('.unread-dot').forEach(n => n.remove()); dialog.querySelector('[data-read-all]').disabled = true; dialog.querySelector('[data-unread-summary]').textContent = 'Все события прочитаны'; }
  });
}
root.addEventListener('click', async event => {
  const button = event.target.closest('[data-action="account"], [data-action="notifications"], [data-export]');
  if (!button) return;
  if (button.dataset.action === 'account') {
    const dialog = showModal('Ваш аккаунт', `<dl class="account-info"><dt>Имя и фамилия</dt><dd>${esc(state.user?.full_name)}</dd><dt>Электронная почта</dt><dd>${esc(state.user?.email)}</dd><dt>Компания</dt><dd>${esc(state.company?.name || 'Компания пока не привязана')}</dd>${state.company ? `<dt>ИНН</dt><dd>${esc(state.company.inn)}</dd>` : ''}</dl><button class="primary wide" data-dialog-logout>Выйти из аккаунта ↗</button>`);
    dialog.querySelector('[data-dialog-logout]').onclick = () => {
      dialog.close();
      const proxy = document.createElement('button'); proxy.dataset.action='logout'; proxy.hidden=true;
      root.append(proxy); proxy.click(); proxy.remove();
      notificationEvents=[]; notificationOwner=null;
      Object.assign(applicationFilters, {search:'',status:'',sort:'new'});
    };
  } else if (button.dataset.action === 'notifications') {
    button.disabled=true; await refreshNotifications(); button.disabled=false;
    if(state.token) showNotifications();
  } else {
    button.disabled=true;
    try { await exportData(button.dataset.export); }
    catch(e) { notice(e.message, 'error'); }
    finally { button.disabled=false; }
  }
});
setInterval(refreshNotifications, 30000);
window.addEventListener('focus', refreshNotifications);

// Keep focus feedback for keyboard navigation without a lingering mouse outline.
document.addEventListener('pointerdown', () => { document.documentElement.dataset.inputMode = 'pointer'; }, true);
document.addEventListener('keydown', event => {
  if (['Tab','ArrowUp','ArrowDown','ArrowLeft','ArrowRight','Enter',' '].includes(event.key)) document.documentElement.dataset.inputMode = 'keyboard';
}, true);

const documentLabels = {...fieldNames, active_credits:"Активные кредиты", closed_credits:"Закрытые кредиты", overdue_count:"Количество просрочек", overdue_amount:"Сумма просрочек"};
let documentDraft = null;
let documentUploading = false;
function documentUploadPanel() {
  return `<section class="card import-panel"><div><span class="eyebrow">Из документа в кабинет</span><h2>Загрузите вашу отчётность</h2><p>ИИ предложит показатели. Проверьте их, исправьте ошибки и выберите, что сохранить. До подтверждения данные компании не изменятся.</p><p class="hint">PDF до 20 страниц, изображения, XLSX, DOCX, CSV/TSV, XML, TXT и JSON · до 10 МБ. Сканы распознаются через OCR. Старые DOC/XLS сначала сохраните в новом формате.</p></div>${state.company ? `<label class="primary upload-label">Выбрать документ ↑<input type="file" data-document-file accept=".pdf,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.xlsx,.docx,.csv,.tsv,.xml,.txt,.json" ${documentUploading ? 'disabled' : ''}></label>` : '<a class="primary" href="#/company">Сначала привяжите компанию ↗</a>'}<p class="import-status" data-import-status role="status">${documentUploading ? 'Документ обрабатывается… Это может занять до трёх минут.' : ''}</p></section>`;
}
function showDocumentPreview(draft) {
  const current = {...state.financials,...state.history};
  const counts = new Set(['employees','active_credits','closed_credits','overdue_count']);
  const dialog = showModal('Проверьте данные документа', `<p class="hint">${esc(draft.filename)} · ${esc(draft.method)} · ИНН: ${esc(draft.inn || 'не найден')} · Единицы файла: ${esc(({rub:'рубли',thousand_rub:'тысячи рублей',million_rub:'миллионы рублей',unknown:'не определены'})[draft.unit])}</p>${draft.warnings.length ? `<ul class="import-warnings">${draft.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul>` : ''}<form data-import-confirm><div class="import-preview-fields"><label class="field">Год отчётности<input name="report_year" type="number" min="1900" max="${new Date().getFullYear()}" value="${esc(draft.report_year ?? '')}" placeholder="Не определён"></label>${Object.entries(documentLabels).map(([key,label]) => `<label class="field">${label}${counts.has(key) ? '' : ' · ₽'}<input name="${key}" type="number" ${key==='profit_annual' ? '' : 'min="0"'} step="${counts.has(key) ? 1 : '0.01'}" value="${esc(draft.values[key] ?? '')}" placeholder="Не найдено — можно заполнить вручную"><span class="hint">Сейчас в кабинете: ${current[key] == null ? 'нет данных' : counts.has(key) ? esc(current[key]) : money(current[key])}</span>${draft.evidence[key] ? `<blockquote>${esc(draft.evidence[key])}</blockquote>` : ''}</label>`).join('')}</div><details class="import-source"><summary>Прочитанный текст документа</summary><pre>${esc(draft.text_excerpt)}</pre></details><p class="hint">Сохранятся только заполненные поля. Пустые поля не заменят текущие значения. Все денежные суммы выше указаны в рублях. Данные останутся неподтверждёнными для кредитования.</p><label class="credit-consent"><input type="checkbox" name="accepted" required> Я проверил компанию, год, единицы измерения и показатели. Подтверждаю сохранение заполненных полей.</label><div data-import-error role="alert"></div><div class="actions"><button class="primary" type="submit" ${draft.company_mismatch ? 'disabled' : ''}>Сохранить показатели</button><button class="secondary" type="button" data-import-cancel>Отмена</button></div></form>`);
  dialog.classList.add('import-dialog');
  let saved = false;
  dialog.querySelector('[data-import-cancel]').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{ if(!saved) api('/company/documents/'+encodeURIComponent(draft.id),{method:'DELETE'}).catch(()=>{}); documentDraft=null; });
  dialog.querySelector('form').addEventListener('submit', async event=>{
    event.preventDefault();
    const form=event.target;
    if(!form.checkValidity() || draft.company_mismatch) return;
    const payload={accepted:form.elements.accepted.checked};
    const financialKeys=new Set([...Object.keys(fieldNames),'report_year']);
    for(const [key,value] of new FormData(form)) {
      if(key==='accepted' || value.trim()==='') continue;
      const group=financialKeys.has(key) ? 'financials' : 'credit_history';
      (payload[group] ||= {})[key]=Number(value);
    }
    const error=form.querySelector('[data-import-error]');
    if(!payload.financials && !payload.credit_history) { error.textContent='Заполните хотя бы один показатель.'; return; }
    form.querySelector('[type=submit]').disabled=true;
    try {
      await post('/company/documents/'+encodeURIComponent(draft.id)+'/confirm',payload);
      saved=true; dialog.close(); await load(); await render();
      notice('Показатели сохранены из документа. Для кредитования потребуется проверка специалистом.');
    } catch(e) {error.textContent=e.message;form.querySelector('[type=submit]').disabled=false;}
  });
}
root.addEventListener('change', async event=>{
  if(!event.target.matches('[data-document-file]') || !event.target.files.length || documentUploading) return;
  const input=event.target, file=input.files[0], owner=state.user?.id;
  if(file.size>10*1024*1024) { notice('Максимальный размер документа — 10 МБ.','error'); input.value='';return; }
  documentUploading=true; input.disabled=true;
  const status=root.querySelector('[data-import-status]');
  status.textContent='Читаем документ и сопоставляем показатели… Это может занять до трёх минут.';
  try {
    const draft=await api('/company/documents/preview?filename='+encodeURIComponent(file.name),{
      method:'POST',body:file,headers:{'Content-Type':'application/octet-stream'},timeoutMs:240000,timeoutMessage:'Разбор документа занял слишком много времени. Попробуйте файл меньшего размера или более чёткий скан.'});
    documentDraft=draft;
    status.textContent='Разбор завершён. Проверьте найденные показатели.';
    if(state.token && state.user?.id === owner) showDocumentPreview(draft);
  } catch(e) {status.textContent=e.message;notice(e.message,'error');}
  finally {documentUploading=false;input.disabled=false;input.value='';}
});

function prepareMobileInputs(container) {
  container.querySelectorAll('input[type="number"]').forEach(input => {
    input.inputMode = input.step === '1' || ['report_year', 'term_months', 'employees', 'active_credits', 'closed_credits', 'overdue_count'].includes(input.name) ? 'numeric' : 'decimal';
  });
  container.querySelectorAll('input[name="inn"]').forEach(input => { input.inputMode = 'numeric'; });
}
function updateVisibleViewport() {
  const viewport = window.visualViewport;
  document.documentElement.style.setProperty('--visible-height', `${viewport?.height || window.innerHeight}px`);
  document.documentElement.style.setProperty('--visual-top', `${viewport?.offsetTop || 0}px`);
}
window.visualViewport?.addEventListener('resize', updateVisibleViewport);
window.visualViewport?.addEventListener('scroll', updateVisibleViewport);
window.addEventListener('resize', updateVisibleViewport);
updateVisibleViewport();

const staffRoles = new Set(['ADMIN', 'REVIEWER']);
const roleNames = {USER:'Клиент', REVIEWER:'Проверяющий', ADMIN:'Администратор'};
const auditNames = {ADMIN_CREATED:'Создан администратор',ADMIN_CREDENTIALS_ROTATED:'Обновлены данные администратора',USER_ACCESS_CHANGED:'Изменён доступ',APPLICATION_REVIEWED:'Рассмотрена заявка'};
let adminUsers = [];
function adminTabs(section) {
  const tabs = state.user.role === 'ADMIN' ? [['overview','Обзор'],['applications','Заявки'],['users','Пользователи'],['audit','Журнал']] : [['applications','Заявки']];
  return `<nav class="admin-tabs" aria-label="Разделы управления">${tabs.map(([key,label])=>`<a class="${key===section?'active':''}" ${key===section?'aria-current="page"':''} href="#/admin?section=${key}">${label}</a>`).join('')}</nav>`;
}
function adminPager(result, section, params) {
  const link = offset => '#/admin?' + new URLSearchParams({...Object.fromEntries(params),section,offset:String(offset)});
  return `<div class="admin-pager"><span>Всего: ${result.total} · ${result.total ? result.offset+1 : 0}–${Math.min(result.offset+result.limit,result.total)}</span><div>${result.offset ? `<a class="secondary" href="${esc(link(Math.max(0,result.offset-result.limit)))}">← Назад</a>`:''}${result.offset+result.limit<result.total ? `<a class="secondary" href="${esc(link(result.offset+result.limit))}">Далее →</a>`:''}</div></div>`;
}
function adminSearch(section, params, statuses=false) {
  return `<form class="admin-search" data-admin-search><input type="hidden" name="section" value="${section}"><label class="field">Поиск<input name="q" maxlength="100" value="${esc(params.get('q')||'')}" placeholder="${statuses?'Компания, ИНН или номер заявки':'Имя или почта'}"></label>${statuses?`<label class="field">Статус<select name="status"><option value="">Все статусы</option>${Object.entries(statusNames).map(([key,label])=>`<option value="${key}" ${params.get('status')===key?'selected':''}>${label}</option>`).join('')}</select></label>`:''}<button class="primary">Найти</button></form>`;
}
async function adminPage(path) {
  if (!staffRoles.has(state.user.role)) return header('Доступ ограничен.','Этот раздел доступен только сотрудникам платформы.');
  const params=new URLSearchParams(location.hash.split('?')[1]||'');
  let section=params.get('section') || (state.user.role==='ADMIN'?'overview':'applications');
  if (!['overview','applications','users','audit'].includes(section)) section='applications';
  if (state.user.role!=='ADMIN') section='applications';
  const detailId=path.split('/')[2];
  if (detailId) return adminDetail(detailId);
  let html=header('Управление кабинетом.','Пользователи, заявки и решения специалистов в одном месте.','<button class="secondary" data-action="refresh">Обновить ↻</button>')+adminTabs(section);
  const query=new URLSearchParams({offset:String(Math.max(0,parseInt(params.get('offset')||'0',10)||0)),limit:'25'});
  if(params.get('q')) query.set('q',params.get('q'));
  if(section==='overview') {
    const d=await api('/admin/overview');
    html+=`<div class="admin-metrics">${[['Пользователи',d.users],['Компании',d.companies],['Всего заявок',d.applications],['Доступ приостановлен',d.blocked_users]].map(([label,n])=>`<section class="card"><p>${esc(label)}</p><strong>${esc(n)}</strong></section>`).join('')}</div><section class="card"><h2>Работа с заявками</h2><div class="admin-status-grid">${Object.entries(statusNames).map(([key,label])=>`<a href="#/admin?section=applications&status=${encodeURIComponent(key)}"><span>${esc(label)}</span><strong>${esc(d.statuses[key]||0)} ↗</strong></a>`).join('')}</div><p class="hint">Решение специалиста доступно для заявок на ручной проверке. Первоначальная оценка и данные на момент подачи сохраняются.</p></section>`; // nosemgrep: javascript.browser.security.raw-html-concat.raw-html-concat -- dynamic text is escaped and URLs are encoded; markup and classes are fixed.
  } else if(section==='users') {
    const d=await api('/admin/users?'+query); adminUsers=d.items;
    html+=adminSearch(section,params)+`<div class="admin-user-list">${d.items.map(u=>`<article class="card admin-user"><div><h3>${esc(u.full_name)}</h3><p>${esc(u.email)}</p><small>${esc(u.company_name||'Компания не привязана')}</small></div><div><span class="pill">${esc(roleNames[u.role]||'Неизвестная роль')}</span> <span class="pill ${u.is_active?'':'bad'}">${u.is_active?'Доступ открыт':'Заблокирован'}</span></div>${u.role!=='ADMIN'?`<button class="secondary" data-admin-user="${esc(u.id)}">Настроить доступ</button>`:'<span class="hint">Серверное управление</span>'}</article>`).join('')||'<div class="empty">Пользователи не найдены</div>'}</div>`+adminPager(d,section,params); // nosemgrep: javascript.browser.security.raw-html-concat.raw-html-concat -- dynamic text is escaped and URLs are encoded; markup and classes are fixed.
  } else if(section==='applications') {
    if(params.get('status'))query.set('status',params.get('status'));
    const d=await api('/admin/applications?'+query);
    html+=adminSearch(section,params,true)+`<div class="admin-application-list">${d.items.map(a=>`<a class="card admin-application" href="#/admin/${esc(a.id)}"><div><span class="hint">№${esc(a.id.slice(0,8))} · ${esc(date(a.created_at))} ${esc(time(a.created_at))}</span><h3>${esc(a.company_name)}</h3><p class="hint">ИНН ${esc(a.inn)} · ${esc(a.owner_email)}</p></div><div><strong>${esc(money(a.requested_amount))}</strong><p>${esc(a.term_months)} мес.</p></div><div>${pill(a.status)}<span class="admin-open">Открыть →</span></div></a>`).join('')||'<div class="empty">По этим условиям заявок нет</div>'}</div>`+adminPager(d,section,params); // nosemgrep: javascript.browser.security.raw-html-concat.raw-html-concat -- dynamic text is escaped and URLs are encoded; markup and classes are fixed.
  } else {
    query.delete('q');const d=await api('/admin/audit?'+query);
    html+=`<section class="card"><h2>Журнал действий сотрудников</h2><p class="hint">Причина, исполнитель и время изменения доступа или решения.</p><ol class="admin-audit">${d.items.map(e=>`<li><strong>${esc(auditNames[e.action]||e.action)}</strong><p>${esc(e.actor_email)} · ${esc(date(e.created_at))} ${esc(time(e.created_at))}</p><span class="hint">Объект: ${esc(e.target_id)}</span><pre>${esc(JSON.stringify(e.details,null,2))}</pre></li>`).join('')||'<li>Действий пока нет</li>'}</ol></section>`+adminPager(d,section,params); // nosemgrep: javascript.browser.security.raw-html-concat.raw-html-concat -- API text and formatted dates are escaped before insertion.
  }
  return html;
}
async function adminDetail(id) {
  const d=await api('/admin/applications/'+encodeURIComponent(id)),a=d.application;
  let html=header('Заявка №'+esc(a.id.slice(0,8)),esc(d.company.name)+' · ИНН '+esc(d.company.inn),'<a class="secondary" href="#/admin?section=applications">← К очереди</a>');
  html+=`<div class="columns"><section class="card"><h2>Параметры заявки</h2>${pill(a.status)}${dataList([['Компания',d.company.name],['Заявитель',d.owner.full_name+' · '+d.owner.email],['Сумма',money(a.requested_amount)],['Срок',a.term_months+' мес.'],['Цель',a.purpose],['Дополнительные сведения',a.additional_info||'—'],['Создана',date(a.created_at)+' '+time(a.created_at)]])}</section><section class="card"><h2>Первоначальная оценка</h2>${d.decision?`${dataList([['Результат',({APPROVED:'Предварительно одобрено',REJECTED:'Отказ',CONDITIONAL_APPROVAL:'Нужна ручная проверка'})[d.decision.outcome]],['Источник',d.decision.source],['Риск',d.decision.risk_score+' / 100']])}<p>${esc(d.decision.explanation)}</p><ul class="factor-list">${[...d.decision.conditions,...d.decision.top_factors].map(s=>`<li>${esc(s)}</li>`).join('')}</ul>`:'<p>Оценка ещё не сформирована.</p>'}${d.review?`<h3>Решение специалиста</h3><p>${d.review.outcome==='APPROVED'?'Предварительно одобрено':'Отклонено'} · ${date(d.review.created_at)} ${time(d.review.created_at)}</p><p>${esc(d.review.comment)}</p>`:''}</section></div>`;
  html+=`<section class="card admin-snapshots"><h2>Данные на момент рассмотрения</h2><p class="hint">Сохранённые версии, на которых основана оценка. Показатели из загруженного файла и ручного ввода требуют проверки источника. Показаны последние 20 версий.</p>${d.snapshots.map(s=>`<details><summary>Версия ${s.version} · ${date(s.captured_at)} ${time(s.captured_at)}</summary><pre>${esc(JSON.stringify(s.data,null,2))}</pre></details>`).join('')||'<p>Данные ещё не зафиксированы.</p>'}</section>`;
  if(a.status==='MANUAL_REVIEW')html+=`<form class="card admin-review" data-admin-review="${esc(id)}"><h2>Решение специалиста</h2><p class="hint">Перед сохранением проверьте документы и источники. Решение записывается в историю; исходная оценка сохраняется.</p><label class="field">Решение<select name="outcome"><option value="APPROVED">Предварительно одобрить</option><option value="REJECTED">Отклонить</option></select></label><label class="field">Обоснование<textarea name="comment" minlength="3" maxlength="1000" required placeholder="Какие сведения проверены и почему принято это решение"></textarea></label><button class="primary">Проверить и сохранить</button></form>`;
  html+=`<section class="card admin-history"><h2>История заявки</h2><ol class="timeline">${d.events.map(e=>`<li>${esc(eventNames[e.event_type]||e.event_type)}<small>${date(e.occurred_at)} · ${time(e.occurred_at)}</small></li>`).join('')}</ol></section>`;
  return html;
}
root.addEventListener('submit', e=>{
  const search=e.target.closest('[data-admin-search]');
  if(search){e.preventDefault();location.hash='/admin?'+new URLSearchParams(new FormData(search));return;}
  const form=e.target.closest('[data-admin-review]');
  if(!form)return;e.preventDefault();if(!form.reportValidity())return;
  const values=Object.fromEntries(new FormData(form)),id=form.dataset.adminReview;
  const dialog=showModal('Подтвердите решение',`<p>Заявка №${esc(id.slice(0,8))}: <strong>${values.outcome==='APPROVED'?'предварительно одобрить':'отклонить'}</strong>.</p><p>${esc(values.comment)}</p><p class="hint">Решение и комментарий сохранятся в истории заявки и журнале действий.</p><p data-admin-error role="alert"></p><button class="primary wide" data-admin-confirm>Подтвердить решение</button>`);
  dialog.querySelector('[data-admin-confirm]').onclick=async event=>{
    event.target.disabled=true;
    try{await post('/admin/applications/'+encodeURIComponent(id)+'/review',values);dialog.close();await render();notice('Решение специалиста сохранено.');}
    catch(error){dialog.querySelector('[data-admin-error]').textContent=error.message;event.target.disabled=false;}
  };
});
root.addEventListener('click',e=>{
  const button=e.target.closest('[data-admin-user]');if(!button)return;
  const user=adminUsers.find(u=>u.id===button.dataset.adminUser);if(!user)return;
  const dialog=showModal('Доступ пользователя',`<p><strong>${esc(user.full_name)}</strong><br>${esc(user.email)}</p><form data-access-form><label class="field">Роль<select name="role"><option value="USER" ${user.role==='USER'?'selected':''}>Клиент</option><option value="REVIEWER" ${user.role==='REVIEWER'?'selected':''}>Проверяющий</option></select></label><label class="field">Доступ<select name="active"><option value="true" ${user.is_active?'selected':''}>Разрешён</option><option value="false" ${!user.is_active?'selected':''}>Заблокирован</option></select></label><label class="field">Причина изменения<textarea name="reason" required minlength="3" maxlength="500"></textarea></label><p class="hint">Изменение роли действует на следующие запросы. Блокировка запрещает вход и прекращает доступ по уже выданным токенам.</p><p data-admin-error role="alert"></p><button class="primary wide">Сохранить доступ</button></form>`);
  dialog.querySelector('form').onsubmit=async event=>{
    event.preventDefault();const form=event.target;if(!form.reportValidity())return;
    const save=form.querySelector('button');save.disabled=true;
    try{await api('/admin/users/'+encodeURIComponent(user.id),{method:'PATCH',body:JSON.stringify({role:form.elements.role.value,is_active:form.elements.active.value==='true',reason:form.elements.reason.value})});dialog.close();await render();notice('Доступ обновлён.');}
    catch(error){form.querySelector('[data-admin-error]').textContent=error.message;save.disabled=false;}
  };
});

render();
